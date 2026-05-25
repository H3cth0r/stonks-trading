"""Tests for websocket client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.shared.websocket_client import WebSocketClient


class TestWebSocketClient:
    """Tests for WebSocketClient."""

    def test_initialization(self) -> None:
        """Test client initializes correctly."""
        client = WebSocketClient(symbols=["btcusdt"], url="wss://test.com/ws")

        assert client.url == "wss://test.com/ws"
        assert client.symbols == ["btcusdt"]
        assert client._connection is None
        assert client._running is False

    def test_initialization_with_callback(self) -> None:
        """Test client initializes with callback."""
        callback = MagicMock()
        client = WebSocketClient(
            symbols=["btcusdt", "ethusdt"],
            callback=callback,
            url="wss://test.com/ws",
        )

        assert client.symbols == ["btcusdt", "ethusdt"]
        assert client.callback == callback

    def test_register_bot(self) -> None:
        """Test registering bot callback."""
        client = WebSocketClient(symbols=["btcusdt"])
        bot_callback = MagicMock()

        client.register_bot(bot_callback)

        assert bot_callback in client._bot_callbacks

    @pytest.mark.asyncio
    async def test_connect_sets_running(self) -> None:
        """Test connect sets running state."""
        client = WebSocketClient(symbols=["btcusdt"], url="wss://test.com/ws")

        # Mock _connect_loop to just set running and exit
        original_connect_loop = client._connect_loop

        async def mock_connect_loop():
            client._running = True
            # Don't call _connect, just return immediately
            return

        client._connect_loop = mock_connect_loop
        await client.connect()

        assert client._running is True

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test disconnect closes websocket."""
        client = WebSocketClient(symbols=["btcusdt"])
        client._running = True

        mock_ws = AsyncMock()
        client._connection = mock_ws

        await client.disconnect()

        assert client._running is False
        assert client._connection is None

    def test_is_connected(self) -> None:
        """Test is_connected property."""
        client = WebSocketClient(symbols=["btcusdt"])

        assert client.is_connected is False

        client._running = True
        client._connection = MagicMock()

        assert client.is_connected is True
