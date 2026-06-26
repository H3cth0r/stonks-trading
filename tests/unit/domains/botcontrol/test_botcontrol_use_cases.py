"""Unit tests for botcontrol use cases.

Tests use cases with mocked repositories and services.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.botcontrol.use_cases import (
    GetBotStatusUseCase,
    ListRunningBotsUseCase,
    StartBotUseCase,
    StopBotUseCase,
)


class TestStartBotUseCase:
    """Test StartBotUseCase."""

    @pytest.mark.asyncio
    async def test_start_bot_success(self):
        """Start bot successfully."""
        mock_instance = MagicMock()
        mock_instance.mode = "dry_run"

        with patch(
            "stonks_trading.domains.botcontrol.use_cases.check_bot_instance_exists",
            new=AsyncMock(return_value=True),
        ), patch(
            "stonks_trading.domains.botcontrol.use_cases.get_bot_process",
            new=AsyncMock(return_value=None),
        ), patch(
            "stonks_trading.domains.botcontrol.use_cases.get_bot_instance",
            new=AsyncMock(return_value=mock_instance),
        ), patch(
            "stonks_trading.domains.botcontrol.use_cases.create_bot_process",
            new=AsyncMock(return_value=MagicMock()),
        ):
            use_case = StartBotUseCase()
            use_case.process_manager = MagicMock()
            use_case.process_manager.start_bot = AsyncMock(return_value=(MagicMock(), None))

            result = await use_case.execute(
                bot_type="neat_swing",
                instance_id="test-bot",
                symbols=["BTC_USD"],
                mode="dry_run",
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_start_bot_not_registered(self):
        """Cannot start unregistered bot."""
        with patch(
            "stonks_trading.domains.botcontrol.use_cases.check_bot_instance_exists",
            new=AsyncMock(return_value=False),
        ):
            use_case = StartBotUseCase()

            with pytest.raises(ValueError, match="not registered"):
                await use_case.execute(
                    bot_type="neat_swing",
                    instance_id="unregistered-bot",
                    symbols=["BTC_USD"],
                    mode="dry_run",
                )


class TestStopBotUseCase:
    """Test StopBotUseCase."""

    @pytest.mark.asyncio
    async def test_stop_bot_not_found(self):
        """Cannot stop non-existent bot."""
        with patch(
            "stonks_trading.domains.botcontrol.use_cases.get_bot_process",
            new=AsyncMock(return_value=None),
        ):
            use_case = StopBotUseCase()

            with pytest.raises(ValueError, match="not found"):
                await use_case.execute("neat_swing", "non-existent")


class TestGetBotStatusUseCase:
    """Test GetBotStatusUseCase."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_bot_status(self):
        """Get status for non-existent bot returns None."""
        with patch(
            "stonks_trading.domains.botcontrol.use_cases.get_bot_process",
            new=AsyncMock(return_value=None),
        ), patch(
            "stonks_trading.domains.botcontrol.use_cases.get_bot_instance",
            new=AsyncMock(return_value=None),
        ):
            use_case = GetBotStatusUseCase()

            result = await use_case.execute("neat_swing", "non-existent")

            assert result is None


class TestListRunningBotsUseCase:
    """Test ListRunningBotsUseCase."""

    @pytest.mark.asyncio
    async def test_list_running_bots_empty(self):
        """List running bots returns empty when none."""
        with patch(
            "stonks_trading.domains.botcontrol.use_cases.list_running_bots",
            new=AsyncMock(return_value=[]),
        ):
            use_case = ListRunningBotsUseCase()

            result = await use_case.execute()

            assert result == []
