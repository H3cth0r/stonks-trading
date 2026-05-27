"""Data Transfer Objects (DTOs) for trading domain API.

Pydantic models for API request/response validation.
All responses inherit from BaseResponse.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from stonks_trading.domains.trading.enums import Side
from stonks_trading.shared.serializers import BaseResponse

# =============================================================================
# Trade DTOs
# =============================================================================


class TradeCreateRequest(BaseModel):
    """API request payload for trade creation with validation."""

    symbol: str = Field(..., min_length=1, max_length=20)
    side: Side = Field(...)
    quantity: float = Field(..., gt=0)
    price: float | None = Field(default=None, gt=0)
    order_type: str = Field(default="market", pattern="^(market|limit)$")


class TradeResponse(BaseResponse):
    """API response DTO for trade (flat fields, not nested entity)."""

    id: int
    symbol: str
    side: str
    fill_price: float
    quantity: float
    fee: float
    created_at: datetime
    order_id: str | None = None


class TradeListResponse(BaseResponse):
    """List of trades response."""

    trades: list[TradeResponse] = Field(default_factory=list)
    total: int = 0


# =============================================================================
# Position DTOs
# =============================================================================


class PositionResponse(BaseResponse):
    """API response DTO for position."""

    id: int
    symbol: str
    quantity: float
    entry_price: float | None = None
    unrealized_pnl_pct: float = 0.0
    market_value: float = 0.0
    updated_at: datetime


class PositionListResponse(BaseResponse):
    """List of positions response."""

    positions: list[PositionResponse] = Field(default_factory=list)


# =============================================================================
# Genome DTOs
# =============================================================================


class GenomeCreateRequest(BaseModel):
    """Request to create/save a genome."""

    symbol: str
    fitness: float
    generation: int = 0
    fee_rate: float = Field(default=0.001, ge=0, le=0.01)
    slippage_bps: int = Field(default=0, ge=0, le=100)
    mode: str = Field(default="backtest", pattern="^(backtest|dry_run|live)$")


class GenomeResponse(BaseResponse):
    """API response DTO for genome."""

    id: int
    symbol: str | None = None
    fitness: float
    generation: int
    fee_rate: float
    slippage_bps: int
    mode: str
    is_active: bool
    created_at: datetime


class GenomeListResponse(BaseResponse):
    """List of genomes response."""

    genomes: list[GenomeResponse] = Field(default_factory=list)
    total: int = 0


class GenomeActivateRequest(BaseModel):
    """Request to activate a genome."""

    genome_id: int


# =============================================================================
# Risk Event DTOs
# =============================================================================


class RiskEventResponse(BaseResponse):
    """API response DTO for risk event."""

    id: int
    event_type: str
    severity: str
    message: str
    symbol: str | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    threshold_value: float | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None


class RiskEventListResponse(BaseResponse):
    """List of risk events response."""

    events: list[RiskEventResponse] = Field(default_factory=list)
    total: int = 0


class RiskEventAcknowledgeRequest(BaseModel):
    """Request to acknowledge a risk event."""

    user: str = Field(..., min_length=1)
    action: str | None = None


# =============================================================================
# Market Data DTOs
# =============================================================================


class MarketDataResponse(BaseResponse):
    """API response DTO for market data."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataListResponse(BaseResponse):
    """List of market data candles."""

    candles: list[MarketDataResponse] = Field(default_factory=list)
    symbol: str


class PriceResponse(BaseResponse):
    """Current price response."""

    symbol: str
    price: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Balance/Portfolio DTOs
# =============================================================================


class BalanceItem(BaseModel):
    """Single balance item."""

    asset: str
    free: float
    locked: float
    total: float


class BalanceResponse(BaseResponse):
    """Account balance response."""

    balances: list[BalanceItem] = Field(default_factory=list)


class PortfolioResponse(BaseResponse):
    """Portfolio summary response."""

    total_value: float
    cash_value: float
    positions_value: float
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    positions: list[PositionResponse] = Field(default_factory=list)


# =============================================================================
# NEAT Signal DTOs
# =============================================================================


class NeatSignalRequest(BaseModel):
    """Request to evaluate NEAT signal."""

    buy_prob: float = Field(..., ge=0.0, le=1.0)
    sell_prob: float = Field(..., ge=0.0, le=1.0)
    current_price: float = Field(..., gt=0)
    portfolio_value: float | None = None


class NeatSignalResponse(BaseResponse):
    """NEAT signal evaluation response."""

    action: str | None = None  # "buy", "sell", or null
    confidence: float
    should_trade: bool
    reason: str | None = None


# =============================================================================
# Error DTOs
# =============================================================================


class ValidationError(BaseModel):
    """Single validation error."""

    field: str
    message: str


class ValidationErrorResponse(BaseResponse):
    """Validation error response with field details."""

    success: bool = False
    error_code: str = "VALIDATION_ERROR"
    errors: list[ValidationError] = Field(default_factory=list)


# =============================================================================
# Bot DTOs (Phase 5)
# =============================================================================


class BotRegisterRequest(BaseModel):
    """Request to register a new bot instance."""

    bot_type: str = Field(..., min_length=1, max_length=50)
    instance_id: str = Field(..., min_length=1, max_length=100)
    symbols: list[str] = Field(default_factory=list)
    mode: str = Field(default="dry_run", pattern="^(backtest|dry_run|live)$")
    config: dict[str, Any] | None = None


