"""Property-based tests for trading use cases using Hypothesis and Faker.

These tests verify the behavior of use cases:
- ExecuteTradeUseCase
- EvaluateSignalUseCase
- MonitorRiskUseCase
- GetVenueBalancesUseCase
- GetMarketPricesUseCase
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stonks_trading.domains.trading.entities import (
    CheckRiskResult,
    ExecuteTradeResult,
)
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.services import (
    FeeCalculator,
    RiskChecker,
)
from stonks_trading.domains.trading.use_cases import (
    EvaluateSignalUseCase,
    ExecuteTradeUseCase,
    MonitorRiskUseCase,
)
from stonks_trading.domains.trading.value_objects import InstrumentMapper, Money
from stonks_trading.shared.testing import (
    fake,
    generate_fake_money,
    generate_fake_position,
    generate_fake_symbol,
)

# Configure hypothesis for this test module
settings.register_profile("use_cases", max_examples=50, deadline=None)
settings.load_profile("use_cases")


# =============================================================================
# ExecuteTradeUseCase Tests
# =============================================================================


class TestExecuteTradeUseCase:
    """Property-based tests for ExecuteTradeUseCase."""

    def setup_method(self) -> None:
        """Set up use case for each test."""
        self.use_case = ExecuteTradeUseCase(
            risk_checker=RiskChecker(
                max_position_pct=0.95,
                max_drawdown_pct=0.15,
                max_trades_per_day=40,
                min_trade_interval_minutes=15,
            ),
            fee_calculator=FeeCalculator(),
            instrument_mapper=InstrumentMapper(),
        )

    @given(st.data())
    async def test_execute_trade_successful(self, data: st.DataObject) -> None:
        """Trade execution should succeed with valid parameters."""
        symbol = generate_fake_symbol()
        side = fake.random_element([Side.BUY, Side.SELL])
        price = generate_fake_money(min_value=1000.0, max_value=100000.0)
        quantity = fake.pyfloat(min_value=0.01, max_value=1.0, right_digits=4)
        portfolio_value = generate_fake_money(min_value=10000.0, max_value=100000.0)

        result = await self.use_case.execute(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            portfolio_value=portfolio_value,
            current_position=None,
            daily_trade_count=5,
            minutes_since_last_trade=30,
            current_drawdown=0.05,
        )

        assert isinstance(result, ExecuteTradeResult)
        if result.success:
            assert result.trade is not None
            assert result.trade.symbol == symbol
            assert result.trade.side == side
            assert result.risk_check is not None
            assert result.risk_check.allowed

    @given(st.data())
    async def test_execute_trade_blocked_by_risk(self, data: st.DataObject) -> None:
        """Trade execution should be blocked when risk limits exceeded."""
        symbol = generate_fake_symbol()
        side = Side.BUY
        price = generate_fake_money(min_value=1000.0, max_value=100000.0)
        quantity = fake.pyfloat(min_value=0.01, max_value=1.0, right_digits=4)
        portfolio_value = generate_fake_money(min_value=10000.0, max_value=100000.0)

        # Exceed drawdown limit
        result = await self.use_case.execute(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            portfolio_value=portfolio_value,
            current_drawdown=0.20,  # Exceeds 15% limit
        )

        assert not result.success
        assert result.risk_check is not None
        assert not result.risk_check.allowed
        assert result.risk_check.risk_level in [RiskLevel.WARNING, RiskLevel.CRITICAL]
        assert result.error is not None

    @given(st.data())
    async def test_execute_buy_creates_position(self, data: st.DataObject) -> None:
        """Buy execution should create or update position."""
        symbol = generate_fake_symbol()
        price = generate_fake_money(min_value=1000.0, max_value=100000.0)
        quantity = fake.pyfloat(min_value=0.01, max_value=1.0, right_digits=4)
        portfolio_value = generate_fake_money(min_value=10000.0, max_value=100000.0)

        result = await self.use_case.execute(
            symbol=symbol,
            side=Side.BUY,
            quantity=quantity,
            price=price,
            portfolio_value=portfolio_value,
            current_position=None,
            daily_trade_count=5,
            minutes_since_last_trade=30,
        )

        if result.success:
            assert result.position is not None
            assert result.position.symbol == symbol
            assert result.position.quantity > 0

    @given(st.data())
    async def test_execute_sell_reduces_position(self, data: st.DataObject) -> None:
        """Sell execution should reduce position."""
        symbol = generate_fake_symbol()
        price = generate_fake_money(min_value=1000.0, max_value=100000.0)
        quantity = fake.pyfloat(min_value=0.01, max_value=0.5, right_digits=4)
        portfolio_value = generate_fake_money(min_value=10000.0, max_value=100000.0)

        # Create existing position with more quantity
        position = generate_fake_position(symbol=symbol, quantity=quantity * 2)

        result = await self.use_case.execute(
            symbol=symbol,
            side=Side.SELL,
            quantity=quantity,
            price=price,
            portfolio_value=portfolio_value,
            current_position=position,
            daily_trade_count=5,
            minutes_since_last_trade=30,
        )

        if result.success:
            assert result.position is not None
            assert result.position.quantity == quantity  # Reduced by sell amount


# =============================================================================
# EvaluateSignalUseCase Tests
# =============================================================================


class TestEvaluateSignalUseCase:
    """Property-based tests for EvaluateSignalUseCase."""

    def setup_method(self) -> None:
        """Set up use case for each test."""
        self.use_case = EvaluateSignalUseCase(
            risk_checker=RiskChecker(),
            decision_threshold=0.6,
        )

    @given(st.data())
    def test_buy_signal_confident(self, data: st.DataObject) -> None:
        """Strong buy signal should return BUY action."""
        buy_prob = fake.pyfloat(min_value=0.61, max_value=1.0, right_digits=4)
        sell_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)

        position = generate_fake_position(quantity=0.0)  # No position
        portfolio_value = generate_fake_money()

        result = self.use_case.evaluate(
            buy_prob=buy_prob,
            sell_prob=sell_prob,
            current_position=position,
            portfolio_value=portfolio_value,
        )

        assert result.action == Side.BUY
        assert result.should_trade is True
        assert result.confidence == buy_prob

    @given(st.data())
    def test_sell_signal_confident(self, data: st.DataObject) -> None:
        """Strong sell signal should return SELL action."""
        buy_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)
        sell_prob = fake.pyfloat(min_value=0.61, max_value=1.0, right_digits=4)

        position = generate_fake_position(quantity=1.0)  # Has position
        portfolio_value = generate_fake_money()

        result = self.use_case.evaluate(
            buy_prob=buy_prob,
            sell_prob=sell_prob,
            current_position=position,
            portfolio_value=portfolio_value,
        )

        assert result.action == Side.SELL
        assert result.should_trade is True
        assert result.confidence == sell_prob

    @given(st.data())
    def test_no_signal_below_threshold(self, data: st.DataObject) -> None:
        """Weak signals should return no action."""
        buy_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)
        sell_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)

        position = generate_fake_position()
        portfolio_value = generate_fake_money()

        result = self.use_case.evaluate(
            buy_prob=buy_prob,
            sell_prob=sell_prob,
            current_position=position,
            portfolio_value=portfolio_value,
        )

        assert result.action is None
        assert result.should_trade is False
        assert result.reason is not None

    @given(st.data())
    def test_buy_blocked_when_in_position(self, data: st.DataObject) -> None:
        """Buy should be blocked when already in position."""
        buy_prob = fake.pyfloat(min_value=0.61, max_value=1.0, right_digits=4)
        sell_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)

        position = generate_fake_position(quantity=1.0)  # Already in position
        portfolio_value = generate_fake_money()

        result = self.use_case.evaluate(
            buy_prob=buy_prob,
            sell_prob=sell_prob,
            current_position=position,
            portfolio_value=portfolio_value,
        )

        assert result.action == Side.BUY  # Signal is BUY
        assert result.should_trade is False  # But shouldn't trade
        assert result.reason is not None

    @given(st.data())
    def test_sell_blocked_when_no_position(self, data: st.DataObject) -> None:
        """Sell should be blocked when no position."""
        buy_prob = fake.pyfloat(min_value=0.0, max_value=0.59, right_digits=4)
        sell_prob = fake.pyfloat(min_value=0.61, max_value=1.0, right_digits=4)

        position = generate_fake_position(quantity=0.0)  # No position
        portfolio_value = generate_fake_money()

        result = self.use_case.evaluate(
            buy_prob=buy_prob,
            sell_prob=sell_prob,
            current_position=position,
            portfolio_value=portfolio_value,
        )

        assert result.action == Side.SELL  # Signal is SELL
        assert result.should_trade is False  # But shouldn't trade
        assert result.reason is not None


# =============================================================================
# MonitorRiskUseCase Tests
# =============================================================================


class TestMonitorRiskUseCase:
    """Property-based tests for MonitorRiskUseCase."""

    def setup_method(self) -> None:
        """Set up use case for each test."""
        self.use_case = MonitorRiskUseCase(
            risk_checker=RiskChecker(max_drawdown_pct=0.15),
        )

    @given(st.data())
    async def test_risk_check_returns_valid_result(self, data: st.DataObject) -> None:
        """Risk check should always return a valid CheckRiskResult."""
        current_equity = generate_fake_money(min_value=1000.0, max_value=50000.0)
        peak_equity = generate_fake_money(min_value=1000.0, max_value=50000.0)
        daily_trades = fake.random_int(min=0, max=50)
        symbol = generate_fake_symbol()

        result = await self.use_case.check(
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_trade_count=daily_trades,
            symbol=symbol,
        )

        assert isinstance(result, CheckRiskResult)
        # Result should have a valid status
        assert result.status in [
            RiskLevel.OK,
            RiskLevel.WARNING,
            RiskLevel.CRITICAL,
            RiskLevel.EMERGENCY,
        ]
        # should_halt should be a boolean
        assert isinstance(result.should_halt, bool)

    @given(st.data())
    async def test_risk_check_critical_drawdown(self, data: st.DataObject) -> None:
        """Risk check should return critical for high drawdown."""
        peak_equity = generate_fake_money(min_value=10000.0, max_value=20000.0)
        # 20% drawdown (exceeds 15% limit)
        current_equity = Money(amount=peak_equity.amount * 0.80, currency="USD")
        daily_trades = fake.random_int(min=0, max=39)

        result = await self.use_case.check(
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_trade_count=daily_trades,
            symbol=generate_fake_symbol(),
        )

        assert result.status == RiskLevel.CRITICAL
        assert result.should_halt is True
        assert len(result.events) > 0
        assert any(e.severity == RiskLevel.CRITICAL.value for e in result.events)

    @given(st.data())
    async def test_risk_check_warning_drawdown(self, data: st.DataObject) -> None:
        """Risk check should return warning for near-limit drawdown."""
        peak_equity = generate_fake_money(min_value=10000.0, max_value=20000.0)
        # 13% drawdown (above 80% of 15% limit)
        current_equity = Money(amount=peak_equity.amount * 0.87, currency="USD")
        daily_trades = fake.random_int(min=0, max=39)

        result = await self.use_case.check(
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_trade_count=daily_trades,
            symbol=generate_fake_symbol(),
        )

        assert result.status == RiskLevel.WARNING
        assert len(result.events) > 0

    @given(st.data())
    async def test_risk_check_trade_limit(self, data: st.DataObject) -> None:
        """Risk check should warn when daily trade limit reached."""
        current_equity = generate_fake_money(min_value=9000.0, max_value=10000.0)
        peak_equity = generate_fake_money(min_value=10000.0, max_value=12000.0)
        daily_trades = fake.random_int(min=40, max=100)  # At or above limit

        result = await self.use_case.check(
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_trade_count=daily_trades,
            symbol=generate_fake_symbol(),
        )

        assert result.status in [RiskLevel.WARNING, RiskLevel.CRITICAL]
        assert any(e.event_type == "trade_limit" for e in result.events)


# =============================================================================
# GetVenueBalancesUseCase Tests
# =============================================================================


class TestGetVenueBalancesUseCase:
    """Tests for GetVenueBalancesUseCase."""

    @pytest.mark.asyncio
    async def test_execute_returns_venue_balances(self) -> None:
        """Use case should return venue balances with correct structure."""
        from unittest.mock import AsyncMock, MagicMock

        from stonks_trading.domains.trading.adapters import IExchangeAdapter
        from stonks_trading.domains.trading.use_cases import (
            GetVenueBalancesUseCase,
        )

        # Create mock adapter
        mock_adapter = MagicMock(spec=IExchangeAdapter)
        mock_balance = MagicMock()
        mock_balance.asset = "USDT"
        mock_balance.free = 10000.0
        mock_balance.locked = 0.0
        mock_balance.total = 10000.0
        mock_adapter.get_balance = AsyncMock(return_value=[mock_balance])

        use_case = GetVenueBalancesUseCase(mock_adapter)
        result = await use_case.execute()

        assert isinstance(result, list)
        assert len(result) > 0
        assert "venue" in result[0]
        assert "balances" in result[0]
        assert "synced_at" in result[0]
        assert result[0]["venue"] == "default"

    @pytest.mark.asyncio
    async def test_execute_groups_by_venue(self) -> None:
        """Use case should group balances by venue."""
        from unittest.mock import AsyncMock, MagicMock

        from stonks_trading.domains.trading.adapters import IExchangeAdapter
        from stonks_trading.domains.trading.use_cases import (
            GetVenueBalancesUseCase,
        )

        # Create mock adapter with multiple balances
        mock_adapter = MagicMock(spec=IExchangeAdapter)
        mock_balance1 = MagicMock()
        mock_balance1.asset = "USDT"
        mock_balance1.free = 10000.0
        mock_balance1.locked = 0.0
        mock_balance1.total = 10000.0
        mock_balance2 = MagicMock()
        mock_balance2.asset = "BTC"
        mock_balance2.free = 0.5
        mock_balance2.locked = 0.0
        mock_balance2.total = 0.5
        mock_adapter.get_balance = AsyncMock(return_value=[mock_balance1, mock_balance2])

        use_case = GetVenueBalancesUseCase(mock_adapter)
        result = await use_case.execute()

        assert len(result) == 1  # One venue
        assert len(result[0]["balances"]) == 2  # Two assets


# =============================================================================
# GetMarketPricesUseCase Tests
# =============================================================================


class TestGetMarketPricesUseCase:
    """Tests for GetMarketPricesUseCase."""

    @pytest.mark.asyncio
    async def test_execute_returns_prices(self) -> None:
        """Use case should return prices for symbols."""
        from unittest.mock import AsyncMock, MagicMock

        from stonks_trading.domains.trading.adapters import IExchangeAdapter
        from stonks_trading.domains.trading.use_cases import (
            GetMarketPricesUseCase,
        )
        from stonks_trading.domains.trading.value_objects import Money, Symbol

        # Create mock adapter
        mock_adapter = MagicMock(spec=IExchangeAdapter)
        mock_adapter.get_price = AsyncMock(return_value=Money(amount=50000.0, currency="USDT"))

        use_case = GetMarketPricesUseCase(mock_adapter)
        symbols = [Symbol(value="BTC_USDT")]
        result = await use_case.execute(symbols)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["symbol"] == "BTC_USDT"
        assert result[0]["price"] == 50000.0
        assert "timestamp" in result[0]

    @pytest.mark.asyncio
    async def test_execute_skips_failed_symbols(self) -> None:
        """Use case should skip symbols that fail to fetch."""
        from unittest.mock import AsyncMock, MagicMock

        from stonks_trading.domains.trading.adapters import IExchangeAdapter
        from stonks_trading.domains.trading.use_cases import (
            GetMarketPricesUseCase,
        )
        from stonks_trading.domains.trading.value_objects import Money, Symbol

        # Create mock adapter that fails for one symbol
        mock_adapter = MagicMock(spec=IExchangeAdapter)
        mock_adapter.get_price = AsyncMock(
            side_effect=[
                Money(amount=50000.0, currency="USDT"),
                Exception("Failed"),
            ]
        )

        use_case = GetMarketPricesUseCase(mock_adapter)
        symbols = [Symbol(value="BTC_USDT"), Symbol(value="ETH_USDT")]
        result = await use_case.execute(symbols)

        assert len(result) == 1  # Only one successful
        assert result[0]["symbol"] == "BTC_USDT"
