"""Integration tests for database layer.

These tests verify database connectivity and ORM functionality.
They require a running database and are skipped in CI if not available.
"""

from datetime import UTC, datetime

import pytest

from stonks_trading.shared.database import TORTOISE_ORM, close_db, init_db
from stonks_trading.shared.postgres_models import (
    BotDecisionModel,
    DataGapModel,
    GenerationMetricModel,
    GenomeModel,
    OrderModel,
    PositionModel,
    RiskEventModel,
    SystemConfigModel,
    TradeModel,
    TradeSide,
    TradingMode,
    TrainingRunModel,
)

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in pytest.importorskip("os").environ
    or "localhost" in pytest.importorskip("os").environ.get("DATABASE_URL", ""),
    reason="Database integration tests require DATABASE_URL",
)


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up and tear down database for each test."""
    await init_db()
    yield
    # Clean up tables after each test
    await TradeModel.all().delete()
    await PositionModel.all().delete()
    await GenomeModel.all().delete()
    await OrderModel.all().delete()
    await RiskEventModel.all().delete()
    await BotDecisionModel.all().delete()
    await TrainingRunModel.all().delete()
    await GenerationMetricModel.all().delete()
    await DataGapModel.all().delete()
    await SystemConfigModel.all().delete()
    await close_db()


class TestDatabaseConnection:
    """Tests for database connectivity."""

    async def test_init_db(self) -> None:
        """Test database initialization."""
        await init_db()
        await close_db()

    async def test_tortoise_orm_config(self) -> None:
        """Test TORTOISE_ORM config is valid."""
        assert "connections" in TORTOISE_ORM
        assert "apps" in TORTOISE_ORM
        assert "default" in TORTOISE_ORM["connections"]


class TestTradeModel:
    """Tests for TradeModel CRUD operations."""

    async def test_create_trade(self) -> None:
        """Test creating a trade."""
        trade = await TradeModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            fill_price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USDT",
            fee_rate=0.001,
            slippage_bps=1.0,
            mode=TradingMode.DRY_RUN,
            genome_id="genome_001",
        )
        assert trade.id is not None
        assert trade.symbol == "BTC_USD"
        assert trade.side == TradeSide.BUY

    async def test_read_trade(self) -> None:
        """Test reading a trade by ID."""
        trade = await TradeModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            fill_price=50000.0,
            quantity=0.1,
            fee=5.0,
        )
        read_trade = await TradeModel.get(id=trade.id)
        assert read_trade.symbol == "BTC_USD"

    async def test_update_trade(self) -> None:
        """Test updating a trade."""
        trade = await TradeModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            fill_price=50000.0,
            quantity=0.1,
            fee=5.0,
        )
        trade.realized_pnl = 100.0
        await trade.save()
        updated = await TradeModel.get(id=trade.id)
        assert updated.realized_pnl == 100.0

    async def test_delete_trade(self) -> None:
        """Test deleting a trade."""
        trade = await TradeModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            fill_price=50000.0,
            quantity=0.1,
            fee=5.0,
        )
        await trade.delete()
        deleted = await TradeModel.get_or_none(id=trade.id)
        assert deleted is None


class TestPositionModel:
    """Tests for PositionModel CRUD operations."""

    async def test_create_position(self) -> None:
        """Test creating a position."""
        position = await PositionModel.create(
            symbol="BTC_USD",
            quantity=0.5,
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=50.0,
        )
        assert position.id is not None
        assert position.symbol == "BTC_USD"

    async def test_get_position_by_symbol(self) -> None:
        """Test getting position by symbol."""
        await PositionModel.create(
            symbol="BTC_USD",
            quantity=0.5,
            entry_price=50000.0,
        )
        position = await PositionModel.get(symbol="BTC_USD")
        assert position.quantity == 0.5

    async def test_update_position(self) -> None:
        """Test updating a position."""
        position = await PositionModel.create(
            symbol="BTC_USD",
            quantity=0.5,
            entry_price=50000.0,
        )
        position.quantity = 0.6
        await position.save()
        updated = await PositionModel.get(symbol="BTC_USD")
        assert updated.quantity == 0.6


class TestGenomeModel:
    """Tests for GenomeModel CRUD operations."""

    async def test_create_genome(self) -> None:
        """Test creating a genome."""
        genome = await GenomeModel.create(
            symbol="BTC_USD",
            genome_data=b"test_genome_data",
            fitness=1.25,
            generation=30,
            model_family="NEAT_RNN_V1",
            is_active=True,
            fee_rate_used=0.001,
            trained_at=datetime.now(UTC),
        )
        assert genome.id is not None
        assert genome.fitness == 1.25

    async def test_get_active_genome(self) -> None:
        """Test getting active genome."""
        await GenomeModel.create(
            symbol="BTC_USD",
            genome_data=b"test",
            fitness=1.0,
            is_active=True,
            trained_at=datetime.now(UTC),
        )
        genome = await GenomeModel.get(is_active=True)
        assert genome.is_active is True

    async def test_genome_filtering(self) -> None:
        """Test filtering genomes by symbol."""
        await GenomeModel.create(
            symbol="BTC_USD",
            genome_data=b"test",
            fitness=1.0,
            trained_at=datetime.now(UTC),
        )
        await GenomeModel.create(
            symbol="ETH_USD",
            genome_data=b"test",
            fitness=0.8,
            trained_at=datetime.now(UTC),
        )
        btc_genomes = await GenomeModel.filter(symbol="BTC_USD")
        assert len(btc_genomes) == 1


class TestOrderModel:
    """Tests for OrderModel CRUD operations."""

    async def test_create_order(self) -> None:
        """Test creating an order."""
        order = await OrderModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            status="pending",
            requested_qty=0.1,
            mode=TradingMode.DRY_RUN,
        )
        assert order.id is not None
        assert order.status == "pending"

    async def test_update_order_status(self) -> None:
        """Test updating order status."""
        order = await OrderModel.create(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            status="pending",
            requested_qty=0.1,
        )
        order.status = "filled"
        order.filled_qty = 0.1
        order.filled_at = datetime.now(UTC)
        await order.save()
        updated = await OrderModel.get(id=order.id)
        assert updated.status == "filled"


class TestRiskEventModel:
    """Tests for RiskEventModel CRUD operations."""

    async def test_create_risk_event(self) -> None:
        """Test creating a risk event."""
        event = await RiskEventModel.create(
            symbol="BTC_USD",
            event_type="drawdown_warning",
            severity="warning",
            value=0.12,
            threshold=0.15,
            message="Drawdown at 12%",
            mode=TradingMode.DRY_RUN,
        )
        assert event.id is not None
        assert event.event_type == "drawdown_warning"

    async def test_acknowledge_risk_event(self) -> None:
        """Test acknowledging a risk event."""
        event = await RiskEventModel.create(
            symbol="BTC_USD",
            event_type="drawdown_warning",
            severity="warning",
            value=0.12,
            threshold=0.15,
            message="Drawdown at 12%",
        )
        event.acknowledged_at = datetime.now(UTC)
        event.acknowledged_by = "test_user"
        await event.save()
        updated = await RiskEventModel.get(id=event.id)
        assert updated.acknowledged_by == "test_user"


class TestSystemConfigModel:
    """Tests for SystemConfigModel CRUD operations."""

    async def test_create_config(self) -> None:
        """Test creating a system config."""
        config = await SystemConfigModel.create(
            key="test_key",
            value={"test": "data"},
        )
        assert config.id is not None
        assert config.key == "test_key"

    async def test_update_config(self) -> None:
        """Test updating a system config."""
        config = await SystemConfigModel.create(
            key="test_key",
            value={"test": "data"},
        )
        config.value = {"test": "updated"}
        await config.save()
        updated = await SystemConfigModel.get(key="test_key")
        assert updated.value == {"test": "updated"}

    async def test_unique_key_constraint(self) -> None:
        """Test that keys must be unique."""
        await SystemConfigModel.create(key="unique_key", value={"test": 1})
        with pytest.raises(Exception):  # Should raise integrity error
            await SystemConfigModel.create(key="unique_key", value={"test": 2})
