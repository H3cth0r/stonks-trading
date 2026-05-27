"""Use cases for NEAT swing strategy.

Application-level business logic orchestrating repositories and services.
"""

from typing import Any

import pandas as pd

from stonks_trading.domains.strategies.neat_swing.entities import NeatModel
from stonks_trading.domains.strategies.neat_swing.services import (
    NeatModelService,
    NeatTrainingRunService,
    NeatTrainingService,
)


class TrainNeatModelUseCase:
    """Use case for training a NEAT model."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ) -> None:
        self.training_service = NeatTrainingService(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            decision_threshold=decision_threshold,
            min_trade_interval=min_trade_interval,
        )
        self.model_service = NeatModelService()
        self.run_service = NeatTrainingRunService()

    async def execute(
        self,
        train_data: pd.DataFrame,
        symbol: str,
        generations: int = 30,
        episode_steps: int = 20160,
        val_data: pd.DataFrame | None = None,
        bot_type: str | None = None,
        bot_instance_id: str | None = None,
    ) -> NeatModel:
        """Execute training.

        Args:
            train_data: Training data with OHLCV and features
            symbol: Trading symbol
            generations: Number of generations
            episode_steps: Steps per episode
            val_data: Optional validation data
            bot_type: Optional bot type for model activation
            bot_instance_id: Optional bot instance ID

        Returns:
            Trained and saved NeatModel
        """
        # Create training run record
        run = await self.run_service.create_run(
            symbol=symbol,
            generations=generations,
            episode_steps=episode_steps,
        )

        # Run training
        genome, metrics = await self.training_service.train(
            train_data=train_data,
            generations=generations,
            episode_steps=episode_steps,
            val_data=val_data,
        )

        # Save model
        model = await self.model_service.save_model(
            genome=genome,
            symbol=symbol,
            metrics=metrics,
            generation=generations,
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
        )

        # Mark training run complete
        if run.id is not None:
            await self.run_service.complete_run(
                run_id=run.id,
                best_fitness=genome.fitness or 0.0,
                best_roi_validation=metrics.get("roi_validation"),
                best_roi_test=metrics.get("roi_test"),
            )

        return model


class EvaluateNeatModelUseCase:
    """Use case for evaluating a NEAT model."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ) -> None:
        self.training_service = NeatTrainingService(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            decision_threshold=decision_threshold,
            min_trade_interval=min_trade_interval,
        )
        self.model_service = NeatModelService()

    async def execute(
        self,
        model_id: int,
        test_data: pd.DataFrame,
    ) -> dict[str, Any]:
        """Execute evaluation.

        Args:
            model_id: Model to evaluate
            test_data: Test dataset

        Returns:
            Evaluation metrics
        """
        model = await self.model_service.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        genome = await self.model_service.load_genome(model)

        return await self.training_service.evaluate(genome, test_data)


class GetActiveNeatModelUseCase:
    """Use case for getting the active NEAT model."""

    def __init__(self) -> None:
        self.model_service = NeatModelService()

    async def execute(
        self,
        symbol: str,
        bot_type: str | None = None,
        bot_instance_id: str | None = None,
    ) -> NeatModel | None:
        """Get active model for symbol.

        Args:
            symbol: Trading symbol
            bot_type: Optional bot type filter
            bot_instance_id: Optional bot instance filter

        Returns:
            Active NeatModel or None
        """
        return await self.model_service.get_active(symbol, bot_type)


class ActivateNeatModelUseCase:
    """Use case for activating a NEAT model."""

    def __init__(self) -> None:
        self.model_service = NeatModelService()

    async def execute(self, model_id: int) -> bool:
        """Activate a model.

        Args:
            model_id: Model to activate

        Returns:
            True if successful
        """
        return await self.model_service.activate_model(model_id)


class ListNeatModelsUseCase:
    """Use case for listing NEAT models."""

    def __init__(self) -> None:
        self.model_service = NeatModelService()

    async def execute(
        self,
        symbol: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
    ) -> list[NeatModel]:
        """List models with filters.

        Args:
            symbol: Optional symbol filter
            is_active: Optional active filter
            limit: Maximum results

        Returns:
            List of NeatModels
        """
        return await self.model_service.list_models(symbol=symbol, is_active=is_active, limit=limit)
