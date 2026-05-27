"""Periodic reporter extracted from NEAT/main.py lines 261-334.

This module provides the PeriodicReporter class for monitoring
NEAT training progress and generating reports.

Original source: NEAT/main.py lines 261-334
"""

import os
import pickle
from typing import Any

import neat
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv


class PeriodicReporter(neat.reporting.BaseReporter):
    """Reporter that validates and reports on training progress.

    Matches NEAT/main.py lines 261-334.

    Features:
    - Validates best genome each generation on held-out data
    - Saves checkpoints every generation
    - Tracks all-time best genome
    - Generates Plotly HTML reports every 5 generations
    """

    def __init__(
        self,
        val_data: pd.DataFrame,
        initial_capital: float = 10000.0,
        checkpoint_dir: str = "checkpoints",
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize reporter.

        Args:
            val_data: Validation dataset (held-out 2-week slice)
            initial_capital: Starting capital for validation
            checkpoint_dir: Directory to save genome checkpoints
            fee_rate: Transaction fee rate for validation
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.val_data = val_data
        self.initial_capital = initial_capital
        self.checkpoint_dir = checkpoint_dir
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

        self.gen = 0
        self.best_all_time_roi = -float("inf")

        # Ensure checkpoints directory exists
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)

    def start_generation(self, generation: int) -> None:
        """Called at start of each generation."""
        self.gen = generation

    def post_evaluate(
        self,
        config: neat.Config,
        population: Any,
        species: Any,
        best_genome: neat.DefaultGenome,
    ) -> None:
        """Called after population evaluation.

        Validates best genome on validation data and generates reports.
        """
        net = neat.nn.RecurrentNetwork.create(best_genome, config)
        env = TradingEnv(
            self.val_data,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            initial_capital=self.initial_capital,
        )

        hist_eq = []
        hist_cash = []
        hist_holdings = []

        for i in range(len(self.val_data)):
            inputs = env.get_state(i)
            action = net.activate(inputs)
            eq = env.step(i, action)
            hist_eq.append(eq)
            hist_cash.append(env.cash)
            hist_holdings.append(env.holdings * env.closes[i])

        roi = (hist_eq[-1] - self.initial_capital) / self.initial_capital * 100

        # --- Save Current Generation Best ---
        checkpoint_path = os.path.join(self.checkpoint_dir, f"gen_{self.gen}_best.pkl")
        with open(checkpoint_path, "wb") as f:
            pickle.dump(best_genome, f)

        # --- Check for All-Time Best ---
        if roi > self.best_all_time_roi:
            self.best_all_time_roi = roi
            print(f"   >>> NEW ALL-TIME BEST! ROI: {roi:.2f}% (Saved to best_all_time.pkl) <<<")
            with open("best_all_time.pkl", "wb") as f:
                pickle.dump(best_genome, f)

        print(f"\n[{self.gen}] Best Genome Validation:")
        print(f"   > Equity:   ${hist_eq[-1]:,.2f} ({roi:+.2f}%)")
        print(f"   > Trades:   {len(env.trades)}")
        print(f"   > Max DD:   {env.max_drawdown * 100:.2f}%")

        if self.gen % 5 == 0:
            self.plot(env, hist_eq, hist_cash, hist_holdings)

    def plot(
        self,
        env: TradingEnv,
        equity: list[float],
        cash: list[float],
        holdings: list[float],
    ) -> str:
        """Generate Plotly HTML report.

        Matches NEAT/main.py lines 311-334.

        Returns:
            Path to saved HTML file
        """
        df = self.val_data
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(
                "Equity vs Buy&Hold",
                "Cash",
                "Holdings Value",
            ),
        )

        bh = (df["Close"] / df.iloc[0]["Close"]) * self.initial_capital
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=bh,
                name="Buy & Hold",
                line={"color": "gray", "dash": "dot"},
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=equity,
                name="Strategy",
                line={"color": "purple"},
            ),
            row=1,
            col=1,
        )

        # Trade Markers
        buys = [t for t in env.trades if t.trade_type == "buy"]
        sells = [t for t in env.trades if t.trade_type == "sell"]

        if buys:
            fig.add_trace(
                go.Scatter(
                    x=[t.timestamp for t in buys],
                    y=[equity[t.step] for t in buys],
                    mode="markers",
                    marker={"symbol": "triangle-up", "color": "lime", "size": 8},
                    name="Buy",
                ),
                row=1,
                col=1,
            )
        if sells:
            fig.add_trace(
                go.Scatter(
                    x=[t.timestamp for t in sells],
                    y=[equity[t.step] for t in sells],
                    mode="markers",
                    marker={"symbol": "triangle-down", "color": "red", "size": 8},
                    name="Sell",
                ),
                row=1,
                col=1,
            )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=cash,
                name="Cash",
                line={"color": "green"},
                fill="tozeroy",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=holdings,
                name="Holdings",
                line={"color": "orange"},
                fill="tozeroy",
            ),
            row=3,
            col=1,
        )

        fig.update_layout(
            title=f"Generation {self.gen} Report",
            template="plotly_dark",
            height=1000,
        )

        report_path = f"Gen_{self.gen}_Report.html"
        fig.write_html(report_path)
        print(f"   > Plot saved: {report_path}")

        return report_path


def test_genome(
    genome: neat.DefaultGenome,
    config: neat.Config,
    test_data: pd.DataFrame,
    label: str,
    initial_capital: float = 10000.0,
    fee_rate: float = 0.001,
    decision_threshold: float = 0.6,
    min_trade_interval: int = 15,
) -> float:
    """Helper to run a test on a specific genome.

    Matches NEAT/main.py lines 423-448.

    Args:
        genome: NEAT genome to test
        config: NEAT configuration
        test_data: Test dataset
        label: Label for this test (used in reporting)
        initial_capital: Starting capital
        fee_rate: Transaction fee rate
        decision_threshold: Probability threshold for trades
        min_trade_interval: Minimum steps between trades

    Returns:
        Final ROI percentage
    """
    from tqdm import tqdm

    print(f"\n--- Testing {label} ---")
    net = neat.nn.RecurrentNetwork.create(genome, config)
    env = TradingEnv(
        test_data,
        fee_rate=fee_rate,
        decision_threshold=decision_threshold,
        min_trade_interval=min_trade_interval,
        initial_capital=initial_capital,
    )

    hist_eq, hist_cash, hist_holdings = [], [], []
    for i in tqdm(range(len(test_data))):
        inputs = env.get_state(i)
        action = net.activate(inputs)
        eq = env.step(i, action)
        hist_eq.append(eq)
        hist_cash.append(env.cash)
        hist_holdings.append(env.holdings * env.closes[i])

    final_roi = (hist_eq[-1] - initial_capital) / initial_capital * 100
    print(f"Final ROI ({label}): {final_roi:.2f}%")
    print(f"Total Trades: {len(env.trades)}")

    # Generate plot using reporter
    reporter = PeriodicReporter(
        test_data,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        decision_threshold=decision_threshold,
        min_trade_interval=min_trade_interval,
    )
    reporter.gen = label
    reporter.plot(env, hist_eq, hist_cash, hist_holdings)

    return final_roi
