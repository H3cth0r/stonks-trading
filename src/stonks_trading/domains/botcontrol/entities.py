"""Domain entities for bot control domain.

Entities are pure dataclasses with zero framework dependencies.
They represent bot process lifecycle and status information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ProcessStatus(str, Enum):
    """Process status enum for bot lifecycle.

    - REGISTERED: Bot registered but never started
    - STARTING: Start command issued, process spawning
    - RUNNING: Process confirmed running
    - STOPPING: Stop command issued
    - STOPPED: Process stopped gracefully
    - ERROR: Process crashed or failed to start
    - UNKNOWN: Cannot determine status
    """

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class BotProcess:
    """Represents a running or stopped bot process.

    Tracks the lifecycle of a bot instance from registration
    through running to stopped state.
    """

    bot_type: str
    bot_instance_id: str
    mode: str
    symbols: list[str] = field(default_factory=list)
    pid: int | None = None  # OS process ID
    status: ProcessStatus = ProcessStatus.REGISTERED
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    exit_code: int | None = None
    error_message: str | None = None
    config_path: str = "config-neat.txt"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def uptime_seconds(self) -> int | None:
        """Calculate uptime in seconds if bot is running."""
        if self.started_at is None:
            return None

        # Handle timezone-aware vs naive datetime comparison

        now = datetime.now(UTC)
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)

        if self.stopped_at is not None:
            stopped = self.stopped_at
            if stopped.tzinfo is None:
                stopped = stopped.replace(tzinfo=UTC)
            return int((stopped - started).total_seconds())
        return int((now - started).total_seconds())

    @property
    def is_running(self) -> bool:
        """Check if bot process is currently running."""
        return self.status == ProcessStatus.RUNNING

    @property
    def context_key(self) -> str:
        """Return unique context key for this bot."""
        return f"{self.bot_type}/{self.bot_instance_id}"


@dataclass
class BotStatus:
    """Status response for API consumers.

    Aggregated view of bot status combining process information
    with runtime state and trading data.
    """

    bot_type: str
    bot_instance_id: str
    status: ProcessStatus
    mode: str
    uptime_seconds: int | None = None
    last_trade_at: datetime | None = None
    current_equity: float | None = None
    position_count: int = 0
    pid: int | None = None
    message: str | None = None
    last_seen: datetime | None = None

    @property
    def is_healthy(self) -> bool:
        """Check if bot is in a healthy state."""
        return self.status == ProcessStatus.RUNNING

    @property
    def status_display(self) -> str:
        """Return human-readable status."""
        return self.status.value
