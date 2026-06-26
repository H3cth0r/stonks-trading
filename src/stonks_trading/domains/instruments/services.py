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
    "get_candle_date_range",
    "update_instrument_data",
    "discover_and_register_instruments",
]
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.config import settings
from stonks_trading.shared.ingest.massive import MassiveAdapter
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


async def get_candle_date_range(
    symbol: str, duckdb_path: str = "data/neat.db"
) -> tuple[datetime | None, datetime | None]:
    """Get the date range of existing candles for a symbol.

    Args:
        symbol: Trading symbol
        duckdb_path: Path to DuckDB database

    Returns:
        Tuple of (min_date, max_date) or (None, None) if no data
    """

    def _query_range():
        duckdb = DuckDBClient(db_path=duckdb_path)
        duckdb.connect()
        try:
            result = duckdb._conn.execute(
                """
                SELECT MIN(timestamp) as min_date, MAX(timestamp) as max_date
                FROM ohlcv_1m
                WHERE symbol = ?
                """,
                [symbol],
            ).fetchone()
            return result
        finally:
            duckdb.close()

    row = await asyncio.to_thread(_query_range)
    if row and row[0] and row[1]:
        # Ensure offset-naive datetimes for consistent comparison
        min_date = (
            row[0].replace(tzinfo=None) if hasattr(row[0], "tzinfo") and row[0].tzinfo else row[0]
        )
        max_date = (
            row[1].replace(tzinfo=None) if hasattr(row[1], "tzinfo") and row[1].tzinfo else row[1]
        )
        return min_date, max_date
    return None, None


async def backfill_from_massive(
    symbol: str,
    days: int = 730,
    duckdb_path: str = "data/neat.db",
    job_id: str | None = None,
    incremental: bool = False,
) -> dict[str, Any]:
    """Backfill historical data from Massive API.

    Supports resumable backfill - will only download missing date ranges.

    Args:
        symbol: Symbol to backfill (e.g., 'BTC_USD')
        days: Number of days to backfill (default 730 = 2 years)
        duckdb_path: Path to DuckDB database
        job_id: Optional job ID for status tracking (generates if not provided)
        incremental: If True, only fetch data from last known candle to now

    Returns:
        dict with job_id, status, candles_downloaded, duration_seconds
    """
    import asyncio

    job_id = job_id or str(uuid.uuid4())

    # Check existing data range
    existing_min, existing_max = await get_candle_date_range(symbol, duckdb_path)

    end = datetime.utcnow()

    if incremental and existing_max:
        # Incremental mode: only fetch from last known date to now
        start = existing_max
        logger.info(
            "Starting incremental backfill",
            job_id=job_id,
            symbol=symbol,
            from_date=start.isoformat(),
            to_date=end.isoformat(),
        )
    elif existing_min and existing_max:
        # Check if we need to extend the range
        target_start = end - timedelta(days=days)
        if existing_min <= target_start and existing_max >= end - timedelta(hours=1):
            # Already have complete data
            logger.info(
                "Backfill already complete",
                symbol=symbol,
                existing_min=existing_min.isoformat(),
                existing_max=existing_max.isoformat(),
            )
            return {
                "job_id": job_id,
                "status": "completed",
                "symbol": symbol,
                "candles_downloaded": 0,
                "message": "Data already up to date",
                "start_date": existing_min.isoformat(),
                "end_date": existing_max.isoformat(),
            }
        # Determine what range we need
        if existing_max < end - timedelta(hours=1):
            # Need to fetch newer data
            start = existing_max
            logger.info(
                "Resuming backfill from existing data",
                job_id=job_id,
                symbol=symbol,
                existing_max=existing_max.isoformat(),
                target_end=end.isoformat(),
            )
        else:
            start = end - timedelta(days=days)
    else:
        # Fresh backfill
        start = end - timedelta(days=days)
        logger.info(
            "Starting fresh Massive backfill",
            job_id=job_id,
            symbol=symbol,
            days=days,
        )

    # Update status to running
    await set_job_status(
        job_id,
        {
            "status": "running",
            "symbol": symbol,
            "progress": 0,
            "candles_downloaded": 0,
            "existing_min": existing_min.isoformat() if existing_min else None,
            "existing_max": existing_max.isoformat() if existing_max else None,
        },
    )

    def _do_backfill() -> dict[str, Any]:
        """Run blocking backfill operations in thread."""
        # Initialize DuckDB
        duckdb = DuckDBClient(db_path=duckdb_path)
        duckdb.connect()

        # Initialize adapter
        adapter = MassiveAdapter(api_key=settings.massive_api_key)

        try:
            # Fetch candles (blocking I/O)
            symbol_obj = Symbol(value=symbol)
            import asyncio as inner_asyncio

            candles = inner_asyncio.run(adapter.backfill(symbol_obj, start, end))

            # Store to DuckDB (blocking I/O)
            count = duckdb.insert_candles_batch(candles)

            return {
                "job_id": job_id,
                "status": "completed",
                "symbol": symbol,
                "candles_downloaded": count,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }

        finally:
            duckdb.close()
            inner_asyncio.run(adapter.disconnect())

    try:
        # Run blocking operations in thread pool to not block event loop
        result = await asyncio.to_thread(_do_backfill)

        logger.info(
            "Massive backfill complete",
            job_id=job_id,
            symbol=symbol,
            candles_stored=result["candles_downloaded"],
        )

        # Update job status in Redis
        await set_job_status(job_id, result)

        return result

    except Exception as e:
        logger.error("Backfill failed", job_id=job_id, symbol=symbol, error=str(e))
        error_result = {
            "job_id": job_id,
            "status": "failed",
            "symbol": symbol,
            "error": str(e),
        }
        await set_job_status(job_id, error_result)
        raise


