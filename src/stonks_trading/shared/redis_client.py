"""Redis client module for shared infrastructure.

Provides async Redis connection singleton and key utilities.
Required for Phase 10A live visualization infrastructure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis

from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger


class RedisKeys:
    """Key naming conventions for Redis data.

    Provides consistent key patterns across the application.
    """

    @staticmethod
    def equity_history(bot_type: str, instance_id: str) -> str:
        """Key for equity history list.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier

        Returns:
            Redis key for equity history
        """
        return f"equity:history:{bot_type}:{instance_id}"

    @staticmethod
    def bot_state(bot_type: str, instance_id: str) -> str:
        """Key for current bot state.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier

        Returns:
            Redis key for bot state
        """
        return f"bot:state:{bot_type}:{instance_id}"

    @staticmethod
    def live_data(symbol: str) -> str:
        """Key for live price data.

        Args:
            symbol: Trading symbol

        Returns:
            Redis key for live price
        """
        return f"live:price:{symbol}"

    @staticmethod
    def candles(symbol: str, timeframe: str) -> str:
        """Key for cached candles.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe (1m, 5m, 1h, etc)

        Returns:
            Redis key for cached candles
        """
        return f"candles:{timeframe}:{symbol}"


# Global Redis connection pool
_redis_pool: redis.ConnectionPool | None = None
_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get async Redis client singleton.

    Returns:
        Redis client instance
    """
    global _redis_pool, _redis_client

    if _redis_client is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=False,
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        logger.info("Redis connection established")

    return _redis_client


async def close_redis() -> None:
    """Close Redis connection pool."""
    global _redis_pool, _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None

    logger.info("Redis connection closed")


@asynccontextmanager
async def redis_session() -> AsyncIterator[redis.Redis]:
    """Context manager for Redis sessions.

    Yields:
        Redis client
    """
    client = await get_redis()
    try:
        yield client
    finally:
        pass  # Don't close - singleton managing lifecycle


async def set_with_expiry(key: str, value: Any, expiry_seconds: int | None = None) -> bool:
    """Set key with optional expiry.

    Args:
        key: Redis key
        value: Value to store
        expiry_seconds: TTL in seconds (defaults to settings.live_data_ttl_seconds)

    Returns:
        True if successful
    """
    client = await get_redis()
    expiry = expiry_seconds or settings.live_data_ttl_seconds
    return await client.setex(key, expiry, value)


async def get_equity_history(
    bot_type: str,
    instance_id: str,
    limit: int = 100,
) -> list[float]:
    """Get equity history for bot.

    Args:
        bot_type: Bot type identifier
        instance_id: Bot instance identifier
        limit: Maximum number of points to return

    Returns:
        List of equity values (oldest first)
    """
    client = await get_redis()
    key = RedisKeys.equity_history(bot_type, instance_id)
    values = await client.lrange(key, 0, limit - 1)
    return [float(v) for v in values]


async def push_equity(bot_type: str, instance_id: str, equity: float) -> int:
    """Push equity value to history.

    Args:
        bot_type: Bot type identifier
        instance_id: Bot instance identifier
        equity: Current equity value

    Returns:
        New list length
    """
    client = await get_redis()
    key = RedisKeys.equity_history(bot_type, instance_id)

    # Push and trim to max points
    await client.lpush(key, str(equity))
    await client.ltrim(key, 0, settings.equity_history_max_points - 1)

    return await client.llen(key)
