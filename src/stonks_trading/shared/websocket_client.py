"""WebSocket client for real-time market data.

Connects to Binance WebSocket streams for 1m klines and broadcasts
to all registered bots. Handles reconnection with exponential backoff.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://stream.binance.com:9443/stream"


class WebSocketClient:
    """Shared WebSocket manager for market data.

    Connects to exchange WebSocket streams, parses normalized candle data,
    and broadcasts to registered bots via callback.
    """

    def __init__(
        self,
        symbols: list[str],
        callback: Callable[[dict[str, Any]], Any] | None = None,
        url: str = BINANCE_WS_URL,
    ):
        """Initialize WebSocket client.

        Args:
            symbols: List of trading symbols (e.g., ["btcusdt", "ethusdt"])
            callback: Optional callback for received candles
            url: WebSocket URL
        """
        self.symbols = [s.lower() for s in symbols]
        self.callback = callback
        self.url = url
        self._connection: Any | None = None
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._bot_callbacks: list[Callable[[dict[str, Any]], Any]] = []

    def register_bot(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        """Register a bot callback for candle updates.

        Args:
            callback: Function to call with each candle
        """
        self._bot_callbacks.append(callback)

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        self._running = True
        self._reconnect_delay = 1.0
        await self._connect_loop()

    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully."""
        self._running = False
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _connect_loop(self) -> None:
        """Main connection loop with auto-reconnect."""
        while self._running:
            try:
                await self._connect()
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _connect(self) -> None:
        """Establish WebSocket connection and listen."""
        # Build stream URL
        streams = "/".join(f"{s}@kline_1m" for s in self.symbols)
        uri = f"{self.url}?streams={streams}"

        async with websockets.connect(uri) as ws:
            self._connection = ws
            logger.info(f"Connected to WebSocket: {streams}")

            async for message in ws:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message.

        Args:
            data: Parsed JSON message
        """
        # Binance combined stream format
        if "stream" in data and "data" in data:
            stream_data = data["data"]
            await self._process_kline(stream_data)
        elif "e" in data and data["e"] == "kline":
            # Single stream format
            await self._process_kline(data)

    async def _process_kline(self, kline_data: dict[str, Any]) -> None:
        """Process kline/candle data.

        Args:
            kline_data: Kline data from WebSocket
        """
        k = kline_data.get("k", {})
        if not k.get("x"):  # Only process closed candles
            return

        # Normalize candle format
        symbol = k.get("s", "").lower()
        candle = {
            "symbol": symbol,
            "ts_open": k.get("t"),
            "ts_close": k.get("T"),
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "closed": True,
        }

        # Call registered callbacks
        if self.callback:
            self.callback(candle)

        for callback in self._bot_callbacks:
            try:
                callback(candle)
            except Exception as e:
                logger.error(f"Bot callback error: {e}")

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to additional symbols.

        Args:
            symbols: Additional symbols to subscribe
        """
        new_symbols = [s.lower() for s in symbols if s.lower() not in self.symbols]
        if new_symbols:
            self.symbols.extend(new_symbols)
            # Note: Reconnection required for new subscriptions
            # This is a limitation of Binance combined streams
            logger.info(f"Added symbols: {new_symbols}. Reconnection required.")
