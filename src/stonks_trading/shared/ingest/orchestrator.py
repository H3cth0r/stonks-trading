"""Main ingestion orchestrator combining adapter, storage, and features.

The orchestrator coordinates the data ingestion pipeline:
1. Receives candles from adapter (WebSocket)
2. Computes features (live feature computer)
3. Stores in DuckDB (hot cache)
4. Archives to Tigris (cold storage, async)
5. Handles gaps (backfill via adapter REST)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.adapter import Candle, MarketDataAdapter
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient
from stonks_trading.shared.storage.tigris_client import TigrisClient


class IngestionOrchestrator:
    """Orchestrates the data ingestion pipeline.

    Combines market data adapter, feature computer, and storage clients
    into a cohesive data pipeline that:
    - Receives real-time candles from WebSocket
    - Computes features using rolling windows
    - Stores in DuckDB (hot cache) for fast queries
    - Archives to Tigris S3 (cold storage) for disaster recovery
    - Handles gaps via REST API backfill

    The orchestrator is designed to run continuously, handling
    disconnections, reconnections, and data gaps automatically.

    Example:
        orchestrator = IngestionOrchestrator(
            adapter=BinanceAdapter(),
            duckdb=DuckDBClient(),
            tigris=tigris_client,
            feature_computer=LiveFeatureComputer(),
        )
        await orchestrator.start([Symbol(value="BTC_USD")])
        # ... run for some time ...
        await orchestrator.stop()
    """

    def __init__(
        self,
        adapter: MarketDataAdapter,
        duckdb: DuckDBClient,
        tigris: TigrisClient | None,
        feature_computer: LiveFeatureComputer,
    ) -> None:
        """Initialize the ingestion orchestrator.

        Args:
            adapter: Market data adapter (e.g., BinanceAdapter)
            duckdb: DuckDB client for hot cache
            tigris: Tigris S3 client for archival (optional)
            feature_computer: Live feature computer
        """
        self.adapter = adapter
        self.duckdb = duckdb
        self.tigris = tigris
        self.features = feature_computer
        self._last_candle: dict[str, datetime] = {}  # symbol -> last timestamp
        self._buffer: dict[str, list[Candle]] = {}   # symbol -> monthly buffer
        self._running = False
        self._gap_threshold = timedelta(minutes=2)

        # Register ourselves as candle handler
        self.adapter.on_candle(self._on_candle)

    async def start(self, symbols: list[Symbol]) -> None:
        """Start ingestion for given symbols.

        Performs the following steps:
        1. Backfills recent history for each symbol
        2. Connects to live WebSocket stream

        Args:
            symbols: List of symbols to ingest data for
        """
        self._running = True

        # Backfill recent history first
        for symbol in symbols:
            await self._backfill_symbol(symbol)

        # Connect to live stream
        await self.adapter.connect(symbols)

        logger.info(
            "Ingestion orchestrator started",
            symbols=[s.value for s in symbols],
        )

    async def _backfill_symbol(self, symbol: Symbol) -> None:
        """Backfill last 24 hours of data.

        Checks DuckDB for existing data and fills any gaps by
        querying the adapter's REST API.

        Args:
            symbol: Symbol to backfill
        """

        end = datetime.now(UTC)
        start = end - timedelta(hours=24)

        # Check what we already have
        latest = self.duckdb.get_latest_timestamp(symbol)
        if latest:
            # Handle timezone-aware vs timezone-naive datetime comparison
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=UTC)
            start = latest + timedelta(minutes=1)

        if start >= end:
            logger.info(
                "No backfill needed, data is up to date",
                symbol=symbol.value,
            )
            return

        logger.info(
            "Backfilling symbol",
            symbol=symbol.value,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        try:
            candles = await self.adapter.backfill(symbol, start, end)

            for candle in candles:
                self._process_candle(candle)

            logger.info(
                "Backfill complete",
                symbol=symbol.value,
                candles_fetched=len(candles),
            )

        except Exception as e:
            logger.error(
                "Backfill failed",
                symbol=symbol.value,
                error=str(e),
            )
            # Continue anyway - live stream will catch up

    def _on_candle(self, candle: Candle) -> None:
        """Handle new closed candle from WebSocket.

        Detects gaps by checking if this candle's timestamp is
        more than 2 minutes after the last candle. If a gap is
        detected, triggers async backfill.

        Args:
            candle: Normalized closed candle
        """
        symbol = candle.symbol

        # Detect gaps
        if symbol in self._last_candle:
            gap = candle.timestamp - self._last_candle[symbol]
            if gap > self._gap_threshold:  # Missed at least 1 candle
                logger.warning(
                    "Gap detected",
                    symbol=symbol,
                    gap_seconds=gap.total_seconds(),
                    last=self._last_candle[symbol].isoformat(),
                    current=candle.timestamp.isoformat(),
                )
                # Trigger async backfill
                asyncio.create_task(
                    self._backfill_gap(symbol, self._last_candle[symbol], candle.timestamp)
                )

        self._last_candle[symbol] = candle.timestamp
        self._process_candle(candle)

    def _process_candle(self, candle: Candle) -> None:
        """Process candle: compute features, store.

        Computes features using the feature computer, stores the
        candle with features in DuckDB, and buffers for Tigris upload.

        Args:
            candle: Normalized closed candle
        """
        # Compute features
        features = self.features.on_candle(candle)

        if features is None:
            # Not enough data yet, store without features
            features = {}

        # Store in DuckDB
        try:
            self.duckdb.insert_candle(candle, features)
        except Exception as e:
            logger.error(
                "Failed to store candle in DuckDB",
                symbol=candle.symbol,
                error=str(e),
            )

        # Buffer for monthly Parquet upload
        if candle.symbol not in self._buffer:
            self._buffer[candle.symbol] = []
        self._buffer[candle.symbol].append(candle)

        # Flush buffer periodically (every 1000 candles or 15 minutes)
        buffer_size = len(self._buffer[candle.symbol])
        if buffer_size >= 1000:
            asyncio.create_task(self._flush_buffer(candle.symbol))

    async def _backfill_gap(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Backfill detected gap.

        Fetches missing candles via REST API and processes them.

        Args:
            symbol: Symbol with gap
            start: Gap start time
            end: Gap end time
        """
        logger.info(
            "Backfilling gap",
            symbol=symbol,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        try:
            candles = await self.adapter.backfill(
                Symbol(value=symbol), start, end
            )
            for candle in candles:
                self._process_candle(candle)

            logger.info(
                "Gap backfill complete",
                symbol=symbol,
                candles_fetched=len(candles),
            )

        except Exception as e:
            logger.error(
                "Gap backfill failed",
                symbol=symbol,
                error=str(e),
            )

    async def _flush_buffer(self, symbol: str) -> None:
        """Flush symbol's buffer to Tigris.

        Uploads buffered candles as a Parquet partition to Tigris S3.

        Args:
            symbol: Symbol to flush
        """
        if not self.tigris:
            self._buffer[symbol] = []
            return

        candles = self._buffer.get(symbol, [])
        if not candles:
            return

        # Clear buffer immediately to avoid duplicate uploads
        self._buffer[symbol] = []

        try:
            key = self.tigris.upload_candles_as_partition(symbol, candles)

            logger.info(
                "Flushed candles to Tigris",
                symbol=symbol,
                key=key,
                candles=len(candles),
            )

        except Exception as e:
            logger.error(
                "Failed to flush buffer to Tigris",
                symbol=symbol,
                error=str(e),
            )
            # Restore buffer for retry
            self._buffer[symbol] = candles + self._buffer.get(symbol, [])

    async def stop(self) -> None:
        """Stop ingestion gracefully.

        Disconnects from WebSocket and flushes all pending buffers.
        """
        self._running = False

        # Disconnect adapter
        await self.adapter.disconnect()

        # Flush remaining buffers
        if self.tigris:
            for symbol in list(self._buffer.keys()):
                await self._flush_buffer(symbol)

        logger.info("Ingestion orchestrator stopped")

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics.

        Returns:
            Dictionary with current state statistics
        """
        return {
            "running": self._running,
            "symbols": list(self._last_candle.keys()),
            "buffer_sizes": {
                symbol: len(candles)
                for symbol, candles in self._buffer.items()
            },
            "feature_stats": self.features.get_stats(),
        }
