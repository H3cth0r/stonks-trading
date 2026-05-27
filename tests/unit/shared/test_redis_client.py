"""Unit tests for redis_client module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRedisKeys:
    """Tests for RedisKeys key generation."""

    def test_equity_history_key(self):
        """equity_history generates correct key format."""
        key = RedisKeys.equity_history("neat_swing", "bot_1")
        assert key == "equity:history:neat_swing:bot_1"

    def test_bot_state_key(self):
        """bot_state generates correct key format."""
        key = RedisKeys.bot_state("neat_swing", "bot_1")
        assert key == "bot:state:neat_swing:bot_1"

    def test_live_data_key(self):
        """live_data generates correct key format."""
        key = RedisKeys.live_data("BTC_USD")
        assert key == "live:price:BTC_USD"

    def test_candles_key(self):
        """candles generates correct key format."""
        key = RedisKeys.candles("BTC_USD", "1h")
        assert key == "candles:1h:BTC_USD"


class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.mark.asyncio
    async def test_cache_manager_get_returns_cached(self):
        """get returns cached value when exists."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b'{"key": "value"}')

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            result = await manager.get("test_key")

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_cache_manager_get_returns_none_when_missing(self):
        """get returns None when key not found."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            result = await manager.get("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_manager_set_serializes_json(self):
        """set serializes value to JSON."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            await manager.set("test_key", {"data": 123}, ttl=60)

        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert call_args[0][0] == "test_key"
        assert call_args[0][1] == 60
        assert '"data": 123' in call_args[0][2]

    @pytest.mark.asyncio
    async def test_cache_manager_invalidate_deletes_matching_keys(self):
        """invalidate deletes keys matching pattern."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()
        mock_client = AsyncMock()

        async def mock_scan_iter(match):
            if match == "test:*":
                yield "test:key1"
                yield "test:key2"

        mock_client.scan_iter = mock_scan_iter
        mock_client.delete = AsyncMock()

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            await manager.invalidate("test:*")

        mock_client.delete.assert_called_once_with("test:key1", "test:key2")

    @pytest.mark.asyncio
    async def test_cache_manager_get_or_set_returns_cached(self):
        """get_or_set returns cached value without calling factory."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b'"cached"')

        factory = AsyncMock(return_value="new_value")

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            result = await manager.get_or_set("key", factory)

        assert result == "cached"
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_manager_get_or_set_calls_factory_on_miss(self):
        """get_or_set calls factory when key missing."""
        from stonks_trading.shared.redis_client import CacheManager

        manager = CacheManager()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.setex = AsyncMock()

        factory = AsyncMock(return_value="new_value")

        with patch("stonks_trading.shared.redis_client.get_redis", return_value=mock_client):
            result = await manager.get_or_set("new_key", factory)

        assert result == "new_value"
        factory.assert_called_once()


class TestCacheKeys:
    """Tests for CACHE_KEYS constants."""

    def test_cache_keys_structure(self):
        """CACHE_KEYS contains expected patterns."""
        from stonks_trading.shared.redis_client import CACHE_KEYS

        assert CACHE_KEYS["portfolio"] == "portfolio:summary"
        assert CACHE_KEYS["bots"] == "bots:list"
        assert CACHE_KEYS["models"] == "models:list:{strategy_type}"
        assert CACHE_KEYS["trades"] == "trades:recent:{limit}"


# Import for tests
from stonks_trading.shared.redis_client import RedisKeys
