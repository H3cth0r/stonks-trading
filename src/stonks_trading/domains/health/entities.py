"""Domain entities for health monitoring domain.

Entities are pure dataclasses with zero framework dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    """Health status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class BotHeartbeat:
    """Bot heartbeat entity for health tracking.

    Records periodic heartbeats from running bots with state hash
    for integrity verification and candle timestamp for trade lag detection.
    """

    bot_type: str
    bot_instance_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
    state_hash: str | None = None
    candle_timestamp: datetime | None = None


@dataclass
class BotHealth:
    """Bot health snapshot for dashboard and monitoring.

    Aggregated view of a bot's current health status including
    heartbeat age, trade lag, positions, and errors.
    """

    bot_type: str
    bot_instance_id: str
    mode: str
    status: HealthStatus
    last_heartbeat_at: datetime | None = None
    trade_lag_seconds: float | None = None
    last_trade_at: datetime | None = None
    position_count: int = 0
    current_drawdown: float = 0.0
    error_count_1h: int = 0
    message: str | None = None
    uptime_seconds: int | None = None


@dataclass
class SystemHealth:
    """System-wide health status.

    Aggregated health across all infrastructure components
    and registered bots.
    """

    status: HealthStatus
    api_healthy: bool
    database_healthy: bool
    duckdb_healthy: bool
    bots: list[BotHealth] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)
    message: str | None = None
