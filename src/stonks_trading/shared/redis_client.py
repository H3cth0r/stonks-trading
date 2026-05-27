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
    result = await client.setex(key, expiry, value)
    return bool(result)


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
    values_raw = await client.lrange(key, 0, limit - 1)  # type: ignore[misc]
    values_str = values_raw if isinstance(values_raw, list) else []
    return [float(v) for v in values_str]


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
    await client.lpush(key, str(equity))  # type: ignore[misc]
    await client.ltrim(key, 0, settings.equity_history_max_points - 1)  # type: ignore[misc]

    result_raw = await client.llen(key)  # type: ignore[misc]
    return int(result_raw)


# Cache key patterns for Phase 10H performance optimization
CACHE_KEYS = {
    "portfolio": "portfolio:summary",
    "bots": "bots:list",
    "models": "models:list:{strategy_type}",
    "trades": "trades:recent:{limit}",
}


class CacheManager:
    """Cache manager for frequently accessed data.

    Phase 10H: Add caching layer for frequently accessed data.
    """

    def __init__(self, default_ttl: int = 300):
        """Initialize cache manager.

        Args:
            default_ttl: Default TTL in seconds (5 minutes)
        """
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        """Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        import json

        client = await get_redis()
        data = await client.get(key)
        if data:
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return data.decode("utf-8") if isinstance(data, bytes) else data
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Cache value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if not specified)
        """
        import json

        client = await get_redis()
        ttl = ttl or self.default_ttl
        serialized = json.dumps(value, default=str)
        await client.setex(key, ttl, serialized)

    async def invalidate(self, pattern: str) -> None:
        """Invalidate cache by pattern.

        Args:
            pattern: Key pattern to match (e.g., "models:*")
        """
        client = await get_redis()
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await client.delete(*keys)

    async def get_or_set(self, key: str, factory: Any, ttl: int | None = None) -> Any:
        """Get from cache or compute and cache if not present.

        Args:
            key: Cache key
            factory: Async callable to compute value if not cached
            ttl: TTL in seconds

        Returns:
            Cached or computed value
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await factory() if callable(factory) else factory
        await self.set(key, value, ttl)
        return value


# Global cache manager instance
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager.

    Returns:
        CacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
