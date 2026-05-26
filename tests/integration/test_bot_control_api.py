"""Integration tests for bot control API.

Tests require running database (Postgres).
"""

from datetime import datetime

import pytest
import pytest_asyncio

from stonks_trading.domains.botcontrol.repositories import (
    check_bot_instance_exists,
    create_bot_process,
    get_bot_process,
    list_bot_processes,
    list_running_bots,
    update_bot_process_status,
)
from stonks_trading.domains.botcontrol.use_cases import GetBotStatusUseCase
from stonks_trading.domains.botcontrol.entities import BotProcess, ProcessStatus
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.postgres_models import BotInstanceModel, BotProcessModel


@pytest.mark.asyncio
class TestBotControlRepositories:
    """Test bot control repository functions."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_db(self, db_transaction):
        """Automatically use database transaction for all tests."""
        pass

    @pytest_asyncio.fixture
    async def test_bot_instance(self) -> BotInstanceModel:
        """Create a test bot instance."""
        instance = await BotInstanceModel.create(
            bot_type="neat_swing",
            instance_id="test-bot-control-1",
            symbols=["BTC_USD"],
            mode="dry_run",
            status="stopped",
        )
        yield instance
        await instance.delete()

    @pytest_asyncio.fixture
    async def test_process(self, test_bot_instance: BotInstanceModel) -> BotProcess:
        """Create a test bot process."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-control-1",
            mode="dry_run",
            symbols=["BTC_USD"],
            pid=12345,
            status=ProcessStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        created = await create_bot_process(process)
        yield created

        # Cleanup
        await BotProcessModel.filter(
            bot_type="neat_swing",
            bot_instance_id="test-bot-control-1",
        ).delete()

    async def test_check_bot_instance_exists(self, test_bot_instance: BotInstanceModel) -> None:
        """Check if bot instance exists."""
        exists = await check_bot_instance_exists("neat_swing", "test-bot-control-1")
        assert exists is True

        exists = await check_bot_instance_exists("neat_swing", "non-existent")
        assert exists is False

    async def test_create_bot_process(self, test_bot_instance: BotInstanceModel) -> None:
        """Create and retrieve bot process."""
        process = BotProcess(
            bot_type="neat_swing",
            bot_instance_id="test-bot-control-1",
            mode="dry_run",
            symbols=["BTC_USD", "ETH_USD"],
            pid=12345,
            status=ProcessStatus.STARTING,
            started_at=datetime.utcnow(),
            config_path="test-config.txt",
        )

        created = await create_bot_process(process)
        assert created.bot_type == "neat_swing"
        assert created.config_path == "test-config.txt"
        assert created.created_at is not None

        # Cleanup
        await BotProcessModel.filter(
            bot_type="neat_swing",
            bot_instance_id="test-bot-control-1",
        ).delete()

    async def test_get_bot_process(self, test_process: BotProcess) -> None:
        """Get bot process by context."""
        retrieved = await get_bot_process("neat_swing", "test-bot-control-1")
        assert retrieved is not None
        assert retrieved.bot_type == "neat_swing"
        assert retrieved.bot_instance_id == "test-bot-control-1"
        assert retrieved.status == ProcessStatus.RUNNING

    async def test_get_bot_process_not_found(self) -> None:
        """Return None for non-existent process."""
        retrieved = await get_bot_process("neat_swing", "non-existent")
        assert retrieved is None

    async def test_update_bot_process_status(self, test_process: BotProcess) -> None:
        """Update bot process status."""
        context = BotContext(bot_type="neat_swing", instance_id="test-bot-control-1")

        updated = await update_bot_process_status(
            context=context,
            status=ProcessStatus.STOPPED,
            stopped_at=datetime.utcnow(),
            exit_code=0,
        )

        assert updated is not None
        assert updated.status == ProcessStatus.STOPPED
        assert updated.exit_code == 0

    async def test_list_running_bots(self, test_process: BotProcess) -> None:
        """List running bots."""
        running = await list_running_bots()
        assert len(running) >= 1
        assert all(p.status == ProcessStatus.RUNNING for p in running)

    async def test_list_bot_processes_by_status(self, test_process: BotProcess) -> None:
        """List processes with status filter."""
        running = await list_bot_processes(status=ProcessStatus.RUNNING)
        assert len(running) >= 1

        stopped = await list_bot_processes(status=ProcessStatus.STOPPED)
        assert all(p.status == ProcessStatus.STOPPED for p in stopped)


@pytest.mark.asyncio
class TestBotControlUseCases:
    """Test bot control use cases."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_db(self, db_transaction):
        """Automatically use database transaction for all tests."""
        pass

    @pytest_asyncio.fixture
    async def registered_bot(self) -> BotInstanceModel:
        """Create a registered bot for testing."""
        instance = await BotInstanceModel.create(
            bot_type="neat_swing",
            instance_id="test-use-case-1",
            symbols=["BTC_USD"],
            mode="dry_run",
            status="stopped",
        )
        yield instance
        await instance.delete()

    async def test_get_bot_status_use_case(self, registered_bot: BotInstanceModel) -> None:
        """Get bot status via use case."""
        use_case = GetBotStatusUseCase()
        status = await use_case.execute("neat_swing", "test-use-case-1")

        # Should return REGISTERED status (no process yet)
        assert status is not None
        assert status.status == ProcessStatus.REGISTERED
