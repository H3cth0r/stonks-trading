"""Instrument domain entities.

Pure dataclasses with zero framework dependencies.
Includes both Instrument registry entities AND market data entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# =============================================================================
# Market Data Entities (moved from market_data domain)
# =============================================================================


@dataclass
class Candle:
    """OHLCV candle data.

    Immutable representation of a single candle/bar.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""

    def get_ohlcv(self) -> tuple[float, float, float, float, float]:
        """Return OHLCV tuple."""
        return (self.open, self.high, self.low, self.close, self.volume)

    def price_range(self) -> float:
        """Calculate price range (high - low)."""
        return self.high - self.low

    def is_bullish(self) -> bool:
        """Check if close > open (bullish candle)."""
        return self.close > self.open

    def is_bearish(self) -> bool:
        """Check if close < open (bearish candle)."""
        return self.close < self.open

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candle:
        """Create from dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            ts = datetime.utcfromtimestamp(ts / 1000 if ts > 1e10 else ts)
        elif isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            timestamp=ts or datetime.utcnow(),
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", 0)),
            volume=float(data.get("volume", 0)),
            symbol=data.get("symbol", ""),
        )


@dataclass
class OrderBook:
    """Order book data for a symbol.

    Snapshot of bid/ask levels.
    """

    symbol: str
    bids: list[tuple[float, float]]  # (price, quantity)
    asks: list[tuple[float, float]]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def best_bid(self) -> tuple[float, float] | None:
        """Get best bid (highest price)."""
        return self.bids[0] if self.bids else None

    def best_ask(self) -> tuple[float, float] | None:
        """Get best ask (lowest price)."""
        return self.asks[0] if self.asks else None

    def spread(self) -> float | None:
        """Calculate bid-ask spread."""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return best_ask[0] - best_bid[0]
        return None

    def mid_price(self) -> float | None:
        """Calculate mid price."""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return (best_bid[0] + best_ask[0]) / 2
        return None


@dataclass
class Tick:
    """Individual trade tick.

    Represents a single trade execution.
    """

    timestamp: datetime
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    trade_id: str | None = None
    symbol: str = ""

    def is_buy(self) -> bool:
        """Check if this was a buy (taker paid ask)."""
        return self.side.lower() == "buy"

    def is_sell(self) -> bool:
        """Check if this was a sell (taker paid bid)."""
        return self.side.lower() == "sell"


@dataclass
class TimeRange:
    """Time range for data queries.

    Immutable value object for time range.
    """

    start: datetime
    end: datetime

    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return (self.end - self.start).total_seconds()

    def duration_hours(self) -> float:
        """Duration in hours."""
        return self.duration_seconds() / 3600

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp is within range."""
        return self.start <= timestamp <= self.end

    def overlaps(self, other: TimeRange) -> bool:
        """Check if another time range overlaps."""
        return self.start < other.end and other.start < self.end


# =============================================================================
# Instrument Registry Entity
# =============================================================================


@dataclass
class Instrument:
    """Trading instrument metadata.

    Represents a registered trading symbol with metadata.
    """

    symbol: str
    name: str = ""
    enabled: bool = False
    auto_backfill: bool = True
    backfill_days: int = 730
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_backfill_at: datetime | None = None
    backfill_job_id: str | None = None
    status: str = "pending"  # pending, backfilling, ready, error

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "enabled": self.enabled,
            "auto_backfill": self.auto_backfill,
            "backfill_days": self.backfill_days,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_backfill_at": self.last_backfill_at.isoformat()
            if self.last_backfill_at
            else None,
            "backfill_job_id": self.backfill_job_id,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instrument:
        """Create from dictionary."""
        return cls(
            symbol=data.get("symbol", ""),
            name=data.get("name", ""),
            enabled=data.get("enabled", False),
            auto_backfill=data.get("auto_backfill", True),
            backfill_days=data.get("backfill_days", 730),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.utcnow(),
            last_backfill_at=datetime.fromisoformat(data["last_backfill_at"])
            if data.get("last_backfill_at")
            else None,
            backfill_job_id=data.get("backfill_job_id"),
            status=data.get("status", "pending"),
        )