async def update_instrument_data(symbol: str, duckdb_path: str = "data/neat.db") -> dict[str, Any]:
    """Fetch latest data for an instrument (incremental update).

    Args:
        symbol: Trading symbol to update
        duckdb_path: Path to DuckDB database

    Returns:
        dict with update status and candles downloaded
    """
    job_id = str(uuid.uuid4())

    # Check existing data
    existing_min, existing_max = await get_candle_date_range(symbol, duckdb_path)

    if not existing_max:
        logger.warning("No existing data found, running full backfill", symbol=symbol)
        return await backfill_from_massive(symbol, days=730, job_id=job_id)

    # Check if data is recent (within last hour)
    time_since_update = datetime.utcnow() - existing_max
    if time_since_update < timedelta(hours=1):
        logger.info(
            "Data is already up to date", symbol=symbol, last_update=existing_max.isoformat()
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "symbol": symbol,
            "candles_downloaded": 0,
            "message": "Data already up to date",
            "last_update": existing_max.isoformat(),
            "time_since_update_minutes": time_since_update.total_seconds() / 60,
        }

    # Run incremental backfill
    logger.info(
        "Updating instrument data",
        symbol=symbol,
        last_update=existing_max.isoformat(),
        time_behind_hours=time_since_update.total_seconds() / 3600,
    )

    return await backfill_from_massive(symbol, days=730, job_id=job_id, incremental=True)


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


async def discover_and_register_instruments(
    duckdb_path: str = "data/neat.db",
) -> list[dict[str, Any]]:
    """Discover existing instruments in DuckDB and auto-register them.

    On startup, scans the database for symbols with data and ensures they
    are registered in the instrument registry. If data exists but the
    instrument is not registered, auto-creates the registration.

    Args:
        duckdb_path: Path to DuckDB database

    Returns:
        List of discovered/registered instruments with their status
    """
    from pathlib import Path

    # Check if database exists
    if not Path(duckdb_path).exists():
        logger.info("No existing DuckDB database found, skipping discovery")
        return []

    def _discover_symbols():
        """Query DuckDB for unique symbols."""
        duckdb = DuckDBClient(db_path=duckdb_path)
        duckdb.connect()
        try:
            result = duckdb._conn.execute(
                """
                SELECT DISTINCT symbol FROM ohlcv_1m
                """
            ).fetchall()
            return [row[0] for row in result if row[0]]
        except Exception as e:
            logger.warning("Could not query DuckDB for symbols", error=str(e))
            return []
        finally:
            duckdb.close()

    # Get symbols from database
    symbols = await asyncio.to_thread(_discover_symbols)

    if not symbols:
        logger.info("No existing instrument data found in DuckDB")
        return []

    discovered = []
    for symbol in symbols:
        # Check if already registered
        existing = await get_instrument(symbol)
        if existing:
            # Check if data is up to date
            min_date, max_date = await get_candle_date_range(symbol, duckdb_path)
            time_since_update = datetime.utcnow() - max_date if max_date else timedelta(days=999)

            if time_since_update > timedelta(hours=1):
                # Data is stale, trigger update
                logger.info(
                    "Instrument data is stale, updating",
                    symbol=symbol,
                    last_update=max_date.isoformat() if max_date else None,
                    hours_behind=time_since_update.total_seconds() / 3600,
                )
                asyncio.create_task(update_instrument_data(symbol, duckdb_path))
                discovered.append(
                    {
                        "symbol": symbol,
                        "action": "updating",
                        "existing": True,
                        "last_update": max_date.isoformat() if max_date else None,
                    }
                )
            else:
                discovered.append(
                    {
                        "symbol": symbol,
                        "action": "already_registered",
                        "existing": True,
                        "last_update": max_date.isoformat() if max_date else None,
                    }
                )
        else:
            # Auto-register with backfill disabled (data already exists)
            logger.info("Auto-registering discovered instrument", symbol=symbol)
            await register_instrument(
                symbol=symbol,
                name=symbol,
                auto_backfill=False,  # Don't backfill, data exists
                backfill_days=730,
            )
            # Mark as ready since data exists
            await update_instrument_status(
                symbol,
                status="ready",
                last_backfill_at=datetime.utcnow(),
            )
            discovered.append(
                {
                    "symbol": symbol,
                    "action": "auto_registered",
                    "existing": False,
                }
            )

    logger.info(
        "Instrument discovery complete",
        found=len(symbols),
        registered=len([d for d in discovered if d["action"] == "auto_registered"]),
    )

    return discovered
