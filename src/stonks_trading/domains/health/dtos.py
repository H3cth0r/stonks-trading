"""Pydantic DTOs for health monitoring domain.

Request and response models for API layer.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class HeartbeatRequest(BaseModel):
    """Request to record a bot heartbeat."""

    bot_type: str = Field(..., description="Bot type (e.g., 'neat_swing')")
    bot_instance_id: str = Field(..., description="Bot instance ID")
    state_hash: str | None = Field(None, description="Hash of bot state for integrity")
    candle_timestamp: datetime | None = Field(
        None, description="Timestamp of last processed candle"
    )


class HeartbeatResponse(BaseModel):
    """Response after recording a heartbeat."""

    id: int
    bot_type: str
    bot_instance_id: str
    timestamp: datetime
    state_hash: str | None = None
    candle_timestamp: datetime | None = None


class BotHealthResponse(BaseModel):
    """Health status for a single bot."""

    bot_type: str
    bot_instance_id: str
    mode: str
    status: str  # healthy, degraded, unhealthy, unknown
    last_heartbeat_at: datetime | None = None
    trade_lag_seconds: float | None = None
    last_trade_at: datetime | None = None
    position_count: int = 0
    current_drawdown: float = 0.0
    error_count_1h: int = 0
    message: str | None = None
    uptime_seconds: int | None = None


class SystemHealthResponse(BaseModel):
    """System-wide health response."""

    status: str  # healthy, degraded, unhealthy
    api_healthy: bool
    database_healthy: bool
    duckdb_healthy: bool
    bots: list[BotHealthResponse]
    checked_at: datetime
    message: str | None = None
    version: str = "0.1.0"  # API version


class HealthCheckResponse(BaseModel):
    """Simple health check for load balancers."""

    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BotHealthListResponse(BaseModel):
    """List of bot health statuses."""

    bots: list[BotHealthResponse]
    total: int
    healthy_count: int
    degraded_count: int
    unhealthy_count: int


class StaleBotsResponse(BaseModel):
    """Response for stale bot detection."""

    stale_bots: list[BotHealthResponse]
    count: int
    threshold_minutes: int


class HealthHistoryRequest(BaseModel):
    """Request parameters for health history."""

    hours: int = Field(default=24, ge=1, le=168, description="Hours of history to retrieve")


class HealthHistoryResponse(BaseModel):
    """Response for health history query."""

    heartbeats: list[HeartbeatResponse]
    count: int
    bot_type: str | None = None
    bot_instance_id: str | None = None
