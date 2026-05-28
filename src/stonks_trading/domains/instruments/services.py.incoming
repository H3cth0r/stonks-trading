"""Market data services for backfill operations.

Pure business logic - NO FastAPI imports.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis

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
