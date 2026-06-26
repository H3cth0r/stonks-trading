"""Unit tests for health domain entities."""

from datetime import datetime, timedelta

import pytest

from stonks_trading.domains.health.entities import BotHealth, BotHeartbeat, HealthStatus, SystemHealth


class TestHealthStatus:
    """Test HealthStatus enum."""

    def test_health_status_values(self) -> None:
        """HealthStatus has expected values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestBotHeartbeat:
    """Test BotHeartbeat entity."""

    def test_bot_heartbeat_creation(self) -> None:
        """Can create BotHeartbeat with required fields."""
        now = datetime.utcnow()
        heartbeat = BotHeartbeat(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            timestamp=now,
            state_hash="abc123",
            candle_timestamp=now,
        )

        assert heartbeat.bot_type == "neat_swing"
        assert heartbeat.bot_instance_id == "test-bot-1"
        assert heartbeat.timestamp == now
        assert heartbeat.state_hash == "abc123"
        assert heartbeat.candle_timestamp == now
        assert heartbeat.id is None

    def test_bot_heartbeat_defaults(self) -> None:
        """BotHeartbeat has sensible defaults."""
        heartbeat = BotHeartbeat(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
        )

        assert heartbeat.bot_type == "neat_swing"
        assert heartbeat.bot_instance_id == "test-bot-1"
        assert heartbeat.timestamp is not None
        assert heartbeat.state_hash is None
        assert heartbeat.candle_timestamp is None


class TestBotHealth:
    """Test BotHealth entity."""

    def test_bot_health_creation(self) -> None:
        """Can create BotHealth with all fields."""
        now = datetime.utcnow()
        health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=HealthStatus.HEALTHY,
            last_heartbeat_at=now,
            trade_lag_seconds=30.0,
            last_trade_at=now,
            position_count=1,
            current_drawdown=0.05,
            error_count_1h=0,
            message=None,
            uptime_seconds=3600,
        )

        assert health.bot_type == "neat_swing"
        assert health.status == HealthStatus.HEALTHY
        assert health.trade_lag_seconds == 30.0

    def test_bot_health_defaults(self) -> None:
        """BotHealth has sensible defaults."""
        health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=HealthStatus.UNKNOWN,
        )

        assert health.position_count == 0
        assert health.current_drawdown == 0.0
        assert health.error_count_1h == 0


class TestSystemHealth:
    """Test SystemHealth entity."""

    def test_system_health_creation(self) -> None:
        """Can create SystemHealth with all fields."""
        now = datetime.utcnow()
        bot_health = BotHealth(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=HealthStatus.HEALTHY,
        )

        system = SystemHealth(
            status=HealthStatus.HEALTHY,
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            bots=[bot_health],
            checked_at=now,
        )

        assert system.status == HealthStatus.HEALTHY
        assert system.api_healthy is True
        assert len(system.bots) == 1

    def test_system_health_defaults(self) -> None:
        """SystemHealth has sensible defaults."""
        now = datetime.utcnow()
        system = SystemHealth(
            status=HealthStatus.HEALTHY,
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            checked_at=now,
        )

        assert system.bots == []
        assert system.message is None
