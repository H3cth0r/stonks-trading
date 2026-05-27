"""Unit tests for testing module utilities."""

import pytest

from stonks_trading.domains.trading.entities import Balance, Position, Trade
from stonks_trading.domains.trading.enums import Side, RiskLevel
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.testing import (
    assert_money_valid,
    assert_position_valid,
    assert_trade_valid,
    balance_strategy,
    generate_fake_money,
    generate_fake_position,
    generate_fake_symbol,
    generate_fake_trade,
    money_strategy,
    ohlcv_data_strategy,
    position_strategy,
    risk_level_strategy,
    side_strategy,
    symbol_strategy,
    trade_strategy,
)


class TestStrategyStrategies:
    """Tests for Hypothesis strategy generators."""

    def test_symbol_strategy_produces_valid_symbols(self):
        """symbol_strategy generates valid Symbol values."""
        symbols = [symbol_strategy().example() for _ in range(10)]
        for sym in symbols:
            assert isinstance(sym, Symbol)
            assert sym.value in ["BTC_USD", "ETH_USD", "XRP_USD", "SOL_USD", "ADA_USD", "DOT_USD"]

    def test_side_strategy_produces_valid_sides(self):
        """side_strategy generates valid Side values."""
        sides = [side_strategy().example() for _ in range(10)]
        for side in sides:
            assert side in [Side.BUY, Side.SELL]

    def test_risk_level_strategy_produces_valid_levels(self):
        """risk_level_strategy generates valid RiskLevel values."""
        levels = [risk_level_strategy().example() for _ in range(10)]
        for level in levels:
            assert level in [RiskLevel.OK, RiskLevel.WARNING, RiskLevel.CRITICAL, RiskLevel.EMERGENCY]

    def test_money_strategy_produces_valid_money(self):
        """money_strategy generates valid Money objects."""
        for _ in range(10):
            money = money_strategy().example()
            assert isinstance(money, Money)
            assert money.amount > 0
            assert money.currency == "USD"


class TestTradeStrategies:
    """Tests for trade-related strategies."""

    def test_trade_strategy_produces_valid_trades(self):
        """trade_strategy generates valid Trade objects."""
        for _ in range(10):
            trade = trade_strategy().example()
            assert isinstance(trade, Trade)
            assert trade.symbol is not None
            assert trade.side in [Side.BUY, Side.SELL]
            assert trade.quantity > 0

    def test_position_strategy_produces_valid_positions(self):
        """position_strategy generates valid Position objects."""
        for _ in range(10):
            pos = position_strategy().example()
            assert isinstance(pos, Position)
            assert pos.symbol is not None

    def test_balance_strategy_produces_valid_balances(self):
        """balance_strategy generates valid Balance objects."""
        for _ in range(10):
            bal = balance_strategy().example()
            assert isinstance(bal, Balance)
            assert bal.asset is not None
            assert bal.free >= 0
            assert bal.locked >= 0


class TestGenerateFakeHelpers:
    """Tests for generate_fake_* helper functions."""

    def test_generate_fake_trade_creates_valid_trade(self):
        """generate_fake_trade creates a Trade entity."""
        trade = generate_fake_trade()
        assert isinstance(trade, Trade)
        assert trade.symbol is not None
        assert trade.side in [Side.BUY, Side.SELL]

    def test_generate_fake_trade_with_overrides(self):
        """generate_fake_trade respects overrides."""
        trade = generate_fake_trade(side=Side.BUY, quantity=99.9)
        assert trade.side == Side.BUY
        assert trade.quantity == 99.9

    def test_generate_fake_position_creates_valid_position(self):
        """generate_fake_position creates a Position entity."""
        position = generate_fake_position()
        assert isinstance(position, Position)
        assert position.symbol is not None

    def test_generate_fake_money_creates_valid_money(self):
        """generate_fake_money creates a Money entity."""
        money = generate_fake_money()
        assert isinstance(money, Money)
        assert money.amount > 0
        assert len(money.currency) == 3

    def test_generate_fake_symbol_creates_valid_symbol(self):
        """generate_fake_symbol creates a Symbol entity."""
        symbol = generate_fake_symbol()
        assert isinstance(symbol, Symbol)
        assert symbol.value in ["BTC_USD", "ETH_USD", "XRP_USD", "SOL_USD", "ADA_USD"]


class TestAssertionHelpers:
    """Tests for assert_* validation helper functions."""

    def test_assert_trade_valid_with_valid_trade(self):
        """assert_trade_valid passes for valid trade."""
        trade = generate_fake_trade(
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.5,
            fee=Money(amount=10.0, currency="USD"),
        )
        assert_trade_valid(trade)  # Should not raise

    def test_assert_position_valid_with_valid_position(self):
        """assert_position_valid passes for valid position."""
        position = generate_fake_position(quantity=1.0)
        assert_position_valid(position)  # Should not raise

    def test_assert_money_valid_with_valid_money(self):
        """assert_money_valid passes for valid money."""
        money = Money(amount=1000.0, currency="USD")
        assert_money_valid(money)  # Should not raise

    def test_assert_position_valid_zero_quantity(self):
        """assert_position_valid allows zero quantity (no entry price needed)."""
        position = generate_fake_position(quantity=0.0)
        assert_position_valid(position)  # Should not raise


class TestOhlcvDataStrategy:
    """Tests for OHLCV data generation strategy."""

    def test_ohlcv_data_strategy_produces_dataframe(self):
        """ohlcv_data_strategy generates a DataFrame."""
        import pandas as pd

        df = ohlcv_data_strategy(rows=50).example()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 50
        assert "Open" in df.columns
        assert "High" in df.columns
        assert "Low" in df.columns
        assert "Close" in df.columns
        assert "Volume" in df.columns
