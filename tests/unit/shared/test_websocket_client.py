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

    @pytest.mark.asyncio
    async def test_subscribe_adds_new_symbols(self) -> None:
        """Test subscribe adds new symbols."""
        client = WebSocketClient(symbols=["btcusdt"])

        await client.subscribe(["ethusdt", "btcusdt"])

        assert "ethusdt" in client.symbols
        assert "btcusdt" in client.symbols

    @pytest.mark.asyncio
    async def test_handle_message_combined_stream_format(self) -> None:
        """Test handling combined stream format from Binance."""
        callback = MagicMock()
        client = WebSocketClient(symbols=["btcusdt"], callback=callback)

        combined_data = {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "k": {
                    "s": "BTCUSDT",
                    "t": 1234567890000,
                    "T": 1234567896000,
                    "o": "50000.00",
                    "h": "50100.00",
                    "l": "49900.00",
                    "c": "50050.00",
                    "v": "1.5",
                    "x": True,
                },
            },
        }

        await client._handle_message(combined_data)

        callback.assert_called_once()
        candle = callback.call_args[0][0]
        assert candle["symbol"] == "btcusdt"
        assert candle["closed"] is True

    @pytest.mark.asyncio
    async def test_handle_message_single_stream_format(self) -> None:
        """Test handling single stream format."""
        callback = MagicMock()
        client = WebSocketClient(symbols=["btcusdt"], callback=callback)

        single_data = {
            "e": "kline",
            "k": {
                "s": "ETHUSDT",
                "t": 1234567890000,
                "T": 1234567896000,
                "o": "3000.00",
                "h": "3100.00",
                "l": "2900.00",
                "c": "3050.00",
                "v": "10.5",
                "x": True,
            },
        }

        await client._handle_message(single_data)

        callback.assert_called_once()
        candle = callback.call_args[0][0]
        assert candle["symbol"] == "ethusdt"

    @pytest.mark.asyncio
    async def test_process_kline_skips_incomplete_candles(self) -> None:
        """Test that only closed candles are processed."""
        callback = MagicMock()
        client = WebSocketClient(symbols=["btcusdt"], callback=callback)

        incomplete_kline = {
            "e": "kline",
            "k": {
                "s": "BTCUSDT",
                "t": 1234567890000,
                "T": 1234567896000,
                "o": "50000.00",
                "h": "50100.00",
                "l": "49900.00",
                "c": "50050.00",
                "v": "1.5",
                "x": False,  # Not closed
            },
        }

        await client._handle_message(incomplete_kline)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_callbacks_invoked_on_kline(self) -> None:
        """Test bot callbacks are called on kline."""
        bot_callback1 = MagicMock()
        bot_callback2 = MagicMock()
        client = WebSocketClient(symbols=["btcusdt"])
        client.register_bot(bot_callback1)
        client.register_bot(bot_callback2)

        kline_data = {
            "e": "kline",
            "k": {
                "s": "BTCUSDT",
                "t": 1234567890000,
                "T": 1234567896000,
                "o": "50000.00",
                "h": "50100.00",
                "l": "49900.00",
                "c": "50050.00",
                "v": "1.5",
                "x": True,
            },
        }

        await client._handle_message(kline_data)

        assert bot_callback1.called
        assert bot_callback2.called
