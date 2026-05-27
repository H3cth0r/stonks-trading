"""Unit tests for portfolio entities."""

import pytest

from stonks_trading.domains.portfolio.entities import Allocation, Portfolio
from stonks_trading.domains.portfolio.services import PortfolioValuator, Rebalancer
from stonks_trading.domains.trading.value_objects import Money


class TestPortfolio:
    """Test Portfolio entity."""

    def test_creation(self):
        """Portfolio can be created."""
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=10000.0, currency="USDT"),
        )
        assert portfolio.bot_type == "neat_swing"
        assert portfolio.total_value.amount == 10000.0

    def test_total_equity(self):
        """total_equity calculates cash + positions."""
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=6000.0, currency="USDT"),
            positions={},
        )
        equity = portfolio.total_equity()
        assert equity.amount == 6000.0


class TestAllocation:
    """Test Allocation entity."""

    def test_creation(self):
        """Allocation can be created."""
        alloc = Allocation(
            symbol="BTC_USD",
            target_pct=0.5,
            current_pct=0.4,
        )
        assert alloc.symbol == "BTC_USD"
        assert alloc.target_pct == 0.5
        assert alloc.current_pct == 0.4

    def test_needs_rebalance(self):
        """needs_rebalance returns true when drift exceeds threshold."""
        alloc = Allocation(
            symbol="BTC_USD",
            target_pct=0.5,
            current_pct=0.4,
            rebalance_threshold=0.05,
        )
        assert alloc.needs_rebalance() is True

    def test_no_rebalance_needed(self):
        """needs_rebalance returns false when within threshold."""
        alloc = Allocation(
            symbol="BTC_USD",
            target_pct=0.5,
            current_pct=0.52,
            rebalance_threshold=0.05,
        )
        assert not alloc.needs_rebalance()

    def test_drift(self):
        """drift calculates deviation from target."""
        alloc = Allocation(
            symbol="BTC_USD",
            target_pct=0.5,
            current_pct=0.45,
        )
        assert alloc.drift() == pytest.approx(-0.05)


class TestPortfolioValuator:
    """Test PortfolioValuator service."""

    def test_calculate_position_value(self):
        valuator = PortfolioValuator()
        value = valuator.calculate_position_value(
            quantity=1.0,
            current_price=50000.0,
        )
        assert value.amount == 50000.0
        assert value.currency == "USDT"

    def test_calculate_total_value(self):
        valuator = PortfolioValuator()
        total = valuator.calculate_total_value(
            cash=Money(amount=5000.0, currency="USDT"),
            positions=[{"symbol": "BTC_USD", "quantity": 0.1}],
            prices={"BTC_USD": 50000.0},
        )
        assert total.amount == 10000.0


class TestRebalancer:
    """Test Rebalancer service."""

    def test_calculate_target_position(self):
        rebalancer = Rebalancer()
        qty = rebalancer.calculate_target_position(
            total_equity=10000.0,
            target_pct=0.5,
            current_price=50000.0,
        )
        assert qty == 0.1

    def test_calculate_rebalance_trades_empty(self):
        rebalancer = Rebalancer()
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=10000.0, currency="USDT"),
        )
        allocations = [
            Allocation(
                symbol="BTC_USD",
                target_pct=0.5,
                current_pct=0.5,
            ),
        ]
        trades = rebalancer.calculate_rebalance_trades(
            portfolio, allocations, {"BTC_USD": 50000.0}
        )
        assert len(trades) == 0
