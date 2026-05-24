"""Training domain services - EXTERNAL API CALLS AND CALCULATIONS.

Services handle:
- NEAT-python interaction (TrainingExecutor)
- Genome evaluation on data (GenomeEvaluator)
- Genome serialization/deserialization (GenomeSerializer)
- Training data fetching (TrainingDataProvider)

Business logic belongs in use_cases.py - not here.

Service rules (per architecture.md):
- Classes allowed for service layer
- No business logic - only calculations and external calls
- Pure transformation functions where possible
"""

import pickle
from collections.abc import Callable
from typing import Any

import neat
import pandas as pd

from stonks_trading.domains.trading.neat.config_builder import create_default_config
from stonks_trading.domains.trading.neat.trainer import NeatTrainer, evaluate_genome_on_data


class TrainingExecutor:
    """Executes NEAT training runs.

    Service - handles the external neat-python library.
    Business logic (when to train, which data) belongs in use cases.
    """

    def __init__(
        self,
        generations: int = 30,
        population_size: int = 150,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize training executor.

        Args:
            generations: Number of generations to train
            population_size: NEAT population size
            initial_capital: Starting capital for episodes
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.generations = generations
        self.population_size = population_size
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

    async def execute_training(
        self,
        train_data: pd.DataFrame,
        progress_callback: Callable[[int, float, float], None] | None = None,
    ) -> tuple[neat.DefaultGenome, list[dict[str, Any]]]:
        """Execute training and return winner + generation metrics.

        Args:
            train_data: Training data DataFrame
            progress_callback: Optional callback(generation, best_fitness, mean_fitness)

        Returns:
            Tuple of (best_genome, generation_metrics_list)
        """
        config = create_default_config()
        trainer = NeatTrainer(
            train_data=train_data,
            config=config,
            initial_capital=self.initial_capital,
            episode_steps=20160,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
        )

        # Run training
        winner = trainer.train(generations=self.generations)

        # Build metrics list (simplified - full implementation would track per-generation)
        generation_metrics: list[dict[str, Any]] = []

        # TODO: Add custom reporter that calls progress_callback
        # For now, just return the winner
        return winner, generation_metrics

    def get_config(self) -> neat.Config:
        """Get NEAT configuration for this executor."""
        return create_default_config()


class GenomeEvaluator:
    """Evaluates genomes on validation data.

    Service - handles neat-python evaluation.
    Business logic (thresholds, decisions) belongs in use cases.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize genome evaluator.

        Args:
            initial_capital: Starting capital for evaluation
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

    async def evaluate_on_data(
        self,
        genome: neat.DefaultGenome,
        data: pd.DataFrame,
    ) -> dict[str, Any]:
        """Evaluate genome on data and return metrics.

        Args:
            genome: NEAT genome to evaluate
            data: DataFrame with OHLCV data

        Returns:
            Dict with keys:
            - final_equity: Final portfolio value
            - final_roi_pct: ROI percentage
            - total_trades: Number of trades
            - max_drawdown: Maximum drawdown
            - equity_curve: List of equity values
        """
        config = create_default_config()  # For evaluation only
        results = evaluate_genome_on_data(
            genome=genome,
            config=config,
            data=data,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            verbose=False,
        )

        return {
            "final_equity": results["final_equity"],
            "final_roi_pct": results["final_roi_pct"],
            "total_trades": results["total_trades"],
            "max_drawdown": results["max_drawdown"],
            "equity_curve": results["equity_curve"],
        }

    def calculate_improvement(
        self,
        new_roi: float,
        prev_roi: float,
    ) -> float:
        """Calculate improvement percentage.

        Args:
            new_roi: New genome ROI
            prev_roi: Previous genome ROI

        Returns:
            Improvement as percentage points
        """
        return new_roi - prev_roi


class GenomeSerializer:
    """Serializes/deserializes genomes to/from storage.

    Service - handles pickle serialization.
    """

    @staticmethod
    def serialize(genome: neat.DefaultGenome, config: neat.Config) -> bytes:
        """Serialize genome and config to bytes.

        Args:
            genome: NEAT genome
            config: NEAT config

        Returns:
            Pickled bytes
        """
        return pickle.dumps((genome, config))

    @staticmethod
    def deserialize(data: bytes) -> tuple[neat.DefaultGenome, neat.Config]:
        """Deserialize genome from bytes.

        Args:
            data: Pickled bytes

        Returns:
            Tuple of (genome, config)
        """
        return pickle.loads(data)  # type: ignore[no-any-return]


class TrainingDataProvider:
    """Provides training data from multiple sources.

    Service - aggregates data from DuckDB, Parquet, etc.
    Business logic (which data, date ranges) in use cases.
    """

    async def fetch_training_window(
        self,
        symbol: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """Fetch training data window from DuckDB.

        Args:
            symbol: Trading symbol
            days: Number of days of historical data

        Returns:
            DataFrame with OHLCV data and features
        """
        # TODO: Implement using DuckDB client
        # This will fetch from parquet files or DuckDB
        msg = f"TrainingDataProvider.fetch_training_window not implemented for {symbol}"
        raise NotImplementedError(msg)

    async def fetch_validation_data(
        self,
        symbol: str,
        days: int = 14,
    ) -> pd.DataFrame:
        """Fetch validation data (last N days after training window).

        Args:
            symbol: Trading symbol
            days: Number of days of validation data

        Returns:
            DataFrame with OHLCV data for validation
        """
        # TODO: Implement using DuckDB client
        msg = f"TrainingDataProvider.fetch_validation_data not implemented for {symbol}"
        raise NotImplementedError(msg)


class CheckpointManager:
    """Manages training checkpoints with retention policy.

    Service - handles checkpoint creation and retention thinning.
    """

    def __init__(
        self,
        keep_every_nth: int = 5,
        max_checkpoints: int = 20,
    ):
        """Initialize checkpoint manager.

        Args:
            keep_every_nth: Keep every Nth checkpoint
            max_checkpoints: Maximum checkpoints to retain
        """
        self.keep_every_nth = keep_every_nth
        self.max_checkpoints = max_checkpoints

    def should_retain_checkpoint(
        self,
        generation: int,
        fitness: float,
        best_fitness: float,
    ) -> bool:
        """Determine if checkpoint should be retained.

        Args:
            generation: Generation number
            fitness: Generation fitness
            best_fitness: Best fitness so far

        Returns:
            True if checkpoint should be kept
        """
        # Always keep best
        if fitness >= best_fitness:
            return True
        # Keep every Nth
        return generation % self.keep_every_nth == 0

    def apply_retention_policy(
        self,
        checkpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply retention policy to list of checkpoints.

        Args:
            checkpoints: List of checkpoint dicts with generation, fitness

        Returns:
            Filtered list of checkpoints to retain
        """
        if len(checkpoints) <= self.max_checkpoints:
            return checkpoints

        # Sort by fitness descending
        sorted_cp = sorted(checkpoints, key=lambda x: x.get("fitness", 0), reverse=True)

        # Keep best and every Nth
        kept = []
        for i, cp in enumerate(sorted_cp):
            gen = cp.get("generation", 0)
            if i < self.max_checkpoints // 2:
                kept.append(cp)  # Keep top performers
            elif gen % self.keep_every_nth == 0:
                kept.append(cp)

        return kept
