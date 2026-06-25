"""Unit tests for bot control domain entities."""

from datetime import datetime, timedelta

import pytest

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus


class TestProcessStatus:
    """Test ProcessStatus enum."""

    def test_process_status_values(self) -> None:
        """ProcessStatus has expected values."""
        assert ProcessStatus.REGISTERED.value == "registered"
        assert ProcessStatus.STARTING.value == "starting"
        assert ProcessStatus.RUNNING.value == "running"
        assert ProcessStatus.STOPPING.value == "stopping"
        assert ProcessStatus.STOPPED.value == "stopped"
        assert ProcessStatus.ERROR.value == "error"
        assert ProcessStatus.UNKNOWN.value == "unknown"


class TestBotProcess:
    """Test BotProcess entity."""

    def test_bot_process_creation(self) -> None:
        """Can create BotProcess with required fields."""
        now = datetime.utcnow()
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            symbols=["BTC_USD"],
            pid=12345,
            status=ProcessStatus.RUNNING,
            started_at=now,
            config_path="config-neat.txt",
        )

        assert process.bot_type == "neat_swing"
        assert process.bot_instance_id == "test-bot-1"
        assert process.mode == "dry_run"
        assert process.symbols == ["BTC_USD"]
        assert process.pid == 12345
        assert process.status == ProcessStatus.RUNNING
        assert process.started_at == now
        assert process.config_path == "config-neat.txt"

    def test_bot_process_defaults(self) -> None:
        """BotProcess has sensible defaults."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
        )

        assert process.symbols == []
        assert process.pid is None
        assert process.status == ProcessStatus.REGISTERED
        assert process.started_at is None
        assert process.stopped_at is None
        assert process.exit_code is None
        assert process.error_message is None
        assert process.config_path == "config-neat.txt"

    def test_bot_process_is_running(self) -> None:
        """is_running property works correctly."""
        running_process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.RUNNING,
        )
        assert running_process.is_running is True

        stopped_process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-2",
            mode="dry_run",
            status=ProcessStatus.STOPPED,
        )
        assert stopped_process.is_running is False

    def test_bot_process_context_key(self) -> None:
        """context_key returns unique identifier."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
        )
        assert process.context_key == "neat_swing/test-bot-1"

    def test_bot_process_uptime_running(self) -> None:
        """uptime_seconds calculated correctly for running bot."""
        started = datetime.utcnow() - timedelta(seconds=3600)
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.RUNNING,
            started_at=started,
        )
        uptime = process.uptime_seconds
        assert uptime is not None
        assert 3590 <= uptime <= 3610  # Allow small timing variance

    def test_bot_process_uptime_stopped(self) -> None:
        """uptime_seconds calculated correctly for stopped bot."""
        started = datetime.utcnow() - timedelta(seconds=7200)
        stopped = datetime.utcnow() - timedelta(seconds=3600)
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.STOPPED,
            started_at=started,
            stopped_at=stopped,
        )
        uptime = process.uptime_seconds
        assert uptime is not None
        assert 3590 <= uptime <= 3610  # Allow small timing variance

    def test_bot_process_uptime_not_started(self) -> None:
        """uptime_seconds is None when bot not started."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.REGISTERED,
        )
        assert process.uptime_seconds is None


class TestBotStatus:
    """Test BotStatus entity."""

    def test_bot_status_creation(self) -> None:
        """Can create BotStatus with all fields."""
        now = datetime.utcnow()
        status = BotStatus(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=ProcessStatus.RUNNING,
            mode="dry_run",
            uptime_seconds=3600,
            last_trade_at=now,
            current_equity=10500.50,
            position_count=1,
            pid=12345,
            message="Bot running normally",
            last_seen=now,
        )

        assert status.bot_type == "neat_swing"
        assert status.bot_instance_id == "test-bot-1"
        assert status.status == ProcessStatus.RUNNING
        assert status.mode == "dry_run"
        assert status.uptime_seconds == 3600
        assert status.current_equity == 10500.50
        assert status.position_count == 1
        assert status.pid == 12345
        assert status.message == "Bot running normally"

    def test_bot_status_defaults(self) -> None:
        """BotStatus has sensible defaults."""
        status = BotStatus(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=ProcessStatus.REGISTERED,
            mode="dry_run",
        )

        assert status.uptime_seconds is None
        assert status.last_trade_at is None
        assert status.current_equity is None
        assert status.position_count == 0
        assert status.pid is None
        assert status.message is None
        assert status.last_seen is None

    def test_bot_status_is_healthy(self) -> None:
        """is_healthy property works correctly."""
        healthy = BotStatus(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=ProcessStatus.RUNNING,
            mode="dry_run",
        )
        assert healthy.is_healthy is True

        unhealthy = BotStatus(
            bot_type="neat_swing",
            bot_instance_id="test-bot-2",
            status=ProcessStatus.ERROR,
            mode="dry_run",
        )
        assert unhealthy.is_healthy is False

    def test_bot_status_display(self) -> None:
        """status_display returns human-readable status."""
        status = BotStatus(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=ProcessStatus.RUNNING,
            mode="dry_run",
        )
        assert status.status_display == "running"
