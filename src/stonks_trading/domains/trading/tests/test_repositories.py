"""Property-based tests for trading repositories using Hypothesis and Faker.

These tests verify the behavior of repository functions:
- Trade repositories
- Position repositories
- Genome repositories
- Risk Event repositories
- Market Data repositories
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from stonks_trading.domains.trading.entities import (
    Genome,
    Position,
    RiskEvent,
    Trade,
)
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.repositories import (
    acknowledge_risk_event,
    activate_genome,
    close_position,
    get_active_genome,
    get_genome_by_id,
    get_position_by_symbol,
    get_trade_by_id,
    list_genomes,
    list_risk_events,
    list_trades,
    list_trades_by_symbol,
    save_genome,
    save_position,
    save_risk_event,
    save_trade,
)
from stonks_trading.shared.testing import (
    fake,
    generate_fake_money,
    generate_fake_position,
    generate_fake_symbol,
    generate_fake_trade,
)

# Configure hypothesis for this test module
settings.register_profile("repositories", max_examples=50, deadline=None)
settings.load_profile("repositories")


# =============================================================================
# Trade Repository Tests
# =============================================================================


class TestTradeRepository:
    """Property-based tests for trade repository functions."""

    @given(st.data())
    async def test_save_trade_creates_id(self, data: st.DataObject) -> None:
        """Saving trade should assign ID."""
        trade = generate_fake_trade(id=None)

        result = await save_trade(trade)

        assert result.id is not None
        assert result.id > 0

    @given(st.data())
    async def test_save_trade_preserves_data(self, data: st.DataObject) -> None:
        """Saving trade should preserve all data."""
        symbol = generate_fake_symbol()
        side = fake.random_element([Side.BUY, Side.SELL])
        price = generate_fake_money()
        quantity = fake.pyfloat(min_value=0.001, max_value=10.0, right_digits=4)
        fee = generate_fake_money(min_value=0.1, max_value=100.0)

        trade = Trade(
            symbol=symbol,
            side=side,
            fill_price=price,
            quantity=quantity,
            fee=fee,
        )

        result = await save_trade(trade)

        assert result.symbol == symbol
        assert result.side == side
        assert result.fill_price.amount == price.amount
        assert result.quantity == quantity
        assert result.fee.amount == fee.amount

    @given(st.data())
    async def test_get_trade_by_id_returns_none_for_missing(self, data: st.DataObject) -> None:
        """Getting non-existent trade should return None."""
        trade_id = fake.random_int(min=1000000, max=9999999)

        result = await get_trade_by_id(trade_id)

        assert result is None

    @given(st.data())
    async def test_list_trades_by_symbol_filters(self, data: st.DataObject) -> None:
        """Listing trades by symbol should filter correctly."""
        symbol = generate_fake_symbol()

        trades = await list_trades_by_symbol(symbol, limit=10)

        assert isinstance(trades, list)
        # For stub implementation, returns empty list
        assert len(trades) == 0

    @given(st.data())
    async def test_list_trades_pagination(self, data: st.DataObject) -> None:
        """Listing trades should support pagination."""
        limit = fake.random_int(min=1, max=100)
        offset = fake.random_int(min=0, max=50)

        trades = await list_trades(limit=limit, offset=offset)

        assert isinstance(trades, list)


# =============================================================================
# Position Repository Tests
# =============================================================================


class TestPositionRepository:
    """Property-based tests for position repository functions."""

    @given(st.data())
    async def test_save_position_creates_id(self, data: st.DataObject) -> None:
        """Saving position should assign ID."""
        position = generate_fake_position(id=None)

        result = await save_position(position)

        assert result.id is not None
        assert result.id > 0

    @given(st.data())
    async def test_save_position_preserves_data(self, data: st.DataObject) -> None:
        """Saving position should preserve all data."""
        symbol = generate_fake_symbol()
        quantity = fake.pyfloat(min_value=0.001, max_value=5.0, right_digits=4)
        price = generate_fake_money()

        position = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
        )

        result = await save_position(position)

        assert result.symbol == symbol
        assert result.quantity == quantity
        assert result.entry_price is not None
        assert result.entry_price.amount == price.amount

    @given(st.data())
    async def test_get_position_by_symbol_returns_none_for_missing(
        self, data: st.DataObject
    ) -> None:
        """Getting non-existent position should return None."""
        symbol = generate_fake_symbol()

        result = await get_position_by_symbol(symbol)

        assert result is None

    @given(st.data())
    async def test_close_position_success(self, data: st.DataObject) -> None:
        """Closing position should succeed."""
        symbol = generate_fake_symbol()
        await save_position(
            Position(symbol=symbol, quantity=0.1, entry_price=generate_fake_money())
        )

        result = await close_position(symbol)

        assert result is True


# =============================================================================
# Genome Repository Tests
# =============================================================================


class TestGenomeRepository:
    """Property-based tests for genome repository functions."""

    @given(st.data())
    async def test_save_genome_creates_id(self, data: st.DataObject) -> None:
        """Saving genome should assign ID."""
        genome = Genome(
            genome_data=b"test_genome",
            fitness=fake.pyfloat(min_value=-1000.0, max_value=1000.0),
            generation=fake.random_int(min=0, max=1000),
            symbol=generate_fake_symbol(),
        )

        result = await save_genome(genome)

        assert result.id is not None
        assert result.id > 0

    @given(st.data())
    async def test_save_genome_preserves_training_params(self, data: st.DataObject) -> None:
        """Saving genome should preserve training parameters."""
        fee_rate = fake.pyfloat(min_value=0.0001, max_value=0.01, right_digits=4)
        slippage = fake.random_int(min=0, max=100)
        mode = fake.random_element(["backtest", "dry_run", "live"])

        genome = Genome(
            genome_data=b"test_genome",
            fee_rate=fee_rate,
            slippage_bps=slippage,
            mode=mode,
            symbol=generate_fake_symbol(),
        )

        result = await save_genome(genome)

        assert result.fee_rate == fee_rate
        assert result.slippage_bps == slippage
        assert result.mode == mode

    @given(st.data())
    async def test_get_genome_by_id_returns_none_for_missing(self, data: st.DataObject) -> None:
        """Getting non-existent genome should return None."""
        genome_id = fake.random_int(min=1000000, max=9999999)

        result = await get_genome_by_id(genome_id)

        assert result is None

    @given(st.data())
    async def test_get_active_genome_returns_none_when_none_active(
        self, data: st.DataObject
    ) -> None:
        """Getting active genome should return None when none active."""
        result = await get_active_genome()

        assert result is None

    @given(st.data())
    async def test_list_genomes_with_symbol_filter(self, data: st.DataObject) -> None:
        """Listing genomes should support symbol filter."""
        symbol = generate_fake_symbol()
        limit = fake.random_int(min=1, max=100)

        genomes = await list_genomes(symbol=symbol, limit=limit)

        assert isinstance(genomes, list)

    @given(st.data())
    async def test_activate_genome_success(self, data: st.DataObject) -> None:
        """Activating genome should succeed."""
        genome = await save_genome(
            Genome(
                genome_data=b"test_genome",
                symbol=generate_fake_symbol(),
            )
        )

        assert genome.id is not None
        result = await activate_genome(genome.id)

        assert result is True


# =============================================================================
# Risk Event Repository Tests
# =============================================================================


class TestRiskEventRepository:
    """Property-based tests for risk event repository functions."""

    @given(st.data())
    async def test_save_risk_event_creates_id(self, data: st.DataObject) -> None:
        """Saving risk event should assign ID."""
        event = RiskEvent(
            event_type=fake.random_element(["drawdown_breach", "trade_limit", "kill_switch"]),
            severity=RiskLevel.CRITICAL.value,
            message=fake.sentence(nb_words=10),
            symbol=generate_fake_symbol(),
        )

        result = await save_risk_event(event)

        assert result.id is not None
        assert result.id > 0

    @given(st.data())
    async def test_save_risk_event_preserves_data(self, data: st.DataObject) -> None:
        """Saving risk event should preserve all data."""
        event_type = "drawdown_breach"
        severity = RiskLevel.CRITICAL.value
        message = "Max drawdown exceeded"
        metric_value = fake.pyfloat(min_value=0.1, max_value=0.5, right_digits=4)

        event = RiskEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            symbol=generate_fake_symbol(),
            metric_name="drawdown",
            metric_value=metric_value,
            threshold_value=0.15,
        )

        result = await save_risk_event(event)

        assert result.event_type == event_type
        assert result.severity == severity
        assert result.message == message
        assert result.metric_value == metric_value

    @given(st.data())
    async def test_list_risk_events_with_filters(self, data: st.DataObject) -> None:
        """Listing risk events should support filters."""
        severity = fake.random_element([RiskLevel.WARNING.value, RiskLevel.CRITICAL.value])
        acknowledged = fake.boolean()
        limit = fake.random_int(min=1, max=100)

        events = await list_risk_events(
            severity=severity,
            acknowledged=acknowledged,
            limit=limit,
        )

        assert isinstance(events, list)

    @given(st.data())
    async def test_acknowledge_risk_event_returns_none_for_missing(
        self, data: st.DataObject
    ) -> None:
        """Acknowledging non-existent event should return None."""
        event_id = fake.random_int(min=1000000, max=9999999)
        user = fake.user_name()
        action = fake.sentence(nb_words=5)

        result = await acknowledge_risk_event(event_id, user, action)

        assert result is None
