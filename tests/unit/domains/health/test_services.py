"""Unit tests for health domain services.

Tests business logic in services - pure logic, no I/O.
"""

from datetime import datetime, timedelta

import pytest

from stonks_trading.domains.health.entities import BotHealth, HealthStatus
from stonks_trading.domains.health.services import (
    BotHealthAssembler,
    HealthStatusCalculator,
    SystemHealthCalculator,
    TradeLagCalculator,
)


class TestHealthStatusCalculator:
    """Test HealthStatusCalculator business rules."""

    def test_healthy_when_all_metrics_good(self) -> None:
        """Returns HEALTHY when heartbeat, lag, and errors are all good."""
        now = datetime.utcnow()
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=now,  # Recent heartbeat
            trade_lag_seconds=30.0,  # 30 seconds lag (< 600 threshold)
            error_count_1h=2,  # 2 errors (< 5 threshold)
        )
        assert status == HealthStatus.HEALTHY

    def test_unhealthy_when_no_heartbeat(self) -> None:
        """Returns UNHEALTHY when no heartbeat recorded."""
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=None,
            trade_lag_seconds=None,
            error_count_1h=0,
        )
        assert status == HealthStatus.UNHEALTHY

    def test_unhealthy_when_stale_heartbeat(self) -> None:
        """Returns UNHEALTHY when heartbeat > 5 minutes old."""
        six_minutes_ago = datetime.utcnow() - timedelta(minutes=6)
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=six_minutes_ago,
            trade_lag_seconds=30.0,
            error_count_1h=0,
        )
        assert status == HealthStatus.UNHEALTHY

    def test_unhealthy_when_trade_lag_high(self) -> None:
        """Returns UNHEALTHY when trade lag > 10 minutes."""
        now = datetime.utcnow()
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=now,
            trade_lag_seconds=700.0,  # > 600 threshold
            error_count_1h=0,
        )
        assert status == HealthStatus.UNHEALTHY

    def test_degraded_when_error_count_high(self) -> None:
        """Returns DEGRADED when errors > 5 in last hour."""
        now = datetime.utcnow()
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=now,
            trade_lag_seconds=30.0,
            error_count_1h=10,  # > 5 threshold
        )
        assert status == HealthStatus.DEGRADED

    def test_unhealthy_takes_priority_over_degraded(self) -> None:
        """UNHEALTHY status takes priority over DEGRADED."""
        six_minutes_ago = datetime.utcnow() - timedelta(minutes=6)
        status = HealthStatusCalculator.calculate(
            last_heartbeat_at=six_minutes_ago,  # UNHEALTHY trigger
            trade_lag_seconds=30.0,
            error_count_1h=10,  # DEGRADED trigger
        )
        assert status == HealthStatus.UNHEALTHY

    def test_get_message_returns_none_for_healthy(self) -> None:
        """Message is None for healthy status."""
        msg = HealthStatusCalculator.get_message(
            status=HealthStatus.HEALTHY,
            heartbeat_age_seconds=60.0,
            trade_lag_seconds=30.0,
            error_count_1h=0,
        )
        assert msg is None

    def test_get_message_includes_stale_heartbeat(self) -> None:
        """Message includes stale heartbeat info."""
        msg = HealthStatusCalculator.get_message(
            status=HealthStatus.UNHEALTHY,
            heartbeat_age_seconds=400.0,  # > 300 threshold
            trade_lag_seconds=30.0,
            error_count_1h=0,
        )
        assert msg is not None
        assert "heartbeat" in msg.lower()


class TestTradeLagCalculator:
    """Test TradeLagCalculator."""

    def test_calculate_returns_seconds_since_candle(self) -> None:
        """Returns seconds since last candle timestamp."""
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        lag = TradeLagCalculator.calculate(one_minute_ago)
        assert lag is not None
        assert 55.0 <= lag <= 65.0  # Allow 5 second tolerance

    def test_calculate_returns_none_for_none_input(self) -> None:
        """Returns None when no candle timestamp provided."""
        lag = TradeLagCalculator.calculate(None)
        assert lag is None

    def test_calculate_never_returns_negative(self) -> None:
        """Lag is never negative (future timestamp)."""
        future = datetime.utcnow() + timedelta(minutes=1)
        lag = TradeLagCalculator.calculate(future)
        assert lag is not None
        assert lag >= 0.0


class TestBotHealthAssembler:
    """Test BotHealthAssembler."""

    def test_assemble_calculates_status_and_lag(self) -> None:
        """Assembles complete health with calculated fields."""
        now = datetime.utcnow()
        base_health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-1",
            mode="dry_run",
            status=HealthStatus.UNKNOWN,
            last_heartbeat_at=now,
            error_count_1h=0,
        )

        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)
        complete = BotHealthAssembler.assemble(base_health, two_minutes_ago)

        assert complete.status == HealthStatus.HEALTHY
        assert complete.trade_lag_seconds is not None
        assert complete.trade_lag_seconds >= 110.0  # ~120 seconds

    def test_assemble_sets_message_for_unhealthy(self) -> None:
        """Sets appropriate message for unhealthy status."""
        six_minutes_ago = datetime.utcnow() - timedelta(minutes=6)
        base_health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-1",
            mode="dry_run",
            status=HealthStatus.UNKNOWN,
            last_heartbeat_at=six_minutes_ago,
            error_count_1h=0,
        )

        complete = BotHealthAssembler.assemble(base_health, None)

        assert complete.status == HealthStatus.UNHEALTHY
        assert complete.message is not None


class TestSystemHealthCalculator:
    """Test SystemHealthCalculator."""

    def test_healthy_when_all_components_healthy(self) -> None:
        """Returns HEALTHY when all components are healthy."""
        bot_health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-1",
            mode="dry_run",
            status=HealthStatus.HEALTHY,
        )

        status = SystemHealthCalculator.calculate(
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            bot_healths=[bot_health],
        )
        assert status == HealthStatus.HEALTHY

    def test_unhealthy_when_database_down(self) -> None:
        """Returns UNHEALTHY when database is down."""
        status = SystemHealthCalculator.calculate(
            api_healthy=True,
            database_healthy=False,
            duckdb_healthy=True,
            bot_healths=[],
        )
        assert status == HealthStatus.UNHEALTHY

    def test_unhealthy_when_api_down(self) -> None:
        """Returns UNHEALTHY when API is down."""
        status = SystemHealthCalculator.calculate(
            api_healthy=False,
            database_healthy=True,
            duckdb_healthy=True,
            bot_healths=[],
        )
        assert status == HealthStatus.UNHEALTHY

    def test_degraded_when_bot_unhealthy(self) -> None:
        """Returns DEGRADED when any bot is unhealthy."""
        unhealthy_bot = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-1",
            mode="dry_run",
            status=HealthStatus.UNHEALTHY,
        )

        status = SystemHealthCalculator.calculate(
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            bot_healths=[unhealthy_bot],
        )
        assert status == HealthStatus.DEGRADED

    def test_degraded_when_duckdb_down(self) -> None:
        """Returns DEGRADED when DuckDB is down."""
        bot_health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-1",
            mode="dry_run",
            status=HealthStatus.HEALTHY,
        )

        status = SystemHealthCalculator.calculate(
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=False,
            bot_healths=[bot_health],
        )
        assert status == HealthStatus.DEGRADED
