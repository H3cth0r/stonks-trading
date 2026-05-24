"""Backtesting domain services - SIMULATION AND CALCULATIONS.

Services handle:
- Metrics calculation (Sharpe, Sortino, Max Drawdown, etc.)
- Equity curve analysis
- Trade statistics

Business logic belongs in use_cases.py - not here.

Service rules (per architecture.md):
- Classes allowed for service layer
- No business logic - only calculations and external calls
"""

from typing import Any

import numpy as np


class MetricsCalculator:
    """Calculate backtest metrics from simulation results."""

    @staticmethod
    def calculate_sharpe_ratio(
        returns: list[float],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> float:
        """Calculate Sharpe ratio.

        Args:
            returns: List of periodic returns
            risk_free_rate: Risk-free rate (annual)
            periods_per_year: Number of periods per year (252 for daily)

        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate / periods_per_year

        std = np.std(excess_returns)
        if std == 0:
            return 0.0

        return float(np.mean(excess_returns) / std * np.sqrt(periods_per_year))

    @staticmethod
    def calculate_sortino_ratio(
        returns: list[float],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> float:
        """Calculate Sortino ratio (downside deviation only).

        Args:
            returns: List of periodic returns
            risk_free_rate: Risk-free rate (annual)
            periods_per_year: Number of periods per year

        Returns:
            Annualized Sortino ratio
        """
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate / periods_per_year

        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) == 0:
            return float("inf") if np.mean(excess_returns) > 0 else 0.0

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return float("inf") if np.mean(excess_returns) > 0 else 0.0

        return float(np.mean(excess_returns) / downside_std * np.sqrt(periods_per_year))

    @staticmethod
    def calculate_max_drawdown(equity_curve: list[float]) -> float:
        """Calculate maximum drawdown percentage.

        Args:
            equity_curve: List of equity values over time

        Returns:
            Maximum drawdown as negative percentage (e.g., -0.15 for 15%)
        """
        if len(equity_curve) < 2:
            return 0.0

        equity = np.array(equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        return float(np.min(drawdown))

    @staticmethod
    def calculate_annualized_return(
        total_return: float,
        days: int,
    ) -> float:
        """Calculate annualized return.

        Args:
            total_return: Total return as decimal (e.g., 0.15 for 15%)
            days: Number of days in the period

        Returns:
            Annualized return as decimal
        """
        if days <= 0:
            return 0.0

        years = days / 365.0
        if years == 0:
            return 0.0

        return float((1 + total_return) ** (1 / years) - 1)

    @staticmethod
    def calculate_win_rate(trades: list[dict[str, Any]]) -> float:
        """Calculate win rate percentage.

        Args:
            trades: List of trade dicts with 'realized_pnl' key

        Returns:
            Win rate as percentage (0-100)
        """
        if not trades:
            return 0.0

        winning_trades = sum(1 for t in trades if t.get("realized_pnl", 0) > 0)
        return float(winning_trades / len(trades) * 100)

    @staticmethod
    def calculate_profit_factor(trades: list[dict[str, Any]]) -> float:
        """Calculate profit factor (gross profit / gross loss).

        Args:
            trades: List of trade dicts with 'realized_pnl' key

        Returns:
            Profit factor ratio
        """
        if not trades:
            return 0.0

        gross_profit = sum(t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) > 0)
        gross_loss = abs(
            sum(t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) < 0)
        )

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0

        return float(gross_profit / gross_loss)

    @staticmethod
    def calculate_avg_win_loss(trades: list[dict[str, Any]]) -> tuple[float, float]:
        """Calculate average win and average loss.

        Args:
            trades: List of trade dicts with 'realized_pnl' key

        Returns:
            Tuple of (avg_win, avg_loss)
        """
        if not trades:
            return 0.0, 0.0

        winning_trades = [t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) > 0]
        losing_trades = [t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) < 0]

        avg_win = float(np.mean(winning_trades)) if winning_trades else 0.0
        avg_loss = float(np.mean(losing_trades)) if losing_trades else 0.0

        return avg_win, abs(avg_loss)

    @staticmethod
    def calculate_alpha_beta(
        strategy_returns: list[float],
        benchmark_returns: list[float],
    ) -> tuple[float, float]:
        """Calculate alpha and beta against a benchmark.

        Args:
            strategy_returns: List of strategy periodic returns
            benchmark_returns: List of benchmark periodic returns

        Returns:
            Tuple of (alpha, beta)
        """
        if len(strategy_returns) != len(benchmark_returns) or len(strategy_returns) < 2:
            return 0.0, 1.0

        strat_arr = np.array(strategy_returns)
        bench_arr = np.array(benchmark_returns)

        # Beta = Cov(strategy, benchmark) / Var(benchmark)
        covariance = np.cov(strat_arr, bench_arr)[0][1]
        variance = np.var(bench_arr)

        beta = covariance / variance if variance != 0 else 1.0

        # Alpha = Mean(strategy) - Beta * Mean(benchmark)
        alpha = np.mean(strat_arr) - beta * np.mean(bench_arr)

        # Annualize alpha
        alpha_annualized = alpha * 252

        return float(alpha_annualized), float(beta)


class EquityCurveAnalyzer:
    """Analyze equity curve for additional insights."""

    @staticmethod
    def calculate_equity_returns(equity_curve: list[float]) -> list[float]:
        """Calculate periodic returns from equity curve.

        Args:
            equity_curve: List of equity values

        Returns:
            List of periodic returns
        """
        if len(equity_curve) < 2:
            return []

        equity = np.array(equity_curve)
        returns = np.diff(equity) / equity[:-1]

        return returns.tolist()

    @staticmethod
    def calculate_buy_hold_return(prices: list[float], initial_capital: float) -> float:
        """Calculate buy-and-hold return for comparison.

        Args:
            prices: List of prices over time
            initial_capital: Starting capital

        Returns:
            Buy-hold return as percentage
        """
        if len(prices) < 2:
            return 0.0

        initial_price = prices[0]
        final_price = prices[-1]

        shares = initial_capital / initial_price
        final_value = shares * final_price

        return float((final_value - initial_capital) / initial_capital * 100)
