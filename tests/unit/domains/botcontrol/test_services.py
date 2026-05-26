"""Unit tests for bot control domain services."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

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
    """Test ProcessManager service."""

    def test_is_process_running(self) -> None:
        """Check if process exists via static method."""
        # Current Python process should be running
        current_pid = os.getpid()
        assert ProcessManager.is_process_running(current_pid) is True

        # Invalid PID should not be running
        assert ProcessManager.is_process_running(99999) is False
        # Note: -1 behavior varies by OS, skip or accept either result

    @pytest.mark.asyncio
    async def test_get_process_status_no_pid(self) -> None:
        """Status is UNKNOWN when no PID provided."""
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test")

        status = await manager.get_process_status(context, None)
        assert status == ProcessStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_process_status_running(self) -> None:
        """Status is RUNNING when process exists."""
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test")

        # Test with current Python process
        status = await manager.get_process_status(context, os.getpid())
        assert status == ProcessStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_process_status_stopped(self) -> None:
        """Status is STOPPED when process doesn't exist."""
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test")

        # Test with invalid PID
        status = await manager.get_process_status(context, 99999)
        assert status == ProcessStatus.STOPPED

    @pytest.mark.asyncio
    async def test_cleanup_stale_processes(self) -> None:
        """Mark processes with dead PIDs as ERROR."""
        manager = ProcessManager()

        # Create fake processes with invalid PIDs
        stale_processes = [
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

        cleaned = await manager.cleanup_stale_processes(stale_processes)

        assert len(cleaned) == 2
        assert all(p.status == ProcessStatus.ERROR for p in cleaned)

    @pytest.mark.asyncio
    async def test_stop_bot_not_tracked(self) -> None:
        """Stop bot returns UNKNOWN when process not tracked."""
        manager = ProcessManager()
        context = BotContext(bot_type="neat_swing", instance_id="test-not-tracked")

        status, exit_code, error = await manager.stop_bot(context, graceful=True)

        assert status == ProcessStatus.UNKNOWN
        assert error == "Process not tracked locally"
