"""Pydantic DTOs for reconciliation domain.

Request and response models for API layer.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReconciliationRunRequest(BaseModel):
    """Request to run reconciliation.

    Triggers a new reconciliation between internal trades
    and exchange venue statements.
    """

    venue: str = Field(default="binance", description="Exchange venue (e.g., binance)")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    start_time: datetime = Field(..., description="Start of reconciliation window")
    end_time: datetime = Field(..., description="End of reconciliation window")
    alert_threshold: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Alert if issues exceed this threshold",
    )


class ReconciliationDiffResponse(BaseModel):
    """Single reconciliation difference in response."""

    status: str = Field(..., description="matched, mismatch, missing_internal, missing_venue")
    internal_trade_id: int | None = None
    venue_trade_id: str | None = None
    field_differences: dict[str, tuple[Any, Any]] = Field(default_factory=dict)
    symbol: str | None = None
    side: str | None = None
    internal_price: float | None = None
    venue_price: float | None = None
    internal_quantity: float | None = None
    venue_quantity: float | None = None
    internal_timestamp: datetime | None = None
    venue_timestamp: datetime | None = None


class ReconciliationRunResponse(BaseModel):
    """Response after running reconciliation."""

    run_id: str
    venue: str
    symbol: str
    start_time: datetime
    end_time: datetime
    status: str = Field(..., description="complete or error")
    total_internal: int = 0
    total_venue: int = 0
    matched: int = 0
    mismatches: int = 0
    missing_internal: int = 0
    missing_venue: int = 0
    is_clean: bool = Field(..., description="True if no issues found")
    created_at: datetime
    message: str | None = None


class ReconciliationReportResponse(BaseModel):
    """Full reconciliation report with diffs."""

    run_id: str
    venue: str
    symbol: str
    start_time: datetime
    end_time: datetime
    total_internal: int
    total_venue: int
    matched: int
    mismatches: int
    missing_internal: int
    missing_venue: int
    total_issues: int
    match_rate: float = Field(..., description="Percentage of matched trades")
    is_clean: bool
    created_at: datetime
    diffs: list[ReconciliationDiffResponse] = Field(default_factory=list)


class ReconciliationReportSummary(BaseModel):
    """Summary of a reconciliation report (for list view)."""

    run_id: str
    venue: str
    symbol: str
    start_time: datetime
    end_time: datetime
    total_internal: int
    total_venue: int
    matched: int
    mismatches: int
    missing_internal: int
    missing_venue: int
    is_clean: bool
    created_at: datetime


class ReconciliationReportListResponse(BaseModel):
    """List of reconciliation reports."""

    reports: list[ReconciliationReportSummary]
    total: int
    limit: int
    offset: int


class ReconciliationThresholdConfig(BaseModel):
    """Configuration for reconciliation tolerance thresholds."""

    price_tolerance_pct: float = Field(
        default=0.01,
        description="Price tolerance in percent (0.01 = 0.01%)",
    )
    quantity_tolerance: float = Field(
        default=0.0001,
        description="Absolute quantity tolerance",
    )
    time_tolerance_seconds: float = Field(
        default=60.0,
        description="Timestamp tolerance in seconds",
    )


class VenueStatementResponse(BaseModel):
    """Venue statement in API response."""

    venue_trade_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    fee_currency: str
    timestamp: datetime
    venue: str
    order_id: str | None = None


class ReconciliationErrorResponse(BaseModel):
    """Error response for reconciliation failures."""

    error: str
    run_id: str | None = None
    message: str | None = None
