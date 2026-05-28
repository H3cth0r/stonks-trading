"""Instrument domain services.

Business logic for instrument registry + market data operations.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis

from stonks_trading.domains.instruments.entities import Instrument
from stonks_trading.domains.instruments.repositories import (
    get_instrument,
    list_instruments,
    save_instrument,
    update_instrument_status,
)

# Re-export repository functions for convenience
__all__ = [
    "get_instrument",
    "list_instruments",
    "save_instrument",
    "register_instrument",
    "enable_instrument",
    "disable_instrument",
    "get_instrument_status",
    "backfill_from_massive",
    "set_job_status",
    "get_job_status",
]
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.config import settings
from stonks_trading.shared.ingest.massive import MassiveAdapter
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


async def backfill_from_massive(
    symbol: str,
    days: int = 730,
    duckdb_path: str = "data/neat.db",
    job_id: str | None = None,
) -> dict[str, Any]:
    """Backfill historical data from Massive API.

    Args:
        symbol: Symbol to backfill (e.g., 'BTC_USD')
        days: Number of days to backfill (default 730 = 2 years)
        duckdb_path: Path to DuckDB database
        job_id: Optional job ID for status tracking (generates if not provided)

    Returns:
        dict with job_id, status, candles_downloaded, duration_seconds
    """
    job_id = job_id or str(uuid.uuid4())

    logger.info("Starting Massive backfill", job_id=job_id, symbol=symbol, days=days)

    # Initialize DuckDB
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    # Initialize adapter
    adapter = MassiveAdapter(api_key=settings.massive_api_key)

    try:
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        # Fetch candles
        symbol_obj = Symbol(value=symbol)
        candles = await adapter.backfill(symbol_obj, start, end)

        # Store to DuckDB
        count = duckdb.insert_candles_batch(candles)

        result = {
            "job_id": job_id,
            "status": "completed",
            "symbol": symbol,
            "candles_downloaded": count,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }

        logger.info(
            "Massive backfill complete",
            job_id=job_id,
            symbol=symbol,
            candles_stored=count,
        )

        # Update job status in Redis
        await set_job_status(job_id, result)

        return result

    finally:
        duckdb.close()
        await adapter.disconnect()


async def set_job_status(job_id: str, status: dict[str, Any], ttl: int = 3600) -> None:
    """Store job status in Redis with TTL."""
    r = redis.from_url(settings.redis_url)
    await r.set(f"backfill:job:{job_id}", json.dumps(status), ex=ttl)
    await r.aclose()


async def get_job_status(job_id: str) -> dict[str, Any] | None:
    """Get job status from Redis."""
    r = redis.from_url(settings.redis_url)
    data = await r.get(f"backfill:job:{job_id}")
    await r.aclose()
    return json.loads(data) if data else None


# =============================================================================
# Instrument Registry Services
# =============================================================================


async def register_instrument(
    symbol: str,
    name: str = "",
    auto_backfill: bool = True,
    backfill_days: int = 730,
) -> Instrument:
    """Register a new trading instrument.

    Args:
        symbol: Trading symbol (e.g., 'BTC_USD')
        name: Human-readable name
        auto_backfill: Whether to auto-backfill 2 years of data
        backfill_days: Number of days to backfill

    Returns:
        Registered instrument
    """
    # Check if already exists
    existing = await get_instrument(symbol)
    if existing:
        logger.info(f"Instrument already exists: {symbol}")
        return existing

    # Create new instrument
    instrument = Instrument(
        symbol=symbol.upper(),
        name=name or symbol.upper(),
        auto_backfill=auto_backfill,
        backfill_days=backfill_days,
        status="pending",
    )

    # Save to registry
    await save_instrument(instrument)

    # Trigger backfill if enabled
    if auto_backfill:
        return await trigger_backfill(instrument)

    return instrument


async def trigger_backfill(instrument: Instrument) -> Instrument:
    """Trigger backfill for an instrument (fire-and-forget).

    Args:
        instrument: Instrument to backfill

    Returns:
        Updated instrument with backfill job_id
    """
    job_id = str(uuid.uuid4())

    instrument.backfill_job_id = job_id
    instrument.status = "backfilling"

    await save_instrument(instrument)

    # Fire-and-forget backfill task
    asyncio.create_task(
        _run_backfill_and_update_status(instrument.symbol, job_id, instrument.backfill_days)
    )

    logger.info(
        f"Started backfill for {instrument.symbol}",
        job_id=job_id,
        days=instrument.backfill_days,
    )

    return instrument


async def _run_backfill_and_update_status(symbol: str, job_id: str, days: int) -> None:
    """Run backfill and update instrument status when complete."""
    try:
        result = await backfill_from_massive(
            symbol=symbol,
            days=days,
            job_id=job_id,
        )
        if result.get("status") == "completed":
            await update_instrument_status(
                symbol,
                status="ready",
                last_backfill_at=datetime.utcnow(),
            )
            logger.info(f"Backfill complete for {symbol}", candles=result.get("candles_downloaded"))
        else:
            await update_instrument_status(symbol, status="error")
    except Exception as e:
        logger.error(f"Backfill failed for {symbol}", error=str(e))
        await update_instrument_status(symbol, status="error")


async def enable_instrument(symbol: str) -> Instrument | None:
    """Enable an instrument for trading.

    Args:
        symbol: Instrument symbol

    Returns:
        Updated instrument or None if not found
    """
    instrument = await get_instrument(symbol)
    if not instrument:
        return None

    if instrument.status != "ready" and instrument.auto_backfill:
        # Can't enable until backfill is complete
        logger.warning(f"Cannot enable {symbol} - backfill not complete")
        return None

    instrument.enabled = True
    instrument.updated_at = datetime.utcnow()

    return await save_instrument(instrument)


async def disable_instrument(symbol: str) -> Instrument | None:
    """Disable an instrument from trading.

    Args:
        symbol: Instrument symbol

    Returns:
        Updated instrument or None if not found
    """
    instrument = await get_instrument(symbol)
    if not instrument:
        return None

    instrument.enabled = False
    instrument.updated_at = datetime.utcnow()

    return await save_instrument(instrument)


async def get_instrument_status(symbol: str) -> dict[str, Any] | None:
    """Get full status including backfill progress.

    Args:
        symbol: Instrument symbol

    Returns:
        Status dict with backfill progress
    """
    instrument = await get_instrument(symbol)
    if not instrument:
        return None

    status = {
        "symbol": instrument.symbol,
        "status": instrument.status,
        "enabled": instrument.enabled,
        "backfill_job_id": instrument.backfill_job_id,
        "last_backfill_at": instrument.last_backfill_at.isoformat()
        if instrument.last_backfill_at
        else None,
    }

    # Check backfill job status if running
    if instrument.backfill_job_id and instrument.status == "backfilling":
        job_status = await get_job_status(instrument.backfill_job_id)
        if job_status:
            status["backfill_progress"] = job_status.get("progress", 0)
            status["backfill_status"] = job_status.get("status", "unknown")
            if job_status.get("status") == "completed":
                status["backfill_candles"] = job_status.get("candles_downloaded", 0)

    return status


async def check_backfill_completion(symbol: str) -> bool:
    """Check if backfill is complete and update status.

    Args:
        symbol: Instrument symbol

    Returns:
        True if backfill is complete, False otherwise
    """
    instrument = await get_instrument(symbol)
    if not instrument or not instrument.backfill_job_id:
        return False

    job_status = await get_job_status(instrument.backfill_job_id)
    if not job_status:
        return False

    if job_status.get("status") == "completed":
        await update_instrument_status(
            symbol,
            status="ready",
            last_backfill_at=datetime.utcnow(),
        )
        return True
    elif job_status.get("status") == "failed":
        await update_instrument_status(
            symbol,
            status="error",
        )
        return True  # Still "complete" (failed)

    return False
