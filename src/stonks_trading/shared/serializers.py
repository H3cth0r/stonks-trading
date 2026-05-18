"""Base serializers and shared DTOs for API responses."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel):
    """REQUIRED: Base class for all API responses.

    All response DTOs must inherit from this class to ensure
    consistent API response structure.
    """

    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: str | None = None


class ErrorResponse(BaseResponse):
    """Standard error response format."""

    success: bool = False
    error_code: str = "UNKNOWN_ERROR"
    details: dict[str, Any] | None = None


class PaginatedResponse(BaseResponse, Generic[T]):
    """Paginated response wrapper."""

    data: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 100
    total_pages: int = 0


class HealthResponse(BaseResponse):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
