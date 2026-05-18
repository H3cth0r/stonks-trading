"""Data Transfer Objects (DTOs) for trading domain API.

Pydantic models for API request/response validation.
All responses inherit from BaseResponse.
"""

from datetime import datetime

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
