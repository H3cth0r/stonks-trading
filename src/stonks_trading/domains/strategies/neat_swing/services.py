"""Services for NEAT swing strategy.

Business logic for NEAT training and evaluation.
These wrap the repositories and implement domain-specific operations.
"""

import pickle
from datetime import datetime
from typing import Any

import neat
import pandas as pd

from stonks_trading.domains.strategies.neat_swing.config import (
    create_default_config,
    get_config_summary,
    load_neat_config,
)
from stonks_trading.domains.strategies.neat_swing.entities import NeatModel, NeatTrainingRun
from stonks_trading.domains.strategies.neat_swing.fitness import calculate_metrics
from stonks_trading.domains.strategies.neat_swing.reporter import PeriodicReporter
from stonks_trading.domains.strategies.neat_swing.repositories import (
    activate_neat_model,
    get_active_neat_model,
    get_neat_model_by_id,
    list_neat_models,
    save_neat_model,
    save_training_run,
    update_training_run,
)
from stonks_trading.domains.strategies.neat_swing.trainer import (
    NeatTrainer,
    evaluate_genome_on_data,
)


class NeatTrainingService:
    """Service for NEAT model training operations."""

    def __init__(
        self,
        config_path: str | None = None,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        self.config_path = config_path
        self.neat_config = load_neat_config(config_path) if config_path else create_default_config()
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

    async def train(
        self,
        train_data: pd.DataFrame,
        generations: int = 30,
        episode_steps: int = 20160,
        val_data: pd.DataFrame | None = None,
    ) -> tuple[neat.DefaultGenome, dict[str, Any]]:
        """Train NEAT model.

        Args:
            train_data: Training data with features
            generations: Number of generations
            episode_steps: Steps per episode
            val_data: Optional validation data

        Returns:
            Tuple of (best_genome, metrics)
        """
        trainer = NeatTrainer(
            train_data=train_data,
            config=self.neat_config,
            initial_capital=self.initial_capital,
            episode_steps=episode_steps,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
        )

        # Create reporter if validation data provided
        reporters = []
        if val_data is not None:
            reporter = PeriodicReporter(val_data, initial_capital=self.initial_capital)
            reporters.append(reporter)

        winner = trainer.train(generations=generations, reporters=reporters)

        # Evaluate on training data
        results = evaluate_genome_on_data(
            winner,
            self.neat_config,
            train_data,
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

        return winner, metrics

    async def evaluate(
        self,
        genome: neat.DefaultGenome,
        test_data: pd.DataFrame,
    ) -> dict[str, Any]:
        """Evaluate genome on test data.

        Args:
            genome: NEAT genome to evaluate
            test_data: Test dataset

        Returns:
            Evaluation metrics
        """
        results = evaluate_genome_on_data(
            genome,
            self.neat_config,
            test_data,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            verbose=False,
        )

        return calculate_metrics(
            results["equity_curve"],
            results["market_prices"],
            self.initial_capital,
        )

    def get_config_summary(self) -> dict[str, Any]:
        """Get NEAT configuration summary."""
        return get_config_summary(self.neat_config)


class NeatModelService:
    """Service for NEAT model persistence operations."""

    async def save_model(
        self,
        genome: neat.DefaultGenome,
        symbol: str,
        metrics: dict[str, Any],
        generation: int = 0,
        bot_type: str | None = None,
        bot_instance_id: str | None = None,
    ) -> NeatModel:
        """Save trained genome as model.

        Args:
            genome: Trained NEAT genome
            symbol: Trading symbol
            metrics: Training metrics
            generation: Generation number
            bot_type: Optional bot type
            bot_instance_id: Optional bot instance ID

        Returns:
            Saved NeatModel
        """
        model = NeatModel(
            model_data=pickle.dumps(genome),
            strategy_type="neat_swing",
            symbol=symbol,
            generation=generation,
            fitness_score=genome.fitness,
            roi_validation=metrics.get("roi_validation"),
            roi_test=metrics.get("roi_test"),
            max_drawdown=metrics.get("max_drawdown"),
            num_trades=metrics.get("num_trades"),
            total_return=metrics.get("total_return"),
            active_for_bot_type=bot_type,
            active_for_instance_id=bot_instance_id,
        )

        return await save_neat_model(model)

    async def get_model(self, model_id: int) -> NeatModel | None:
        """Get model by ID."""
        return await get_neat_model_by_id(model_id)

    async def get_active(self, symbol: str, bot_type: str | None = None) -> NeatModel | None:
        """Get active model for symbol."""
        return await get_active_neat_model(symbol, bot_type)

    async def list_models(
        self,
        symbol: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
    ) -> list[NeatModel]:
        """List models with filters."""
        return await list_neat_models(symbol=symbol, is_active=is_active, limit=limit)

    async def activate_model(self, model_id: int) -> bool:
        """Activate a model."""
        return await activate_neat_model(model_id)

    async def load_genome(self, model: NeatModel) -> neat.DefaultGenome:
        """Load genome from model.

        Args:
            model: NeatModel with serialized genome

        Returns:
            NEAT genome
        """
        return pickle.loads(model.model_data)


class NeatTrainingRunService:
    """Service for training run persistence."""

    async def create_run(
        self,
        symbol: str,
        generations: int,
        pop_size: int = 150,
        episode_steps: int = 20160,
        fee_rate: float = 0.001,
    ) -> NeatTrainingRun:
        """Create a new training run."""
        run = NeatTrainingRun(
            symbol=symbol,
            generations=generations,
            pop_size=pop_size,
            episode_steps=episode_steps,
            fee_rate=fee_rate,
            status="running",
        )
        return await save_training_run(run)

    async def complete_run(
        self,
        run_id: int,
        best_fitness: float,
        best_roi_validation: float | None = None,
        best_roi_test: float | None = None,
    ) -> bool:
        """Mark training run as completed with metrics."""
        return await update_training_run(
            run_id,
            best_fitness=best_fitness,
            best_roi_validation=best_roi_validation,
            best_roi_test=best_roi_test,
            finished_at=datetime.utcnow(),
            status="completed",
        )
