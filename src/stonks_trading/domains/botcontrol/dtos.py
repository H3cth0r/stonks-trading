"""Pydantic DTOs for bot control domain.

Request and response models for API layer.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class StartBotRequest(BaseModel):
    """Request to start a bot instance."""

    symbols: list[str] = Field(
        default=["BTC_USD"], description="Trading symbols (e.g., ['BTC_USD', 'ETH_USD'])"
    )
    mode: str = Field(default="dry_run", description="Trading mode: dry_run or live")
    config_path: str = Field(default="config-neat.txt", description="Path to NEAT config file")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate trading mode."""
        if v not in {"dry_run", "live"}:
            raise ValueError("mode must be 'dry_run' or 'live'")
        return v

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        """Validate symbols list."""
        if not v:
            raise ValueError("At least one symbol required")
        for symbol in v:
            if not symbol or len(symbol) < 3:
                raise ValueError(f"Invalid symbol: {symbol}")
        return [s.upper() for s in v]


class StartBotResponse(BaseModel):
    """Response after starting a bot."""

    bot_type: str = Field(..., description="Bot type identifier")
    bot_instance_id: str = Field(..., description="Bot instance ID")
    status: str = Field(..., description="Process status")
    pid: int | None = Field(None, description="OS process ID")
    started_at: datetime = Field(..., description="Start timestamp")
    message: str | None = Field(None, description="Status message")


class StopBotResponse(BaseModel):
    """Response after stopping a bot."""

    bot_type: str = Field(..., description="Bot type identifier")
    bot_instance_id: str = Field(..., description="Bot instance ID")
    status: str = Field(..., description="Process status")
    stopped_at: datetime = Field(..., description="Stop timestamp")
    uptime_seconds: int | None = Field(None, description="Total uptime in seconds")
    exit_code: int | None = Field(None, description="Process exit code")
    message: str | None = Field(None, description="Status or error message")


class BotStatusResponse(BaseModel):
    """Bot status response for dashboard and API."""

    bot_type: str = Field(..., description="Bot type identifier")
    bot_instance_id: str = Field(..., description="Bot instance ID")
    status: str = Field(..., description="Process status (running, stopped, error, etc.)")
    mode: str = Field(..., description="Trading mode")
    uptime_seconds: int | None = Field(None, description="Uptime in seconds")
    last_seen: datetime | None = Field(None, description="Last seen timestamp")
    current_equity: float | None = Field(None, description="Current equity value")
    position_count: int = Field(0, description="Number of open positions")
    pid: int | None = Field(None, description="OS process ID")
    message: str | None = Field(None, description="Status message")


class RunningBotsResponse(BaseModel):
    """Response for listing running bots."""

    bots: list[BotStatusResponse] = Field(default_factory=list, description="List of running bots")
    total: int = Field(0, description="Total count")


class RestartBotResponse(BaseModel):
    """Response after restarting a bot."""

    bot_type: str = Field(..., description="Bot type identifier")
    bot_instance_id: str = Field(..., description="Bot instance ID")
    status: str = Field(..., description="New process status")
    pid: int | None = Field(None, description="New OS process ID")
    started_at: datetime = Field(..., description="Restart timestamp")
    message: str = Field(default="Bot restarted successfully")


class ErrorResponse(BaseModel):
    """Error response for failed operations."""

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Optional error code")