class BotInstanceResponse(BaseResponse):
    """API response DTO for bot instance."""

    id: int
    bot_type: str
    instance_id: str
    symbols: list[str]
    mode: str
    status: str
    created_at: datetime
    last_seen_at: datetime | None = None


class BotStateResponse(BaseResponse):
    """API response DTO for bot state."""

    bot_type: str
    instance_id: str
    status: str
    state: dict[str, Any]


class BotListResponse(BaseResponse):
    """List of bot instances response."""

    bots: list[BotInstanceResponse] = Field(default_factory=list)
    total: int = 0


class BotInstanceListResponse(BaseResponse):
    """List of bot instances for a specific type."""

    instances: list[BotInstanceResponse] = Field(default_factory=list)
    total: int = 0


# =============================================================================
# Activity DTOs (Phase 6)
# =============================================================================


class ActivityItemResponse(BaseResponse):
    """Single activity item (trade, order, risk event, etc.)."""

    id: int
    type: str  # "trade", "order", "risk_event", "training", "genome_activation"
    timestamp: datetime
    symbol: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    bot_type: str | None = None
    bot_instance_id: str | None = None


class ActivityListResponse(BaseResponse):
    """List of activity items with cursor pagination."""

    activities: list[ActivityItemResponse] = Field(default_factory=list)
    cursor: str | None = None
    total: int = 0


# =============================================================================
# Order DTOs (Phase 6)
# =============================================================================


class OrderResponse(BaseResponse):
    """API response DTO for order lifecycle."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    status: str  # pending, open, filled, cancelled, failed
    quantity: float
    filled_quantity: float = 0.0
    price: float | None = None
    fill_price: float | None = None
    created_at: datetime
    updated_at: datetime
    bot_type: str
    bot_instance_id: str


class OrderListResponse(BaseResponse):
    """List of orders response."""

    orders: list[OrderResponse] = Field(default_factory=list)
    total: int = 0


# =============================================================================
# Venue Balance DTOs (Phase 6)
# =============================================================================


class VenueBalanceItemResponse(BaseResponse):
    """Single venue balance item."""

    asset: str
    free: float
    locked: float
    total: float


class VenueBalanceResponse(BaseResponse):
    """Venue balance response with sync metadata."""

    venue: str
    balances: list[VenueBalanceItemResponse] = Field(default_factory=list)
    synced_at: datetime


class VenueBalanceListResponse(BaseResponse):
    """List of venue balances."""

    venues: list[VenueBalanceResponse] = Field(default_factory=list)


# =============================================================================
# Market Price DTOs (Phase 6)
# =============================================================================


class MarketPriceResponse(BaseResponse):
    """Market price for a symbol."""

    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume_24h: float | None = None
    timestamp: datetime


class MarketPriceListResponse(BaseResponse):
    """List of market prices."""

    prices: list[MarketPriceResponse] = Field(default_factory=list)


# =============================================================================
# Training DTOs (Phase 6)
# =============================================================================


class TrainingRunResponse(BaseResponse):
    """Training run metadata response."""

    id: int
    symbol: str
    status: str  # running, completed, failed, pending
    started_at: datetime
    finished_at: datetime | None = None
    best_fitness: float | None = None
    best_validation_roi: float | None = None
    generations_completed: int = 0
    git_sha: str
    config: dict[str, Any] = Field(default_factory=dict)
    bot_type: str
    bot_instance_id: str


class TrainingRunListResponse(BaseResponse):
    """List of training runs."""

    runs: list[TrainingRunResponse] = Field(default_factory=list)
    total: int = 0


class CheckpointResponse(BaseResponse):
    """Training checkpoint response."""

    generation: int
    artifact_uri: str
    size_bytes: int
    created_at: datetime
    fitness: float | None = None


class CheckpointListResponse(BaseResponse):
    """List of training checkpoints."""

    checkpoints: list[CheckpointResponse] = Field(default_factory=list)
    total: int = 0


# =============================================================================
# Genome Admin DTOs (Phase 6)
# =============================================================================


class GenomeImportRequest(BaseModel):
    """Request to import a staged genome (admin only)."""

    model_family: str = Field(..., min_length=1)
    feature_schema_id: str = Field(..., min_length=1)
    trainer_git_sha: str = Field(..., min_length=1)
    bot_type: str = Field(..., min_length=1)
    bot_instance_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    artifact_uri: str = Field(..., min_length=1)
    checksum: str = Field(..., min_length=1)
    config: dict[str, Any] | None = None


class GenomePruneRequest(BaseModel):
    """Request to prune old genomes (admin only)."""

    retention_days: int = Field(default=30, ge=1, le=365)
    keep_active: bool = True
    dry_run: bool = True


class GenomePruneResponse(BaseResponse):
    """Response from genome prune operation."""

    pruned_count: int
    kept_count: int
    pruned_ids: list[int] = Field(default_factory=list)


# =============================================================================
# Backfill DTOs (Phase 10B)
# =============================================================================


class BackfillMassiveRequest(BaseModel):
    """Request to start a Massive backfill job."""

    symbol: str = Field(..., min_length=1, examples=["BTC_USD"])
    days: int = Field(default=730, ge=1, le=730)


class BackfillMassiveResponse(BaseResponse):
    """Response when starting a Massive backfill job."""

    job_id: str
    symbol: str
    days: int
    estimated_chunks: int
    estimated_duration_minutes: int


class JobStatusResponse(BaseResponse):
    """Job status response for backfill operations."""

    job_id: str
    status: str  # "running", "completed", "failed"
    progress: float = 0.0
    total_chunks: int | None = None
    candles_downloaded: int | None = None
    error: str | None = None
