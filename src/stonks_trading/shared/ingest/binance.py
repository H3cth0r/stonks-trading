"""Binance market data adapter (WebSocket + REST).

This module provides a Binance-specific implementation of the MarketDataAdapter,
supporting real-time WebSocket streaming and REST API backfill.
"""

import asyncio
import contextlib
import json
from datetime import datetime
from typing import Any

import httpx
import websockets
from websockets.client import ClientProtocol as WebSocketClientProtocol

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.ingest.adapter import Candle, MarketDataAdapter
from stonks_trading.shared.logger import logger


class BinanceAdapter(MarketDataAdapter):
    """Binance Spot market data adapter.

    Connects to Binance's WebSocket API for real-time 1-minute klines and
    uses the REST API for historical backfill and gap repair.

    WebSocket URL: wss://stream.binance.com:9443/stream
    REST URL: https://api.binance.com

    Supports combined streams for multiple symbols in a single connection.
    Automatically reconnects with exponential backoff on connection failures.

    Example:
        adapter = BinanceAdapter()
        adapter.on_candle(my_handler)
        await adapter.connect([Symbol(value="BTC_USD")])
        # ... run event loop ...
        await adapter.disconnect()
    """

    WS_URL = "wss://stream.binance.com:9443"
    REST_URL = "https://api.binance.com"
    TESTNET_WS_URL = "wss://testnet.binance.vision"
    TESTNET_REST_URL = "https://testnet.binance.vision"

    def __init__(self, use_testnet: bool = False) -> None:
        """Initialize Binance adapter.

        Args:
            use_testnet: If True, use Binance Spot Testnet instead of production.
                        Testnet is recommended for development and testing.
        """
        super().__init__(venue="binance")
        self.ws: WebSocketClientProtocol | None = None
        self._symbols: list[Symbol] = []
        self._reconnect_attempts = 0
        self._max_reconnect_delay = 60
        self._running = False
        self._message_task: asyncio.Task[Any] | None = None
        self._use_testnet = use_testnet

        # Select URLs based on testnet flag
        self._ws_url = self.TESTNET_WS_URL if use_testnet else self.WS_URL
        self._rest_url = self.TESTNET_REST_URL if use_testnet else self.REST_URL

    def _to_venue_symbol(self, symbol: Symbol) -> str:
        """Convert canonical symbol to Binance format.

        Converts BTC_USD -> BTCUSDT (Binance spot format)

        Args:
            symbol: Canonical symbol (e.g., BTC_USD)

        Returns:
            Binance symbol format (e.g., BTCUSDT)
        """
        # BTC_USD -> BTCUSDT
        return symbol.value.replace("_USD", "USDT")

    def _from_venue_symbol(self, venue_symbol: str) -> Symbol:
        """Convert Binance symbol to canonical format.

        Converts BTCUSDT -> BTC_USD (canonical format)

        Args:
            venue_symbol: Binance symbol (e.g., BTCUSDT)

        Returns:
            Canonical Symbol (e.g., BTC_USD)
        """
        # BTCUSDT -> BTC_USD
        base = venue_symbol.replace("USDT", "").replace("USDC", "")
        return Symbol(value=f"{base}_USD")

    async def connect(self, symbols: list[Symbol]) -> None:
        """Connect to combined WebSocket stream.

        Establishes a WebSocket connection to Binance's combined stream endpoint
        for 1-minute klines of the specified symbols.

        Args:
            symbols: List of canonical symbols to subscribe to

        Raises:
            ConnectionError: If WebSocket connection fails
        """
        import ssl

        self._symbols = symbols
        self._running = True

        # Build stream path
        # Production WebSocket is public and free - works for both mainnet and testnet
        # Testnet WebSocket for klines is often unavailable, so we use production WS
        streams = "/".join(f"{self._to_venue_symbol(s).lower()}@kline_1m" for s in symbols)

        # Always use production WebSocket for market data (klines are public)
        # Testnet is only used for REST API (orders, account)
        if len(symbols) == 1:
            url = f"wss://stream.binance.com:9443/ws/{streams}"
        else:
            url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        if self._use_testnet:
            logger.info(
                "Using production WebSocket for market data (testnet WS unavailable)",
                symbols=[s.value for s in symbols],
            )

        # SSL context - disable verification for development
        # On macOS, Python may not find system certificates properly
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        logger.warning("SSL verification disabled for development - use only for testing!")

        try:
            self.ws = await websockets.connect(url, ssl=ssl_context)
            self._reconnect_attempts = 0
            logger.info(
                "Connected to Binance WebSocket",
                venue="binance",
                streams=streams,
                testnet=self._use_testnet,
            )

            # Start message loop in background task
            self._message_task = asyncio.create_task(self._message_loop())

        except Exception as e:
            logger.error(
                "Failed to connect to Binance WebSocket",
                error=str(e),
                url=url,
            )
            raise ConnectionError(f"Failed to connect to Binance WebSocket: {e}") from e

    async def _message_loop(self) -> None:
        """Main WebSocket message loop with auto-reconnect.

        Continuously receives messages from the WebSocket and processes them.
        Handles connection closures and errors with automatic reconnection
        using exponential backoff.

        This loop runs until disconnect() is called.
        """
        while self._running:
            try:
                if not self.ws:
                    await self._reconnect()
                    continue

                msg = await self.ws.recv()
                await self._handle_message(json.loads(msg))

            except websockets.ConnectionClosed:
                logger.warning(
                    "Binance WebSocket closed, attempting reconnect...",
                    attempt=self._reconnect_attempts,
                )
                await self._reconnect()

            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse WebSocket message",
                    error=str(e),
                )

            except Exception as e:
                logger.error(
                    "Error in message loop",
                    error=str(e),
                )
                await asyncio.sleep(1)

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff.

        Implements exponential backoff starting at 1 second, doubling
        each attempt up to a maximum of 60 seconds.

        Waits for the calculated delay, then attempts to reconnect with
        the same symbols that were previously subscribed.
        """
        delay = min(2**self._reconnect_attempts, self._max_reconnect_delay)
        logger.info(
            "Reconnecting to Binance WebSocket",
            delay_seconds=delay,
            attempt=self._reconnect_attempts,
        )
        await asyncio.sleep(delay)

        try:
            await self.connect(self._symbols)
            self._reconnect_attempts = 0
            logger.info("Successfully reconnected to Binance WebSocket")
        except Exception as e:
            self._reconnect_attempts += 1
            logger.error(
                "Reconnection failed",
                error=str(e),
                next_attempt=self._reconnect_attempts,
            )

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Parse WebSocket message and emit candle.

        Processes kline (candlestick) messages from Binance WebSocket.
        Only emits candles when the candle is closed (k["x"] == True).

        Args:
            msg: Parsed JSON message from WebSocket
        """
        data = msg.get("data", {})
        if data.get("e") != "kline":
            return

        k = data["k"]
        if not k.get("x", False):  # Not closed yet
            return

        candle = Candle(
            symbol=self._from_venue_symbol(data["s"]).value,
            venue="binance",
            timestamp=datetime.fromtimestamp(k["t"] / 1000),
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            closed=True,
        )

        self._emit_candle(candle)

    async def backfill(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Backfill via Binance REST klines endpoint.

        Fetches historical 1-minute klines from Binance's REST API.
        Paginates automatically to retrieve all data in the requested range.

        Binance returns max 1000 candles per request, so this method
        makes multiple requests as needed.

        Args:
            symbol: Canonical symbol to fetch data for
            start: Start time (inclusive)
            end: End time (inclusive)

        Returns:
            List of normalized candles in chronological order

        Raises:
            httpx.HTTPError: If REST API request fails
        """
        candles: list[Candle] = []
        current_start = int(start.timestamp() * 1000)  # Binance uses milliseconds
        end_ms = int(end.timestamp() * 1000)

        logger.info(
            "Starting Binance backfill",
            symbol=symbol.value,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        async with httpx.AsyncClient() as client:
            while current_start < end_ms:
                params: dict[str, Any] = {
                    "symbol": self._to_venue_symbol(symbol),
                    "interval": "1m",
                    "startTime": current_start,
                    "limit": 1000,
                }

                try:
                    response = await client.get(
                        f"{self._rest_url}/api/v3/klines",
                        params=params,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        break

                    for row in data:
                        candles.append(
                            Candle(
                                symbol=symbol.value,
                                venue="binance",
                                timestamp=datetime.fromtimestamp(row[0] / 1000),
                                open=float(row[1]),
                                high=float(row[2]),
                                low=float(row[3]),
                                close=float(row[4]),
                                volume=float(row[5]),
                                closed=True,
                            )
                        )

                    # Move to next batch: last candle's close time + 1 minute
                    current_start = data[-1][6] + 1  # row[6] is close time

                    # Rate limiting: avoid hitting Binance limits
                    await asyncio.sleep(0.1)

                except httpx.HTTPStatusError as e:
                    logger.error(
                        "Binance API error during backfill",
                        status_code=e.response.status_code,
                        error=str(e),
                    )
                    raise
                except Exception as e:
                    logger.error(
                        "Unexpected error during backfill",
                        error=str(e),
                    )
                    raise

        logger.info(
            "Backfill complete",
            symbol=symbol.value,
            candles_fetched=len(candles),
        )

        return candles

    async def disconnect(self) -> None:
        """Clean disconnect from stream.

        Stops the message loop and closes the WebSocket connection.
        Safe to call multiple times.
        """
        self._running = False

        # Cancel message loop task
        if self._message_task and not self._message_task.done():
            self._message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._message_task

        # Close WebSocket
        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info("Disconnected from Binance WebSocket")
