"""Market data adapter protocol and base classes.

This module defines the abstract base class for market data adapters,
providing a consistent interface for WebSocket streaming and REST backfill
from different exchanges.
"""

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from stonks_trading.domains.trading.value_objects import Symbol


@dataclass(frozen=True)
class Candle:
    """Normalized OHLCV candle from any venue.

    All market data adapters must emit candles in this normalized format,
    regardless of the source exchange's native format.

    Attributes:
        symbol: Canonical symbol (e.g., BTC_USD)
        venue: Source venue (binance, kraken, etc.)
        timestamp: Candle open time (UTC)
        open: Opening price
        high: High price
        low: Low price
        close: Closing price
        volume: Trading volume
        closed: True if candle is finalized (x=true in Binance terms)
    """

    symbol: str
    venue: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool

    def to_feature_inputs(self) -> dict[str, float]:
        """Convert to format expected by feature engineering.

        Returns:
            Dictionary with OHLCV values for feature computation.
        """
        return {
            "Open": self.open,
            "High": self.high,
            "Low": self.low,
            "Close": self.close,
            "Volume": self.volume,
        }


class MarketDataAdapter(ABC):
    """Abstract base class for market data adapters.

    Implementations must provide:
    - WebSocket connection for real-time data
    - REST API backfill for historical data
    - Symbol conversion between canonical and venue formats

    The adapter handles reconnection with exponential backoff and
    provides normalized Candle objects to registered handlers.
    """

    def __init__(self, venue: str) -> None:
        """Initialize adapter with venue identifier.

        Args:
            venue: Venue identifier (e.g., "binance", "kraken")
        """
        self.venue = venue
        self._candle_handlers: list[Callable[[Candle], None]] = []

    def on_candle(self, handler: Callable[[Candle], None]) -> None:
        """Register a handler for closed candle events.

        Handlers are called synchronously when a closed candle is received
        from the WebSocket stream. Handlers should not block.

        Args:
            handler: Callable that receives a Candle object
        """
        self._candle_handlers.append(handler)

    def _emit_candle(self, candle: Candle) -> None:
        """Emit candle to all registered handlers.

        Iterates through all registered handlers and calls them with
        the candle. Exceptions in individual handlers are caught and
        logged but do not stop other handlers from receiving the candle.

        Args:
            candle: The normalized candle to emit
        """
        for handler in self._candle_handlers:
            with contextlib.suppress(Exception):
                handler(candle)

    @abstractmethod
    async def connect(self, symbols: list[Symbol]) -> None:
        """Connect to WebSocket stream for given symbols.

        Establishes a WebSocket connection to the exchange's streaming API
        for the specified symbols. Should handle connection errors and
        implement reconnection logic.

        Args:
            symbols: List of canonical symbols to subscribe to

        Raises:
            ConnectionError: If connection cannot be established
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean disconnect from stream.

        Closes the WebSocket connection and releases resources.
        Should be called when shutting down or switching symbols.
        """
        raise NotImplementedError

    @abstractmethod
    async def backfill(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Backfill historical data via REST API.

        Fetches historical candles from the exchange's REST API for
        the specified time range. Used for:
        - Initial data loading on startup
        - Gap repair after disconnections
        - Historical analysis

        Args:
            symbol: Canonical symbol to fetch data for
            start: Start time (inclusive)
            end: End time (inclusive)

        Returns:
            List of normalized candles in chronological order

        Raises:
            ValueError: If symbol is not supported
            ConnectionError: If REST API request fails
        """
        raise NotImplementedError
