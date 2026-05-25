"""Tests for backtesting domain services."""

import numpy as np
import pytest

from stonks_trading.domains.backtesting.services import (
    EquityCurveAnalyzer,
    MetricsCalculator,
)


class TestMetricsCalculator:
    """Tests for MetricsCalculator service."""

    def test_calculate_sharpe_ratio(self) -> None:
        """Test Sharpe ratio calculation."""
        returns = [0.001, 0.002, -0.001, 0.003, 0.001]
        result = MetricsCalculator.calculate_sharpe_ratio(returns)

        # With consistent positive returns, Sharpe should be positive
        assert result > 0

    def test_calculate_sharpe_ratio_empty(self) -> None:
        """Test Sharpe ratio with empty returns."""
        result = MetricsCalculator.calculate_sharpe_ratio([])
        assert result == 0.0

    def test_calculate_sharpe_ratio_single(self) -> None:
        """Test Sharpe ratio with single return."""
        result = MetricsCalculator.calculate_sharpe_ratio([0.01])
        assert result == 0.0

    def test_calculate_sortino_ratio(self) -> None:
        """Test Sortino ratio calculation."""
        returns = [0.001, 0.002, -0.001, 0.003, 0.001]
        result = MetricsCalculator.calculate_sortino_ratio(returns)

        # Should be positive
        assert result > 0

    def test_calculate_sortino_ratio_no_downside(self) -> None:
        """Test Sortino ratio with no downside returns."""
        returns = [0.001, 0.002, 0.003, 0.001, 0.002]
        result = MetricsCalculator.calculate_sortino_ratio(returns)

        # Should be infinity (all positive returns)
        assert result == float("inf")

    def test_calculate_max_drawdown(self) -> None:
        """Test max drawdown calculation."""
        equity_curve = [10000.0, 11000.0, 9000.0, 9500.0, 8000.0]

        result = MetricsCalculator.calculate_max_drawdown(equity_curve)

        # Peak at 11000, trough at 8000, drawdown = (8000-11000)/11000 = -0.2727
        assert result < 0
        assert pytest.approx(result, abs=0.01) == -0.2727

    def test_calculate_max_drawdown_empty(self) -> None:
        """Test max drawdown with empty curve."""
        result = MetricsCalculator.calculate_max_drawdown([])
        assert result == 0.0

    def test_calculate_annualized_return(self) -> None:
        """Test annualized return calculation."""
        total_return = 0.15  # 15% return
        days = 180

        result = MetricsCalculator.calculate_annualized_return(total_return, days)

        # (1.15)^(365/180) - 1
        assert result > 0.15

    def test_calculate_win_rate(self) -> None:
        """Test win rate calculation."""
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": -50.0},
            {"realized_pnl": 200.0},
            {"realized_pnl": 150.0},
        ]

        result = MetricsCalculator.calculate_win_rate(trades)

        # 3 wins out of 4 trades = 75%
        assert result == 75.0

    def test_calculate_win_rate_empty(self) -> None:
        """Test win rate with no trades."""
        result = MetricsCalculator.calculate_win_rate([])
        assert result == 0.0

    def test_calculate_profit_factor(self) -> None:
        """Test profit factor calculation."""
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": -50.0},
            {"realized_pnl": 200.0},
            {"realized_pnl": -30.0},
        ]

        result = MetricsCalculator.calculate_profit_factor(trades)

        # Total wins: 300, Total losses: 80, PF = 3.75
        assert pytest.approx(result, rel=1e-3) == 3.75

    def test_calculate_profit_factor_no_losses(self) -> None:
        """Test profit factor with no losing trades."""
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": 200.0},
        ]

        result = MetricsCalculator.calculate_profit_factor(trades)

        # Should be infinity
        assert result == float("inf")

    def test_calculate_avg_win_loss(self) -> None:
        """Test average win/loss calculation."""
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": -50.0},
            {"realized_pnl": 200.0},
            {"realized_pnl": -30.0},
        ]

        avg_win, avg_loss = MetricsCalculator.calculate_avg_win_loss(trades)

        # Avg win: (100 + 200) / 2 = 150
        # Avg loss: (50 + 30) / 2 = 40
        assert avg_win == 150.0
        assert avg_loss == 40.0

    def test_calculate_alpha_beta(self) -> None:
        """Test alpha and beta calculation."""
        strategy_returns = [0.01, 0.02, -0.01, 0.015, 0.005]
        benchmark_returns = [0.005, 0.015, -0.005, 0.01, 0.005]

        alpha, beta = MetricsCalculator.calculate_alpha_beta(
            strategy_returns, benchmark_returns
        )

        # Beta should be positive (correlated)
        assert beta > 0
        # Alpha could be positive or negative
        assert isinstance(alpha, float)

    def test_calculate_alpha_beta_mismatched_lengths(self) -> None:
        """Test alpha/beta with mismatched lengths."""
        result = MetricsCalculator.calculate_alpha_beta([0.01], [0.005, 0.01])
        assert result == (0.0, 1.0)


class TestEquityCurveAnalyzer:
    """Tests for EquityCurveAnalyzer service."""

    def test_calculate_equity_returns(self) -> None:
        """Test equity returns calculation."""
        equity_curve = [10000.0, 10500.0, 10200.0, 11000.0]

        result = EquityCurveAnalyzer.calculate_equity_returns(equity_curve)

        # Returns: [(10500-10000)/10000, (10200-10500)/10500, (11000-10200)/10200]
        expected = [0.05, -0.02857, 0.07843]
        assert len(result) == 3
        assert pytest.approx(result[0], abs=0.001) == expected[0]

    def test_calculate_equity_returns_empty(self) -> None:
        """Test equity returns with empty curve."""
        result = EquityCurveAnalyzer.calculate_equity_returns([])
        assert result == []

    def test_calculate_equity_returns_single(self) -> None:
        """Test equity returns with single value."""
        result = EquityCurveAnalyzer.calculate_equity_returns([10000.0])
        assert result == []

    def test_calculate_buy_hold_return(self) -> None:
        """Test buy and hold return calculation."""
        prices = [100.0, 105.0, 102.0, 110.0]
        initial_capital = 10000.0

        result = EquityCurveAnalyzer.calculate_buy_hold_return(prices, initial_capital)

        # Buy at 100, sell at 110: (11000 - 10000) / 10000 = 10%
        assert result == 10.0

    def test_calculate_buy_hold_return_empty(self) -> None:
        """Test buy and hold return with empty prices."""
        result = EquityCurveAnalyzer.calculate_buy_hold_return([], 10000.0)
        assert result == 0.0
