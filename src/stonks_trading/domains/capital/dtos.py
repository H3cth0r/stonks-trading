"""Pydantic DTOs for capital management domain.

Request and response models for API layer.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreateCapitalPoolRequest(BaseModel):
    """Request to create a new capital pool."""

    pool_id: str = Field(..., description="Unique pool identifier (e.g., 'main', 'hedge')")
    name: str = Field(..., description="Human-readable pool name", min_length=1, max_length=100)
    initial_capital: float = Field(..., description="Initial capital amount", ge=0)
    currency: str = Field(default="USDT", description="Currency code", min_length=3, max_length=10)
    min_allocation: float = Field(default=100.0, description="Minimum allocation per bot")
    rebalance_threshold_pct: float = Field(
        default=5.0, description="Rebalance threshold percentage", ge=0, le=100
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        """Normalize currency to uppercase."""
        return v.upper()


class CapitalPoolResponse(BaseModel):
    """Response for capital pool operations."""

    id: int | None = None
    pool_id: str
    name: str
    total_capital: float
    available_capital: float
    reserved_capital: float
    currency: str
    min_allocation: float
    rebalance_threshold_pct: float
    is_active: bool = True
    utilization_pct: float
    created_at: datetime
    updated_at: datetime


class CapitalPoolsListResponse(BaseModel):
    """Response for listing capital pools."""

    pools: list[CapitalPoolResponse]
    total: int
    total_capital: float


class AllocateCapitalRequest(BaseModel):
    """Request to allocate capital to a bot."""

    amount: float = Field(..., description="Amount to allocate", ge=0)
    currency: str = Field(default="USDT", description="Currency code")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Validate positive amount."""
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        """Normalize currency to uppercase."""
        return v.upper()


class AllocateCapitalResponse(BaseModel):
    """Response for capital allocation."""

    bot_type: str
    bot_instance_id: str
    pool_id: str
    allocated_amount: float
    currency: str
    current_value: float | None = None
    roi_pct: float | None = None
    status: str = "active"
    created_at: datetime


class DeallocateCapitalRequest(BaseModel):
    """Request to deallocate capital from a bot."""

    pass  # No body needed, bot identified by path params


class DeallocateCapitalResponse(BaseModel):
    """Response for capital deallocation."""

    bot_type: str
    bot_instance_id: str
    pool_id: str
    deallocated_amount: float
    currency: str
    success: bool
    message: str


class CapitalAllocationResponse(BaseModel):
    """Response for capital allocation queries."""

    bot_type: str
    bot_instance_id: str
    pool_id: str
    allocated_amount: float
    current_value: float | None = None
    unrealized_pnl: float | None = None
    roi_pct: float | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CapitalAllocationListResponse(BaseModel):
    """Response for listing capital allocations."""

    allocations: list[CapitalAllocationResponse]
    total: int


class RebalanceTarget(BaseModel):
    """Single rebalance target."""

    bot_type: str = Field(..., description="Bot type identifier")
    instance_id: str = Field(..., description="Bot instance identifier")
    target_pct: float = Field(..., description="Target percentage of pool capital", ge=0, le=100)


class RebalanceRequest(BaseModel):
    """Request to rebalance capital across bots."""

    rebalance_targets: list[RebalanceTarget] = Field(
        ..., description="List of bots and target percentages"
    )

    @field_validator("rebalance_targets")
    @classmethod
    def validate_targets(cls, v: list[RebalanceTarget]) -> list[RebalanceTarget]:
        """Validate rebalance targets."""
        if not v:
            raise ValueError("At least one rebalance target required")
        total_pct = sum(t.target_pct for t in v)
        if abs(total_pct - 100.0) > 0.01:
            raise ValueError(f"Target percentages must sum to 100, got {total_pct}")
        return v


class RebalanceResponse(BaseModel):
    """Response for rebalance operations."""

    pool_id: str
    total_rebalanced: int
    allocations: list[CapitalAllocationResponse]
    message: str


class ErrorResponse(BaseModel):
    """Error response for failed operations."""

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Optional error code")
