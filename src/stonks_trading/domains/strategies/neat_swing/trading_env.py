"""Trading environment extracted from NEAT/main.py lines 97-179.

This module provides the TradingEnv class with configurable parameters
while maintaining parity with the original NEAT/main.py behavior.

Original source: NEAT/main.py lines 97-179

Key difference from original:
    - fee_rate is configurable (default 0.001 matches TRANSACTION_FEE)
    - slippage_bps for dry-run mode (default 0 for parity)
    - mode parameter for backtest/dry_run/live behavior

Parity guarantee:
    With fee_rate=0.001, slippage_bps=0, mode="backtest",
    this produces identical results to NEAT/main.py.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from stonks_trading.domains.strategies.neat_swing.features import get_feature_columns


@dataclass
class TradeRecord:
    """Record of a trade execution.

    Mirrors the trade dict structure in NEAT/main.py:
    {'step': step, 'type': 'buy'|'sell', 'price': price, 'time': date}
    """

    step: int
    trade_type: str  # 'buy' or 'sell'
    price: float
    timestamp: datetime
    fee_paid: float = 0.0
    quantity: float = 0.0
    cash_after: float = 0.0
    holdings_after: float = 0.0


class TradingEnv:
    """Trading environment for NEAT training and simulation.

    Extracted from NEAT/main.py lines 97-179 with the following
    configurable parameters added:
        - fee_rate: Transaction fee rate (default 0.001 = 0.1%)
        - slippage_bps: Slippage in basis points (default 0)
        - mode: "backtest", "dry_run", or "live"

    With default parameters (fee_rate=0.001, slippage_bps=0),
    this produces identical results to the original NEAT/main.py.

    Attributes:
        data: DataFrame with OHLCV and engineered features
        fee_rate: Transaction fee rate per trade leg
        slippage_bps: Slippage in basis points (for dry-run simulation)
        mode: Trading mode ("backtest", "dry_run", "live")
        initial_capital: Starting cash amount
        min_trade_interval: Minimum steps between trades
        decision_threshold: Probability threshold for actions
    """

    def __init__(
        self,
        data: pd.DataFrame,
        fee_rate: float = 0.001,  # Matches TRANSACTION_FEE in NEAT/main.py
        slippage_bps: float = 0.0,  # Default 0 for parity with original
        mode: str = "backtest",
        initial_capital: float = 10000.0,
        min_trade_interval: int = 15,
        decision_threshold: float = 0.6,
    ):
        self.data = data
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.mode = mode
        self.initial_capital = initial_capital
        self.min_trade_interval = min_trade_interval
        self.decision_threshold = decision_threshold

        # Initialize state
        self.reset()

    def reset(self) -> None:
        """Reset environment to initial state.

        Matches NEAT/main.py lines 102-113.
        """
        self.cash: float = self.initial_capital
        self.holdings: float = 0.0
        self.trades: list[TradeRecord] = []
        self.peak_equity: float = self.initial_capital
        self.max_drawdown: float = 0.0
        self.last_trade_step: int = 0
        self.entry_price: float = 0.0

        # Cache price data for performance
        self.closes: np.ndarray = self.data["Close"].values
        self.dates: pd.DatetimeIndex = self.data.index

        # Cache feature columns
        feature_cols = get_feature_columns()
        self.feats: np.ndarray = self.data[feature_cols].values

    def get_state(self, step: int) -> np.ndarray:
        """Get NEAT network inputs for given step.

        Matches NEAT/main.py lines 117-136.

        Returns 7 inputs:
            [is_invested (1/-1), unrealized_pnl, trend_1h, rsi_1h,
             rsi_15m, roc, bb_width]

        Args:
            step: Current step index in the data

        Returns:
            Array of 7 clipped and cleaned inputs
        """
        price = self.closes[step]

        # Calculate Unrealized PnL % (Crucial for Profit Taking)
        unrealized_pnl = (price - self.entry_price) / self.entry_price if self.holdings > 0 else 0.0

        # Is Invested? (Binary 1.0 or -1.0)
        is_invested = 1.0 if self.holdings > 0 else -1.0

        # Market Feats
        mkt = self.feats[step]

        # Combine [Invested, Unr_PnL, 5 Market Indicators] = 7 Inputs
        state = np.hstack(([is_invested, unrealized_pnl], mkt))

        # Clean inputs
        return np.nan_to_num(np.clip(state, -5.0, 5.0))

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price for dry-run simulation.

        In backtest mode (original), slippage is 0.
        In dry-run mode, simulates realistic fill prices.
        """
        if self.mode == "backtest" or self.slippage_bps == 0:
            return price

        # Convert bps to multiplier (e.g., 5 bps = 0.0005)
        slippage_pct = self.slippage_bps / 10000.0

        if side == "buy":
            # Buy at slightly higher price
            return price * (1 + slippage_pct)
        else:
            # Sell at slightly lower price
            return price * (1 - slippage_pct)

    def step(self, step: int, action: tuple[float, float]) -> float:
        """Execute one step of the trading environment.

        Matches NEAT/main.py lines 138-179.

        Action format: (buy_prob, sell_prob) - softmax-style probabilities

        Trading logic (matches original):
        1. Calculate equity and update drawdown
        2. Check minimum trade interval
        3. Buy if: buy_prob > threshold AND buy_prob > sell_prob AND cash > 10
        4. Sell if: sell_prob > threshold AND sell_prob > buy_prob AND holdings > 0
        5. All-in / All-out position sizing

        Args:
            step: Current step index
            action: Tuple of (buy_prob, sell_prob)

        Returns:
            Current equity (cash + holdings * price)
        """
        # Action: [Buy, Sell] (Probabilities)
        buy_prob, sell_prob = action
        price = self.closes[step]

        # Calculate Equity
        equity = self.cash + (self.holdings * price)

        # Update Drawdown
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity
        if dd > self.max_drawdown:
            self.max_drawdown = dd

        # Interval Constraint
        if step - self.last_trade_step < self.min_trade_interval:
            return equity

        # --- LOGIC: All-in / All-out ---

        # Buy Signal
        if buy_prob > self.decision_threshold and buy_prob > sell_prob:
            if self.cash > 10:  # If we have cash, go All-In
                # Apply slippage for dry-run mode
                fill_price = self._apply_slippage(price, "buy")

                cost = self.cash
                fee = cost * self.fee_rate
                self.holdings = (cost - fee) / fill_price
                self.cash = 0.0
                self.entry_price = fill_price
                self.last_trade_step = step

                self.trades.append(
                    TradeRecord(
                        step=step,
                        trade_type="buy",
                        price=fill_price,
                        timestamp=self.dates[step],
                        fee_paid=fee,
                        quantity=self.holdings,
                        cash_after=self.cash,
                        holdings_after=self.holdings,
                    )
                )

        # Sell Signal
        elif sell_prob > self.decision_threshold and sell_prob > buy_prob and self.holdings > 0:
            # Apply slippage for dry-run mode
            fill_price = self._apply_slippage(price, "sell")

            val = self.holdings * fill_price
            fee = val * self.fee_rate
            self.cash = val - fee
            quantity_sold = self.holdings
            self.holdings = 0.0
            self.entry_price = 0.0
            self.last_trade_step = step

            self.trades.append(
                TradeRecord(
                    step=step,
                    trade_type="sell",
                    price=fill_price,
                    timestamp=self.dates[step],
                    fee_paid=fee,
                    quantity=quantity_sold,
                    cash_after=self.cash,
                    holdings_after=self.holdings,
                )
            )

        return self.cash + (self.holdings * price)

    def get_equity(self, step: int) -> float:
        """Calculate equity at given step without executing action."""
        price = self.closes[step]
        return self.cash + (self.holdings * price)

    def get_position_summary(self, step: int) -> dict[str, Any]:
        """Get summary of current position state."""
        price = self.closes[step]
        equity = self.get_equity(step)

        unrealized_pnl = 0.0
        if self.holdings > 0 and self.entry_price > 0:
            unrealized_pnl = (price - self.entry_price) / self.entry_price

        return {
            "cash": self.cash,
            "holdings": self.holdings,
            "holdings_value": self.holdings * price,
            "equity": equity,
            "entry_price": self.entry_price,
            "current_price": price,
            "unrealized_pnl_pct": unrealized_pnl,
            "max_drawdown": self.max_drawdown,
            "total_trades": len(self.trades),
            "is_invested": self.holdings > 0,
        }

    def get_trade_stats(self) -> dict[str, Any]:
        """Get statistics about executed trades."""
        if not self.trades:
            return {
                "total_trades": 0,
                "buys": 0,
                "sells": 0,
                "total_fees": 0.0,
            }

        buys = [t for t in self.trades if t.trade_type == "buy"]
        sells = [t for t in self.trades if t.trade_type == "sell"]
        total_fees = sum(t.fee_paid for t in self.trades)

        return {
            "total_trades": len(self.trades),
            "buys": len(buys),
            "sells": len(sells),
            "total_fees": total_fees,
            "avg_buy_price": (sum(t.price for t in buys) / len(buys) if buys else 0),
            "avg_sell_price": (sum(t.price for t in sells) / len(sells) if sells else 0),
        }
