"""NEAT-specific entities extending base Model.

These entities extend the base strategy Model with NEAT-specific
fields and represent the genome/trading brain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stonks_trading.domains.strategies.base.entities import Model


@dataclass
class NeatModel(Model):
    """NEAT genome as a strategy Model.

    Extends base Model with NEAT-specific fields for genome data,
    generation number, and NEAT-specific metrics.

    This is the migrated version of trading/entities.py Genome class.
    """

    generation: int = 0
    species_id: int | None = None

    def __post_init__(self) -> None:
        # Ensure strategy_type is set
        if not self.strategy_type:
            object.__setattr__(self, "strategy_type", "neat_swing")

    @classmethod
    def from_model(
        cls, model: Model, generation: int = 0, species_id: int | None = None
    ) -> NeatModel:
        """Create NeatModel from base Model.

        Args:
            model: Base Model entity
            generation: NEAT generation number
            species_id: NEAT species ID

        Returns:
            NeatModel instance
        """
        return cls(
            model_data=model.model_data,
            id=model.id,
            strategy_type=model.strategy_type or "neat_swing",
            symbol=model.symbol,
            version=model.version,
            fitness_score=model.fitness_score,
            roi_validation=model.roi_validation,
            roi_test=model.roi_test,
            max_drawdown=model.max_drawdown,
            num_trades=model.num_trades,
            total_return=model.total_return,
            created_at=model.created_at,
            activated_at=model.activated_at,
            deactivated_at=model.deactivated_at,
            active_for_bot_type=model.active_for_bot_type,
            active_for_instance_id=model.active_for_instance_id,
            metadata=model.metadata,
            generation=generation,
            species_id=species_id,
        )

    def to_model(self) -> Model:
        """Convert to base Model.

        Returns:
            Base Model entity
        """
        return Model(
            model_data=self.model_data,
            id=self.id,
            strategy_type=self.strategy_type,
            symbol=self.symbol,
            version=self.version,
            fitness_score=self.fitness_score,
            roi_validation=self.roi_validation,
            roi_test=self.roi_test,
            max_drawdown=self.max_drawdown,
            num_trades=self.num_trades,
            total_return=self.total_return,
            created_at=self.created_at,
            activated_at=self.activated_at,
            deactivated_at=self.deactivated_at,
            active_for_bot_type=self.active_for_bot_type,
            active_for_instance_id=self.active_for_instance_id,
            metadata=self.metadata,
        )


@dataclass
class NeatTrainingRun:
    """NEAT training run record.

    Tracks the training session with all metadata needed
    for reproducibility and analysis.
    """

    id: int | None = None
    symbol: str = ""
    generations: int = 30
    pop_size: int = 150
    best_fitness: float | None = None
    best_roi_validation: float | None = None
    best_roi_test: float | None = None
    episode_steps: int = 20160
    fee_rate: float = 0.001
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    status: str = "running"  # running, completed, failed
    config_snapshot: dict[str, Any] | None = None
    model_id: int | None = None  # Reference to saved NeatModel


@dataclass
class GenerationMetric:
    """Per-generation metrics during NEAT training.

    Captures the evolution of the population across generations.
    """

    run_id: int
    generation: int
    best_fitness: float
    mean_fitness: float
    worst_fitness: float | None = None
    num_species: int | None = None
    num_genomes: int | None = None
    best_roi_validation: float | None = None
    stagnation_count: int = 0
    num_trades_best: int | None = None
    max_drawdown_best: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
