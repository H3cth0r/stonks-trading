"""Pydantic DTOs for instrument registry API.

API layer - FastAPI imports OK here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstrumentRequest(BaseModel):
    """Request to register a new instrument."""

    symbol: str = Field(..., description="Trading symbol (e.g., 'BTC_USD')")
    name: str = Field(default="", description="Human-readable name")
    auto_backfill: bool = Field(default=True, description="Auto-backfill 2 years of data")
    backfill_days: int = Field(default=730, ge=1, le=3650, description="Days to backfill")


class InstrumentUpdateRequest(BaseModel):
    """Request to update instrument metadata."""

    name: str | None = Field(default=None, description="Human-readable name")
    auto_backfill: bool | None = Field(default=None, description="Auto-backfill on registration")
    backfill_days: int | None = Field(default=None, ge=1, le=3650, description="Days to backfill")


class InstrumentResponse(BaseModel):
    """Response for a single instrument."""

    symbol: str
    name: str
    enabled: bool
    auto_backfill: bool
    backfill_days: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_backfill_at: datetime | None = None
    backfill_job_id: str | None = None


class InstrumentListResponse(BaseModel):
    """Response for listing instruments."""

    instruments: list[InstrumentResponse]
    total: int


class InstrumentStatusResponse(BaseModel):
    """Response for instrument status including backfill progress."""

    symbol: str
    status: str
    enabled: bool
    backfill_job_id: str | None = None
    backfill_progress: float | None = None
    backfill_status: str | None = None
    backfill_candles: int | None = None
