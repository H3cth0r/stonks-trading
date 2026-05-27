"""NEAT trainer module extracted from NEAT/main.py eval_genomes.

This module provides genome evaluation and training orchestration
with ITrainableStrategy implementation.

Original source: NEAT/main.py lines 238-255, 450-497
"""

import pickle
import random
import time
from collections.abc import Callable
from typing import Any

import neat
import pandas as pd
import ta
from tqdm import tqdm

from stonks_trading.domains.strategies.base.entities import (
    EvaluationResult,
    Model,
    Signal,
    StrategyConfig,
    TrainingData,
    TrainingResult,
)
from stonks_trading.domains.strategies.base.interfaces import ITrainableStrategy
from stonks_trading.domains.strategies.neat_swing.config import (
    create_default_config,
    load_neat_config,
)
from stonks_trading.domains.strategies.neat_swing.features import engineer_features
from stonks_trading.domains.strategies.neat_swing.fitness import (
    calculate_fitness,
    calculate_metrics,
)
from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv
from stonks_trading.domains.trading.value_objects import Symbol


class NeatSwingStrategy(ITrainableStrategy):
    """NEAT trainer for swing trading strategy.

    Implements ITrainableStrategy interface for the multi-strategy architecture.
    Encapsulates the training loop and genome evaluation logic
    from NEAT/main.py.
    """

    def __init__(
        self,
        config_path: str | None = None,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize NEAT trainer.

        Args:
            config_path: Path to NEAT config file (uses default if None)
            initial_capital: Starting capital for episodes
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.config_path = config_path
        self.neat_config = load_neat_config(config_path) if config_path else create_default_config()
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

        # Trained genome storage
        self._trained_genome: neat.DefaultGenome | None = None
        self._generation: int = 0

    def get_strategy_type(self) -> str:
        """Get strategy type identifier."""
        return "neat_swing"

    def get_required_data_frequency(self) -> str:
        """Get required market data frequency."""
        return "1m"

    async def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        position: dict[str, Any] | None,
    ) -> Signal | None:
        """Generate trading signal (not used in training context)."""
        return None

    async def compute_features(
        self,
        symbol: Symbol,
        candles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute features from candles for training.

        Returns features compatible with NEAT input vector.
        """
        if len(candles) < 200:
            return {
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }

        closes = pd.Series([c.get("close", c.get("Close", 0)) for c in candles])

        # Create sequential datetime index for resampling
        start_time = pd.Timestamp("2024-01-01")
        closes.index = pd.date_range(start=start_time, periods=len(closes), freq="1min")

        # Resample to 1h for trend and RSI
        df_1h = closes.resample("1h").last().dropna()

        # Trend
        if len(df_1h) >= 200:
            sma50 = ta.trend.SMAIndicator(df_1h, 50).sma_indicator()
            sma200 = ta.trend.SMAIndicator(df_1h, 200).sma_indicator()
            trend_1h = (sma50 - sma200) / sma200
            trend_1h_value = trend_1h.iloc[-1] if not trend_1h.empty else 0.0
        else:
            trend_1h_value = 0.0

        # RSI 1h
        if len(df_1h) >= 14:
            rsi_1h = ta.momentum.RSIIndicator(df_1h, 14).rsi() / 100.0
            rsi_1h_value = rsi_1h.iloc[-1] if not rsi_1h.empty else 0.5
        else:
            rsi_1h_value = 0.5

        # RSI 15m
        df_15m = closes.resample("15min").last().dropna()
        if len(df_15m) >= 14:
            rsi_15m = ta.momentum.RSIIndicator(df_15m, 14).rsi() / 100.0
            rsi_15m_value = rsi_15m.iloc[-1] if not rsi_15m.empty else 0.5
        else:
            rsi_15m_value = 0.5

        # ROC on 1m
        if len(closes) >= 11:
            roc = ta.momentum.ROCIndicator(closes, 10).roc()
            roc_value = roc.iloc[-1] if not roc.empty else 0.0
        else:
            roc_value = 0.0

        # BB width on 1m
        if len(closes) >= 20:
            bb = ta.volatility.BollingerBands(closes, window=20)
            bb_width = bb.bollinger_wband()
            bb_width_value = bb_width.iloc[-1] if not bb_width.empty else 0.0
        else:
            bb_width_value = 0.0

        return {
            "trend_1h": float(trend_1h_value),
            "rsi_1h": float(rsi_1h_value),
            "rsi_15m": float(rsi_15m_value),
            "roc": float(roc_value),
            "bb_width": float(bb_width_value),
        }

    async def load_model(self, model_data: bytes) -> None:
        """Load genome from serialized data."""
        self._trained_genome = pickle.loads(model_data)

    async def save_model(self) -> bytes:
        """Serialize and return genome data."""
        if self._trained_genome is None:
            raise ValueError("No trained genome to save")
        return pickle.dumps(self._trained_genome)

    def get_feature_schema(self) -> list[str]:
        """Get list of required features for NEAT."""
        return ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]

    async def train(
        self,
        data: TrainingData,
        config: StrategyConfig,
    ) -> TrainingResult:
        """Train NEAT on historical data.

        Args:
            data: Training data with candles
            config: Training configuration

        Returns:
            Training result with metrics and trained model
        """
        start_time = time.time()

        # Convert TrainingData to DataFrame
        df = pd.DataFrame(data.candles)
        if "Datetime" in df.columns:
            df.set_index("Datetime", inplace=True)
        elif "datetime" in df.columns:
            df.set_index("datetime", inplace=True)

        # Engineer features
        df = engineer_features(df)

        episode_steps = getattr(config, "episode_steps", 20160)
        generations = getattr(config, "generations", 30)

        # Create trainer
        trainer = NeatTrainer(
            train_data=df,
            config=self.neat_config,
            initial_capital=self.initial_capital,
            episode_steps=episode_steps,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
        )

        # Run training
        winner = trainer.train(generations=generations)
        self._trained_genome = winner
        self._generation = generations

        # Calculate metrics
        test_results = evaluate_genome_on_data(
            winner,
            self.neat_config,
            df,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            verbose=False,
        )

        metrics = calculate_metrics(
            test_results["equity_curve"],
            test_results["market_prices"],
            self.initial_capital,
        )

        training_time = time.time() - start_time

        # Create model
        model = Model(
            model_data=pickle.dumps(winner),
            strategy_type="neat_swing",
            symbol=data.symbol or config.symbol,
            fitness_score=winner.fitness,
            roi_test=metrics["total_return"] * 100,
            max_drawdown=metrics["max_drawdown"],
            num_trades=test_results["total_trades"],
            total_return=metrics["total_return"],
        )

        return TrainingResult(
            model=model,
            best_fitness=winner.fitness or 0.0,
            best_roi_test=metrics["total_return"] * 100,
            num_generations=generations,
            training_time_seconds=training_time,
        )

    async def evaluate(
        self,
        model: Model,
        data: TrainingData,
    ) -> EvaluationResult:
        """Evaluate trained model on test data.

        Args:
            model: Trained model to evaluate
            data: Evaluation data

        Returns:
            Evaluation result with performance metrics
        """
        # Load genome
        genome = pickle.loads(model.model_data)

        # Convert to DataFrame
        df = pd.DataFrame(data.candles)
        if "Datetime" in df.columns:
            df.set_index("Datetime", inplace=True)
        elif "datetime" in df.columns:
            df.set_index("datetime", inplace=True)

        # Engineer features
        df = engineer_features(df)

        # Evaluate
        results = evaluate_genome_on_data(
            genome,
            self.neat_config,
            df,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            verbose=False,
        )

        metrics = calculate_metrics(
            results["equity_curve"],
            results["market_prices"],
            self.initial_capital,
        )

        return EvaluationResult(
            model=model,
            total_return=metrics["total_return"],
            sharpe_ratio=None,  # Not computed in NEAT fitness
            max_drawdown=metrics["max_drawdown"],
            roi_test=metrics["total_return"] * 100,
            num_trades=results["total_trades"],
            win_rate=None,  # Not computed in NEAT fitness
        )


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

    def create_eval_function(self) -> Callable[..., None]:
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
