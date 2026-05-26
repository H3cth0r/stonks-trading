"""Domain entities for reconciliation domain.

Entities are pure dataclasses with zero framework dependencies.
They represent trade reconciliation between internal records
and exchange venue statements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ReconciliationStatus(str, Enum):
    """Status of a reconciliation comparison.

    - PENDING: Reconciliation not yet processed
    - MATCHED: Internal and venue trades match within tolerance
    - MISMATCH: Trades match but fields differ beyond tolerance
    - MISSING_INTERNAL: Trade exists in venue but not in internal records
    - MISSING_VENUE: Trade exists internally but not in venue records
    """

    PENDING = "pending"
    MATCHED = "matched"
    MISMATCH = "mismatch"
    MISSING_INTERNAL = "missing_internal"
    MISSING_VENUE = "missing_venue"


@dataclass
class VenueStatement:
    """Trade record from exchange venue (e.g., Binance myTrades).

    Represents a single trade execution as reported by the exchange.
    Used for reconciliation against internal trade records.
    """

    venue_trade_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    fee_currency: str
    timestamp: datetime
    venue: str
    # Optional fields from exchange
    order_id: str | None = None
    commission: float | None = None
    commission_asset: str | None = None
    is_maker: bool | None = None


@dataclass
class ReconciliationDiff:
    """Difference found during reconciliation.

    Represents a single comparison between internal trade
    and venue statement, including field-level differences.
    """

    status: ReconciliationStatus
    internal_trade_id: int | None = None
    venue_trade_id: str | None = None
    field_differences: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    # Additional context for display/debugging
    symbol: str | None = None
    side: str | None = None
    internal_price: float | None = None
    venue_price: float | None = None
    internal_quantity: float | None = None
    venue_quantity: float | None = None
    internal_timestamp: datetime | None = None
    venue_timestamp: datetime | None = None


@dataclass
class ReconciliationReport:
    """Summary of a reconciliation run.

    Aggregates results from comparing internal trades
    against venue statements for a specific time period.
    """

    run_id: str
    venue: str
    symbol: str
    start_time: datetime
    end_time: datetime
    total_internal: int = 0
    total_venue: int = 0
    matched: int = 0
    mismatches: int = 0
    missing_internal: int = 0
    missing_venue: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    diffs: list[ReconciliationDiff] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Check if reconciliation found no issues."""
        return self.mismatches == 0 and self.missing_internal == 0 and self.missing_venue == 0

    @property
    def total_issues(self) -> int:
        """Total number of reconciliation issues found."""
        return self.mismatches + self.missing_internal + self.missing_venue

    @property
    def match_rate(self) -> float:
        """Percentage of trades that matched successfully."""
        total = self.total_internal + self.total_venue
        if total == 0:
            return 100.0
        return (self.matched * 2) / total * 100


@dataclass
class ReconciliationThresholds:
    """Tolerance thresholds for matching trades.

    Defines acceptable differences between internal and venue records.
    """

    price_tolerance_pct: float = 0.01  # 0.01% = 0.0001
    quantity_tolerance: float = 0.0001  # Absolute quantity difference
    time_tolerance_seconds: float = 60.0  # 60 seconds

    def is_price_match(self, internal: float, venue: float) -> bool:
        """Check if prices match within tolerance."""
        if internal == 0 and venue == 0:
            return True
        if internal == 0 or venue == 0:
            return False
        diff_pct = abs(internal - venue) / ((internal + venue) / 2)
        return diff_pct <= self.price_tolerance_pct / 100

    def is_quantity_match(self, internal: float, venue: float) -> bool:
        """Check if quantities match within tolerance."""
        return abs(internal - venue) <= self.quantity_tolerance

    def is_time_match(self, internal: datetime, venue: datetime) -> bool:
        """Check if timestamps match within tolerance."""
        diff_seconds = abs((internal - venue).total_seconds())
        return diff_seconds <= self.time_tolerance_seconds
