"""NEAT training module extracted from NEAT/main.py eval_genomes.

This module provides genome evaluation and training orchestration.

Original source: NEAT/main.py lines 238-255, 450-497
"""

import random
from collections.abc import Callable
from typing import Any

import neat
import pandas as pd
from tqdm import tqdm

from stonks_trading.domains.trading.neat.fitness import calculate_fitness
from stonks_trading.domains.trading.neat.trading_env import TradingEnv


class NeatTrainer:
    """NEAT trainer for swing trading strategy.

    Encapsulates the training loop and genome evaluation logic
    from NEAT/main.py.
    """

    def __init__(
        self,
        train_data: pd.DataFrame,
        config: neat.Config,
        initial_capital: float = 10000.0,
        episode_steps: int = 20160,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize trainer.

        Args:
            train_data: Training dataset (1m OHLCV with features)
            config: NEAT configuration
            initial_capital: Starting capital for episodes
            episode_steps: Steps per training episode (~14 days)
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.train_data = train_data
        self.config = config
        self.initial_capital = initial_capital
        self.episode_steps = episode_steps
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

        self.data_len = len(train_data)

    def eval_genomes(
        self,
        genomes: list[tuple[int, neat.DefaultGenome]],
        config: neat.Config | None = None,
    ) -> None:
        """Evaluate a population of genomes.

        Matches NEAT/main.py lines 238-255.

        Trains on random 2-week episodes for each genome.

        Args:
            genomes: List of (genome_id, genome) tuples
            config: NEAT configuration (uses self.config if None)
        """
        if config is None:
            config = self.config

        # Train on random 2-week episodes
        start = random.randint(0, self.data_len - self.episode_steps - 1)
        batch = self.train_data.iloc[start : start + self.episode_steps]
        mkt_prices = batch["Close"].values

        for _, genome in genomes:
            net = neat.nn.RecurrentNetwork.create(genome, config)
            env = TradingEnv(
                batch,
                fee_rate=self.fee_rate,
                decision_threshold=self.decision_threshold,
                min_trade_interval=self.min_trade_interval,
                initial_capital=self.initial_capital,
            )

            eq_curve = []
            for i in range(len(batch)):
                inputs = env.get_state(i)
                action = net.activate(inputs)
                eq_curve.append(env.step(i, action))

            genome.fitness = calculate_fitness(env, eq_curve, mkt_prices, self.initial_capital)

    def create_eval_function(self) -> Callable:
        """Create evaluation function for neat.Population.run()."""
        return lambda genomes, config: self.eval_genomes(genomes, config)

    def train(
        self,
        generations: int = 30,
        reporters: list[neat.reporting.BaseReporter] | None = None,
    ) -> neat.DefaultGenome:
        """Run NEAT training.

        Args:
            generations: Number of generations to train
            reporters: Optional list of reporters to attach

        Returns:
            Best genome from final generation
        """
        population = neat.Population(self.config)

        # Add default stdout reporter
        population.add_reporter(neat.StdOutReporter(True))

        # Add custom reporters
        if reporters:
            for reporter in reporters:
                population.add_reporter(reporter)

        print("Training Simplified Swing Trader...")
        winner = population.run(self.create_eval_function(), generations)

        return winner


def evaluate_genome_on_data(
    genome: neat.DefaultGenome,
    config: neat.Config,
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
    fee_rate: float = 0.001,
    decision_threshold: float = 0.6,
    min_trade_interval: int = 15,
    verbose: bool = True,
) -> dict[str, Any]:
    """Evaluate a single genome on given data.

    Args:
        genome: NEAT genome to evaluate
        config: NEAT configuration
        data: Dataset to evaluate on
        initial_capital: Starting capital
        fee_rate: Transaction fee rate
        decision_threshold: Probability threshold for trades
        min_trade_interval: Minimum steps between trades
        verbose: Whether to print progress

    Returns:
        Dictionary with evaluation results
    """
    net = neat.nn.RecurrentNetwork.create(genome, config)
    env = TradingEnv(
        data,
        fee_rate=fee_rate,
        decision_threshold=decision_threshold,
        min_trade_interval=min_trade_interval,
        initial_capital=initial_capital,
    )

    hist_eq = []
    hist_cash = []
    hist_holdings = []
    hist_states = []

    iterator = range(len(data))
    if verbose:
        iterator = tqdm(iterator, desc="Evaluating genome")

    for i in iterator:
        inputs = env.get_state(i)
        action = net.activate(inputs)
        eq = env.step(i, action)

        hist_eq.append(eq)
        hist_cash.append(env.cash)
        hist_holdings.append(env.holdings * env.closes[i])
        hist_states.append(inputs)

    final_roi = (hist_eq[-1] - initial_capital) / initial_capital * 100

    results = {
        "final_equity": hist_eq[-1],
        "final_roi_pct": final_roi,
        "total_trades": len(env.trades),
        "buy_trades": len([t for t in env.trades if t.trade_type == "buy"]),
        "sell_trades": len([t for t in env.trades if t.trade_type == "sell"]),
        "max_drawdown": env.max_drawdown,
        "equity_curve": hist_eq,
        "cash_curve": hist_cash,
        "holdings_curve": hist_holdings,
        "trades": env.trades,
        "states": hist_states,
        "market_prices": data["Close"].values,
    }

    return results


def compare_genomes(
    genome_a: neat.DefaultGenome,
    genome_b: neat.DefaultGenome,
    config: neat.Config,
    data: pd.DataFrame,
    labels: tuple[str, str] = ("Genome A", "Genome B"),
    **kwargs: Any,
) -> dict[str, Any]:
    """Compare two genomes on the same data.

    Args:
        genome_a: First genome
        genome_b: Second genome
        config: NEAT configuration
        data: Dataset to evaluate on
        labels: Names for the genomes
        **kwargs: Additional arguments for evaluate_genome_on_data

    Returns:
        Dictionary with comparison results
    """
    results_a = evaluate_genome_on_data(genome_a, config, data, verbose=False, **kwargs)
    results_b = evaluate_genome_on_data(genome_b, config, data, verbose=False, **kwargs)

    print(f"\n{'=' * 50}")
    print("GENOME COMPARISON")
    print(f"{'=' * 50}")
    print(f"{labels[0]}:")
    print(f"  ROI: {results_a['final_roi_pct']:.2f}%")
    print(f"  Trades: {results_a['total_trades']}")
    print(f"  Max DD: {results_a['max_drawdown'] * 100:.2f}%")
    print(f"\n{labels[1]}:")
    print(f"  ROI: {results_b['final_roi_pct']:.2f}%")
    print(f"  Trades: {results_b['total_trades']}")
    print(f"  Max DD: {results_b['max_drawdown'] * 100:.2f}%")
    print(f"{'=' * 50}")

    winner = labels[0] if results_a["final_roi_pct"] > results_b["final_roi_pct"] else labels[1]
    print(f">> Winner: {winner}")

    return {
        "results_a": results_a,
        "results_b": results_b,
        "labels": labels,
        "winner": winner,
    }
