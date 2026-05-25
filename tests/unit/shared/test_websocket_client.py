"""Tests for websocket client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.shared.websocket_client import WebSocketClient


class TestWebSocketClient:
    """Tests for WebSocketClient."""

    def test_initialization(self) -> None:
        """Test client initializes correctly."""
        client = WebSocketClient("wss://test.com/ws")

        assert client.url == "wss://test.com/ws"
        assert client._ws is None
        assert client._running is False

    def test_initialization_with_headers(self) -> None:
        """Test client initializes with headers."""
        headers = {"Authorization": "Bearer token123"}
        client = WebSocketClient("wss://test.com/ws", headers=headers)

        assert client.headers == headers

    @pytest.mark.asyncio
    async def test_connect_creates_websocket(self) -> None:
        """Test connect creates websocket."""
        client = WebSocketClient("wss://test.com/ws")

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws

            await client.connect()

            assert client._running is True
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test disconnect closes websocket."""
        client = WebSocketClient("wss://test.com/ws")
        client._running = True

        mock_ws = AsyncMock()
        client._ws = mock_ws

        await client.disconnect()

        assert client._running is False

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        """Test sending message."""
        client = WebSocketClient("wss://test.com/ws")

        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._running = True

        await client.send({"type": "subscribe", "symbol": "BTC_USD"})

        mock_ws.send.assert_called_once()

    def test_is_connected(self) -> None:
        """Test is_connected property."""
        client = WebSocketClient("wss://test.com/ws")

        assert client.is_connected is False

        client._running = True
        client._ws = MagicMock()

        assert client.is_connected is True
