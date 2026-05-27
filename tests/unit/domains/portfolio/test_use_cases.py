"""Unit tests for portfolio use cases."""

import pytest

from stonks_trading.domains.portfolio.entities import Allocation, Portfolio
from stonks_trading.domains.portfolio.use_cases import (
    GetPortfolioUseCase,
    RebalancePortfolioUseCase,
    UpdateAllocationUseCase,
)
from stonks_trading.domains.trading.value_objects import Money


class TestGetPortfolioUseCase:
    """Tests for GetPortfolioUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = GetPortfolioUseCase()
        assert use_case.valuator is not None

    @pytest.mark.asyncio
    async def test_execute_returns_portfolio(self):
        """Execute returns portfolio from repository."""
        use_case = GetPortfolioUseCase()
        portfolio = await use_case.execute(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
        )
        assert portfolio is not None
        assert portfolio.bot_type == "neat_swing"
        assert portfolio.bot_instance_id == "test_bot"
        assert portfolio.total_value.amount == 10000.0


class TestRebalancePortfolioUseCase:
    """Tests for RebalancePortfolioUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = RebalancePortfolioUseCase()
        assert use_case.rebalancer is not None

    @pytest.mark.asyncio
    async def test_execute_returns_trades(self):
        """Execute returns rebalance trades."""
        use_case = RebalancePortfolioUseCase()
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=5000.0, currency="USDT"),
            positions={},
        )
        allocations = [
            Allocation(
                symbol="BTC_USD",
                target_pct=0.6,
                current_pct=0.0,  # Needs rebalance
                rebalance_threshold=0.05,
            ),
        ]
        prices = {"BTC_USD": 50000.0}

        trades = await use_case.execute(portfolio, allocations, prices)

        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC_USD"
        assert trades[0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_execute_no_trades_when_balanced(self):
        """Execute returns empty when no rebalance needed."""
        use_case = RebalancePortfolioUseCase()
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=4000.0, currency="USDT"),
            positions={},
        )
        allocations = [
            Allocation(
                symbol="BTC_USD",
                target_pct=0.6,
                current_pct=0.6,  # No rebalance needed
                rebalance_threshold=0.05,
            ),
        ]
        prices = {"BTC_USD": 50000.0}

        trades = await use_case.execute(portfolio, allocations, prices)

        assert len(trades) == 0


class TestUpdateAllocationUseCase:
    """Tests for UpdateAllocationUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = UpdateAllocationUseCase()
        assert use_case is not None

    @pytest.mark.asyncio
    async def test_execute_returns_allocation(self):
        """Execute returns updated allocation."""
        use_case = UpdateAllocationUseCase()
        allocation = await use_case.execute(
            portfolio_id=1,
            symbol="ETH_USD",
            target_pct=0.3,
        )

        assert allocation.symbol == "ETH_USD"
        assert allocation.target_pct == 0.3
        assert allocation.current_pct == 0
        assert allocation.portfolio_id == 1
