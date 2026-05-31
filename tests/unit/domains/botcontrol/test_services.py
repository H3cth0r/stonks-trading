"""Unit tests for bot control domain services."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.botcontrol.services import (
    BotStatusAssembler,
    ProcessManager,
    ProcessValidator,
)
from stonks_trading.domains.trading.value_objects import BotContext


class TestProcessValidator:
    """Test ProcessValidator service."""

    def test_validate_bot_type_valid(self) -> None:
        """Accept valid bot types."""
        assert ProcessValidator.validate_bot_type("neat_swing") is True

    def test_validate_bot_type_invalid(self) -> None:
        """Reject invalid bot types."""
        assert ProcessValidator.validate_bot_type("unknown_bot") is False
        assert ProcessValidator.validate_bot_type("") is False

    def test_validate_mode_valid(self) -> None:
        """Accept valid modes."""
        assert ProcessValidator.validate_mode("dry_run") is True
        assert ProcessValidator.validate_mode("live") is True

    def test_validate_mode_invalid(self) -> None:
        """Reject invalid modes."""
        assert ProcessValidator.validate_mode("test") is False
        assert ProcessValidator.validate_mode("backtest") is False

    def test_validate_symbols_valid(self) -> None:
        """Accept valid symbol lists."""
        is_valid, error = ProcessValidator.validate_symbols(["BTC_USD"])
        assert is_valid is True
        assert error is None

        is_valid, error = ProcessValidator.validate_symbols(["BTC_USD", "ETH_USD"])
        assert is_valid is True
        assert error is None

    def test_validate_symbols_empty(self) -> None:
        """Reject empty symbol lists."""
        is_valid, error = ProcessValidator.validate_symbols([])
        assert is_valid is False
        assert "at least one symbol" in error.lower()

    def test_validate_symbols_invalid(self) -> None:
        """Reject invalid symbols."""
        is_valid, error = ProcessValidator.validate_symbols(["X"])
        assert is_valid is False
        assert "invalid symbol" in error.lower()


class TestBotStatusAssembler:
    """Test BotStatusAssembler service."""

    def test_assemble_basic(self) -> None:
        """Assemble status with minimal data."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.RUNNING,
        )

        status = BotStatusAssembler.assemble(
            process=process,
            state=None,
            last_trade_at=None,
        )

        assert status.bot_type == "neat_swing"
        assert status.bot_instance_id == "test-bot-1"
        assert status.status == ProcessStatus.RUNNING
        assert status.mode == "dry_run"
        assert status.current_equity is None
        assert status.position_count == 0

    def test_assemble_with_state(self) -> None:
        """Assemble status with state data."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.RUNNING,
        )

        state = {
            "current_equity": 10500.50,
            "positions": {"BTC_USD": {"quantity": 0.5}},
        }

        status = BotStatusAssembler.assemble(
            process=process,
            state=state,
            last_trade_at=None,
        )

        assert status.current_equity == 10500.50
        assert status.position_count == 1

    def test_assemble_with_message(self) -> None:
        """Assemble status includes message for non-running states."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.ERROR,
            error_message="Process crashed",
        )

        status = BotStatusAssembler.assemble(
            process=process,
            state=None,
            last_trade_at=None,
        )

        assert status.message == "Process crashed"

    def test_assemble_starting_message(self) -> None:
        """Assemble status shows message for starting state."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            status=ProcessStatus.STARTING,
        )

        status = BotStatusAssembler.assemble(
            process=process,
            state=None,
            last_trade_at=None,
        )

        assert "starting" in status.message.lower()


class TestProcessManager:
    """Test ProcessManager service (Worker-only architecture)."""

    def test_is_process_running(self) -> None:
        """In Worker mode, API never has direct process visibility.

        ProcessManager.is_process_running() always returns False
        because the Worker container manages subprocesses.
        """
        # API container cannot see Worker subprocesses
        assert ProcessManager.is_process_running(99999) is False
        assert ProcessManager.is_process_running(1) is False

    @pytest.mark.asyncio
    async def test_get_process_status_no_pid(self) -> None:
        """Status is UNKNOWN when no PID provided."""
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test")

        status = await manager.get_process_status(context, None)
        assert status == ProcessStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_process_status_returns_unknown(self) -> None:
        """In Worker mode, API returns UNKNOWN for all PIDs.

        The API container delegates to Worker HTTP API and does not
        have direct visibility into subprocess status.
        """
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test")

        # Any PID returns UNKNOWN (Worker manages actual status)
        status = await manager.get_process_status(context, 12345)
        assert status == ProcessStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_cleanup_stale_processes(self) -> None:
        """In Worker mode, stale process cleanup is handled by Worker.

        API layer returns empty list - Worker handles subprocess lifecycle.
        """
        manager = ProcessManager()

        # Create processes (Worker manages these)
        processes = [
            BotProcess(
                bot_type="neat_swing",
                bot_instance_id="test-1",
                mode="dry_run",
                status=ProcessStatus.RUNNING,
                pid=99998,
            ),
            BotProcess(
                bot_type="neat_swing",
                bot_instance_id="test-2",
                mode="dry_run",
                status=ProcessStatus.RUNNING,
                pid=99999,
            ),
        ]

        cleaned = await manager.cleanup_stale_processes(processes)

        # Worker handles cleanup - API returns empty
        assert len(cleaned) == 0

    @pytest.mark.asyncio
    async def test_stop_bot_delegates_to_worker(self) -> None:
        """Stop bot delegates to Worker HTTP API.

        When Worker is unavailable, returns ERROR status.
        """
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test-not-tracked")

        status, exit_code, error = await manager.stop_bot(context, graceful=True)

        # Without Worker running, we get ERROR (Worker HTTP call failed)
        assert status == ProcessStatus.ERROR
        assert error is not None
        assert "Worker" in error or "nodename" in error or "servname" in error

    @pytest.mark.asyncio
    async def test_start_bot_delegates_to_worker(self) -> None:
        """Start bot delegates to Worker HTTP API."""
        manager = ProcessManager()

        # Without Worker running, start raises RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            await manager.start_bot(
                bot_type="neat_swing",
                instance_id="test-bot",
                symbols=["BTC_USD"],
                mode="dry_run",
                config_path="config-neat.txt",
            )

        assert "Worker" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_start_bot_with_mocked_worker(self) -> None:
        """Start bot succeeds when Worker responds."""
        from stonks_trading.domains.botcontrol.dtos import StartBotResponse

        manager = ProcessManager()

        # Mock the Worker HTTP client
        mock_response = StartBotResponse(
            bot_type="neat_swing",
            bot_instance_id="test-bot",
            status="starting",
            pid=12345,
            started_at=datetime.utcnow(),
            message="Bot started",
        )

        with patch.object(
            manager._worker_client,
            'start_bot',
            new=AsyncMock(return_value=mock_response)
        ):
            result = await manager.start_bot(
                bot_type="neat_swing",
                instance_id="test-bot",
                symbols=["BTC_USD"],
                mode="dry_run",
                config_path="config-neat.txt",
            )

            assert result.bot_type == "neat_swing"
            assert result.bot_instance_id == "test-bot"
            assert result.pid == 12345
            assert result.status == ProcessStatus.STARTING

    @pytest.mark.asyncio
    async def test_stop_bot_with_mocked_worker(self) -> None:
        """Stop bot succeeds when Worker responds."""
        from stonks_trading.domains.botcontrol.dtos import StopBotResponse

        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test-bot")

        # Mock the Worker HTTP client
        mock_response = StopBotResponse(
            bot_type="neat_swing",
            bot_instance_id="test-bot",
            status="stopped",
            stopped_at=datetime.utcnow().isoformat(),
            uptime_seconds=60,
            exit_code=0,
            message="Bot stopped gracefully",
        )

        with patch.object(
            manager._worker_client,
            'stop_bot',
            new=AsyncMock(return_value=mock_response)
        ):
            status, exit_code, error = await manager.stop_bot(
                context=context,
                graceful=True,
            )

            assert status == ProcessStatus.STOPPED
            assert exit_code == 0
            assert "stopped" in (error or "").lower()
