"""Unit tests for botcontrol repositories.

Tests repository functions with mocked database models.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.botcontrol.entities import BotProcess, ProcessStatus
from stonks_trading.domains.botcontrol.repositories import (
    _model_to_bot_process,
    check_bot_instance_exists,
    create_bot_process,
    delete_bot_process,
    get_bot_process,
    list_bot_processes,
    list_running_bots,
    list_stale_processes,
    update_bot_process_status,
)
from stonks_trading.domains.trading.value_objects import BotContext


class TestModelToEntityConversion:
    """Test conversion functions."""

    def test_model_to_bot_process(self):
        """Test conversion from model to entity."""
        mock_model = MagicMock()
        mock_model.bot_type = "neat_swing"
        mock_model.bot_instance_id = "test-bot-1"
        mock_model.mode = "dry_run"
        mock_model.symbols = ["BTC_USD"]
        mock_model.pid = 12345
        mock_model.status = "running"
        mock_model.started_at = datetime.utcnow()
        mock_model.stopped_at = None
        mock_model.exit_code = None
        mock_model.error_message = None
        mock_model.config_path = "config.txt"
        mock_model.created_at = datetime.utcnow()
        mock_model.updated_at = datetime.utcnow()

        entity = _model_to_bot_process(mock_model)

        assert entity.bot_type == "neat_swing"
        assert entity.bot_instance_id == "test-bot-1"
        assert entity.status == ProcessStatus.RUNNING
        assert entity.pid == 12345


class TestCheckBotInstanceExists:
    """Test check_bot_instance_exists function."""

    @pytest.mark.asyncio
    async def test_instance_exists(self):
        """Check returns True when instance exists."""
        mock_queryset = MagicMock()
        mock_queryset.count = AsyncMock(return_value=1)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotInstanceModel.filter",
            return_value=mock_queryset,
        ):
            result = await check_bot_instance_exists("neat_swing", "test-bot")
            assert result is True

    @pytest.mark.asyncio
    async def test_instance_not_exists(self):
        """Check returns False when instance does not exist."""
        mock_queryset = MagicMock()
        mock_queryset.count = AsyncMock(return_value=0)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotInstanceModel.filter",
            return_value=mock_queryset,
        ):
            result = await check_bot_instance_exists("neat_swing", "non-existent")
            assert result is False


class TestCreateBotProcess:
    """Test create_bot_process function."""

    @pytest.mark.asyncio
    async def test_create_process(self):
        """Create process successfully."""
        mock_model = MagicMock()
        mock_model.created_at = datetime.utcnow()
        mock_model.updated_at = datetime.utcnow()

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.create",
            new=AsyncMock(return_value=mock_model),
        ):
            process = BotProcess(
                bot_type="neat_swing",
                bot_instance_id="test-bot",
                mode="dry_run",
                symbols=["BTC_USD"],
                pid=12345,
                status=ProcessStatus.RUNNING,
                started_at=datetime.utcnow(),
                config_path="config.txt",
            )
            result = await create_bot_process(process)
            assert result.created_at is not None


class TestGetBotProcess:
    """Test get_bot_process function."""

    @pytest.mark.asyncio
    async def test_get_existing_process(self):
        """Get existing process."""
        mock_model = MagicMock()
        mock_model.bot_type = "neat_swing"
        mock_model.bot_instance_id = "test-bot"
        mock_model.mode = "dry_run"
        mock_model.symbols = ["BTC_USD"]
        mock_model.pid = 12345
        mock_model.status = "running"
        mock_model.started_at = datetime.utcnow()
        mock_model.stopped_at = None
        mock_model.exit_code = None
        mock_model.error_message = None
        mock_model.config_path = "config.txt"
        mock_model.created_at = datetime.utcnow()
        mock_model.updated_at = datetime.utcnow()

        mock_queryset = MagicMock()
        mock_queryset.first = AsyncMock(return_value=mock_model)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            result = await get_bot_process("neat_swing", "test-bot")
            assert result is not None
            assert result.bot_type == "neat_swing"

    @pytest.mark.asyncio
    async def test_get_nonexistent_process(self):
        """Get non-existent process returns None."""
        mock_queryset = MagicMock()
        mock_queryset.first = AsyncMock(return_value=None)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            result = await get_bot_process("neat_swing", "non-existent")
            assert result is None


class TestUpdateBotProcessStatus:
    """Test update_bot_process_status function."""

    @pytest.mark.asyncio
    async def test_update_status(self):
        """Update process status successfully."""
        mock_model = MagicMock()
        mock_model.bot_type = "neat_swing"
        mock_model.bot_instance_id = "test-bot"
        mock_model.mode = "dry_run"
        mock_model.symbols = ["BTC_USD"]
        mock_model.pid = 12345
        mock_model.status = "stopped"
        mock_model.started_at = datetime.utcnow()
        mock_model.stopped_at = datetime.utcnow()
        mock_model.exit_code = 0
        mock_model.error_message = None
        mock_model.config_path = "config.txt"
        mock_model.created_at = datetime.utcnow()
        mock_model.updated_at = datetime.utcnow()
        mock_model.save = AsyncMock()

        mock_queryset = MagicMock()
        mock_queryset.first = AsyncMock(return_value=mock_model)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            context = BotContext(bot_type="neat_swing", instance_id="test-bot")
            result = await update_bot_process_status(
                context=context,
                status=ProcessStatus.STOPPED,
                stopped_at=datetime.utcnow(),
                exit_code=0,
            )
            assert result is not None
            assert result.status == ProcessStatus.STOPPED

    @pytest.mark.asyncio
    async def test_update_nonexistent_process(self):
        """Update non-existent process returns None."""
        mock_queryset = MagicMock()
        mock_queryset.first = AsyncMock(return_value=None)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            context = BotContext(bot_type="neat_swing", instance_id="non-existent")
            result = await update_bot_process_status(
                context=context, status=ProcessStatus.STOPPED
            )
            assert result is None


class TestDeleteBotProcess:
    """Test delete_bot_process function."""

    @pytest.mark.asyncio
    async def test_delete_process(self):
        """Delete process successfully."""
        mock_queryset = MagicMock()
        mock_queryset.delete = AsyncMock(return_value=1)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            context = BotContext(bot_type="neat_swing", instance_id="test-bot")
            result = await delete_bot_process(context)
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_process(self):
        """Delete non-existent process returns False."""
        mock_queryset = MagicMock()
        mock_queryset.delete = AsyncMock(return_value=0)

        with patch(
            "stonks_trading.domains.botcontrol.repositories.BotProcessModel.filter",
            return_value=mock_queryset,
        ):
            context = BotContext(bot_type="neat_swing", instance_id="non-existent")
            result = await delete_bot_process(context)
            assert result is False
