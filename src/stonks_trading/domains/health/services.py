"""Service classes for health monitoring domain.

Pure business logic, no I/O operations.
All methods are deterministic and testable.
"""

from datetime import datetime

from stonks_trading.domains.health.entities import BotHealth, HealthStatus


class HealthStatusCalculator:
    """Calculate health status based on bot metrics.

    Business Rules:
    - UNHEALTHY if last_heartbeat > 5 minutes ago
    - UNHEALTHY if trade_lag > 10 minutes
    - DEGRADED if error_count_1h > 5
    - HEALTHY otherwise
    """

    HEARTBEAT_THRESHOLD_SECONDS = 300  # 5 minutes
    TRADE_LAG_THRESHOLD_SECONDS = 600  # 10 minutes
    ERROR_THRESHOLD_1H = 5

    @classmethod
    def calculate(
        cls,
        last_heartbeat_at: datetime | None,
        trade_lag_seconds: float | None,
        error_count_1h: int,
    ) -> HealthStatus:
        """Calculate health status based on metrics."""
        # UNHEALTHY checks first (highest priority)
        if last_heartbeat_at is None:
            return HealthStatus.UNHEALTHY

        now = datetime.utcnow()
        heartbeat_age_seconds = (now - last_heartbeat_at).total_seconds()

        if heartbeat_age_seconds > cls.HEARTBEAT_THRESHOLD_SECONDS:
            return HealthStatus.UNHEALTHY

        if trade_lag_seconds is not None and trade_lag_seconds > cls.TRADE_LAG_THRESHOLD_SECONDS:
            return HealthStatus.UNHEALTHY

        # DEGRADED checks
        if error_count_1h > cls.ERROR_THRESHOLD_1H:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    @classmethod
    def get_message(
        cls,
        status: HealthStatus,
        heartbeat_age_seconds: float | None,
        trade_lag_seconds: float | None,
        error_count_1h: int,
    ) -> str | None:
        """Get human-readable message for health status."""
        if status == HealthStatus.HEALTHY:
            return None

        messages = []

        if (
            heartbeat_age_seconds is not None
            and heartbeat_age_seconds > cls.HEARTBEAT_THRESHOLD_SECONDS
        ):
            minutes = int(heartbeat_age_seconds / 60)
            messages.append(f"Last heartbeat {minutes}m ago")

        if trade_lag_seconds is not None and trade_lag_seconds > cls.TRADE_LAG_THRESHOLD_SECONDS:
            minutes = int(trade_lag_seconds / 60)
            messages.append(f"Trade lag {minutes}m")

        if error_count_1h > cls.ERROR_THRESHOLD_1H:
            messages.append(f"{error_count_1h} errors in last hour")

        return "; ".join(messages) if messages else None


class TradeLagCalculator:
    """Calculate trade lag based on last candle timestamp."""

    @staticmethod
    def calculate(last_candle_at: datetime | None) -> float | None:
        """Calculate seconds since last candle.

        Returns None if no candle timestamp available.
        """
        if last_candle_at is None:
            return None

        now = datetime.utcnow()
        lag_seconds = (now - last_candle_at).total_seconds()
        return max(0.0, lag_seconds)


class BotHealthAssembler:
    """Assemble complete BotHealth from partial data."""

    @classmethod
    def assemble(
        cls,
        base_health: BotHealth,
        last_candle_at: datetime | None,
    ) -> BotHealth:
        """Assemble complete health with calculated fields."""
        # Calculate trade lag
        trade_lag_seconds = TradeLagCalculator.calculate(last_candle_at)

        # Calculate health status
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=base_health.last_heartbeat_at,
            trade_lag_seconds=trade_lag_seconds,
            error_count_1h=base_health.error_count_1h,
        )

        # Calculate heartbeat age for message
        heartbeat_age_seconds = None
        if base_health.last_heartbeat_at is not None:
            heartbeat_age_seconds = (
                datetime.utcnow() - base_health.last_heartbeat_at
            ).total_seconds()

        # Get status message
        message = HealthStatusCalculator.get_message(
            status=status,
            heartbeat_age_seconds=heartbeat_age_seconds,
            trade_lag_seconds=trade_lag_seconds,
            error_count_1h=base_health.error_count_1h,
        )

        return BotHealth(
            bot_type=base_health.bot_type,
            bot_instance_id=base_health.bot_instance_id,
            mode=base_health.mode,
            status=status,
            last_heartbeat_at=base_health.last_heartbeat_at,
            trade_lag_seconds=trade_lag_seconds,
            last_trade_at=base_health.last_trade_at,
            position_count=base_health.position_count,
            current_drawdown=base_health.current_drawdown,
            error_count_1h=base_health.error_count_1h,
            message=message,
        )


class SystemHealthCalculator:
    """Calculate overall system health from component health."""

    @staticmethod
    def calculate(
        api_healthy: bool,
        database_healthy: bool,
        duckdb_healthy: bool,
        bot_healths: list[BotHealth],
    ) -> HealthStatus:
        """Calculate system-wide health status."""
        # System is unhealthy if core components fail
        if not api_healthy or not database_healthy:
            return HealthStatus.UNHEALTHY

        # Count bot statuses
        unhealthy_count = sum(1 for b in bot_healths if b.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for b in bot_healths if b.status == HealthStatus.DEGRADED)

        # If any bot is unhealthy, system is degraded
        if unhealthy_count > 0:
            return HealthStatus.DEGRADED

        # If multiple bots are degraded, system is degraded
        if degraded_count > 1:
            return HealthStatus.DEGRADED

        # DuckDB issues cause degraded status
        if not duckdb_healthy:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY
