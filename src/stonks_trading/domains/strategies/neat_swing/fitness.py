"""Fitness calculation extracted from NEAT/main.py lines 185-236.

This module provides the calculate_fitness function for evaluating
NEAT genomes during training.

Original source: NEAT/main.py lines 185-236
"""

from typing import Any

import numpy as np

from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv

# Reward Weights (Srivastava et al. adapted)
# These match the constants in NEAT/main.py lines 34-38
W_RETURN = 1.0
W_RISK = 0.5  # Lower risk penalty to encourage trading
W_DIFF = 3.0  # Massive bonus for beating Buy & Hold
W_TREYNOR = 1.0

# Default initial capital (matches NEAT/main.py line 27)
INITIAL_CAPITAL = 10000.0


def calculate_fitness(
    env: TradingEnv,
    equity_curve: list[float],
    market_prices: np.ndarray,
    initial_capital: float = INITIAL_CAPITAL,
    w_return: float = W_RETURN,
    w_risk: float = W_RISK,
    w_diff: float = W_DIFF,
    w_treynor: float = W_TREYNOR,
) -> float:
    """Calculate fitness score for a genome.

    Matches NEAT/main.py lines 185-236 exactly.

    The fitness function uses a composite score based on:
    1. Total Return (weighted by w_return)
    2. Downside Risk (penalized by w_risk)
    3. Differential Return vs Buy & Hold (bonus by w_diff)
    4. Treynor Ratio (bonus by w_treynor)

    Constraints applied:
    - Penalize inactivity (< 2 trades)
    - Penalize churning (> 40 trades)
    - Penalize bankruptcy (< 60% of initial capital)

    Args:
        env: TradingEnv instance with trade history
        equity_curve: List of equity values over time
        market_prices: Array of market prices for same period
        initial_capital: Starting capital amount
        w_return: Weight for return component
        w_risk: Weight for risk penalty
        w_diff: Weight for differential return
        w_treynor: Weight for Treynor ratio

    Returns:
        Fitness score (higher is better)
    """
    eq = np.array(equity_curve)

    # 1. Total Return
    total_ret = (eq[-1] - initial_capital) / initial_capital

    # 2. Downside Risk (Only bad volatility)
    rets = np.diff(eq) / eq[:-1]
    neg_rets = rets[rets < 0]
    sigma_down = np.std(neg_rets) * np.sqrt(len(eq)) if len(neg_rets) > 0 else 0.0

    # 3. Market Beta
    mkt_rets = np.diff(market_prices) / market_prices[:-1]
    min_len = min(len(rets), len(mkt_rets))

    if min_len > 10 and np.var(mkt_rets[:min_len]) > 1e-9:
        cov = np.cov(rets[:min_len], mkt_rets[:min_len])[0, 1]
        beta = cov / np.var(mkt_rets[:min_len])
    else:
        beta = 1.0
    beta = max(0.1, abs(beta))  # Avoid zero division

    # 4. Metrics
    market_ret = (market_prices[-1] - market_prices[0]) / market_prices[0]

    # Differential Return: (Strategy - Market) / Beta
    diff_ret = (total_ret - market_ret) / beta

    # Treynor: Return / Beta
    treynor = total_ret / beta

    # --- Composite Score ---
    score = (
        (w_return * total_ret * 100)
        - (w_risk * sigma_down * 100)
        + (w_diff * diff_ret * 100)
        + (w_treynor * treynor * 100)
    )

    # --- Constraints ---

    # 1. Penalize Inactivity (Must make at least 2 trades in 2 weeks)
    if len(env.trades) < 2:
        score -= 50

    # 2. Penalize Churning (More than 40 trades in 2 weeks is likely scalping,
    #    which fails with fees)
    if len(env.trades) > 40:
        score -= len(env.trades) - 40

    # 3. Bankruptcy
    if eq[-1] < initial_capital * 0.6:
        score -= 500

    return score


def calculate_metrics(
    equity_curve: list[float],
    market_prices: np.ndarray,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict[str, Any]:
    """Calculate performance metrics for reporting.

    Returns dict with:
        - total_return: Percentage return
        - market_return: Buy & hold return
        - max_drawdown: Maximum drawdown percentage
        - sharpe_ratio: Risk-adjusted return
        - beta: Market beta
    """
    eq = np.array(equity_curve)

    # Returns
    total_ret = (eq[-1] - initial_capital) / initial_capital
    market_ret = (market_prices[-1] - market_prices[0]) / market_prices[0]

    # Downside Risk
    rets = np.diff(eq) / eq[:-1]
    neg_rets = rets[rets < 0]
    sigma_down = np.std(neg_rets) * np.sqrt(len(eq)) if len(neg_rets) > 0 else 0.0

    # Beta
    mkt_rets = np.diff(market_prices) / market_prices[:-1]
    min_len = min(len(rets), len(mkt_rets))

    if min_len > 10 and np.var(mkt_rets[:min_len]) > 1e-9:
        cov = np.cov(rets[:min_len], mkt_rets[:min_len])[0, 1]
        beta = cov / np.var(mkt_rets[:min_len])
    else:
        beta = 1.0
    beta = max(0.1, abs(beta))

    # Differential and Treynor
    diff_ret = (total_ret - market_ret) / beta
    treynor = total_ret / beta

    # Max Drawdown
    peak = initial_capital
    max_dd = 0.0
    for value in eq:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "total_return": total_ret,
        "market_return": market_ret,
        "differential_return": diff_ret,
        "treynor_ratio": treynor,
        "downside_risk": sigma_down,
        "beta": beta,
        "max_drawdown": max_dd,
        "final_equity": eq[-1],
    }
