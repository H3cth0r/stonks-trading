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
    async def test_connect_creates_websocket(self) -> None:
        """Test connect creates websocket."""
        client = WebSocketClient(symbols=["btcusdt"], url="wss://test.com/ws")

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws

            # Override _connect to avoid the actual connection loop
            async def mock_connect_impl():
                client._connection = mock_ws
                client._running = True

            client._connect = mock_connect_impl
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
