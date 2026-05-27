"""Unit tests for portfolio repositories."""

import pytest

from stonks_trading.domains.portfolio.entities import Portfolio
from stonks_trading.domains.portfolio.repositories import (
    get_portfolio,
    save_portfolio,
)
from stonks_trading.domains.trading.value_objects import Money


@pytest.mark.asyncio
class TestGetPortfolioRepository:
    """Tests for get_portfolio repository function."""

    async def test_get_portfolio_returns_portfolio(self):
        """get_portfolio returns a Portfolio entity."""
        portfolio = await get_portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
            current_equity=15000.0,
            currency="USDT",
        )

        assert portfolio.bot_type == "neat_swing"
        assert portfolio.bot_instance_id == "test_bot"
        assert portfolio.total_value.amount == 15000.0
        assert portfolio.cash.amount == 15000.0
        assert portfolio.positions == {}

    async def test_get_portfolio_default_values(self):
        """get_portfolio uses defaults when not specified."""
        portfolio = await get_portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
        )

        assert portfolio.total_value.amount == 10000.0
        assert portfolio.cash.currency == "USDT"


@pytest.mark.asyncio
class TestSavePortfolioRepository:
    """Tests for save_portfolio repository function."""

    async def test_save_portfolio_assigns_id(self):
        """save_portfolio assigns an ID if not present."""
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=10000.0, currency="USDT"),
            positions={},
            id=None,
        )

        saved = await save_portfolio(portfolio)

        assert saved.id is not None
        assert saved.id == 1

    async def test_save_portfolio_preserves_id(self):
        """save_portfolio preserves existing ID."""
        portfolio = Portfolio(
            bot_type="neat_swing",
            bot_instance_id="test_bot",
            total_value=Money(amount=10000.0, currency="USDT"),
            cash=Money(amount=10000.0, currency="USDT"),
            positions={},
            id=42,
        )

        saved = await save_portfolio(portfolio)

        assert saved.id == 42
