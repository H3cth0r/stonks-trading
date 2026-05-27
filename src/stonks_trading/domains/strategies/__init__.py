"""Strategy base domain - interfaces and abstractions for multi-strategy architecture.

This domain provides the foundation for supporting multiple trading strategies
(NEAT, FIBRAS, etc.) with a common interface.

Sub-packages:
- base: Base interfaces, entities, registry, and repositories
- neat_swing: NEAT swing trading strategy implementation
"""

from stonks_trading.domains.strategies.base.entities import (
    EvaluationResult,
    Model,
    Signal,
    StrategyConfig,
    TrainingData,
    TrainingResult,
)
from stonks_trading.domains.strategies.base.interfaces import IStrategy, ITrainableStrategy
from stonks_trading.domains.strategies.base.registry import StrategyRegistry

__all__ = [
    # Base interfaces
    "IStrategy",
    "ITrainableStrategy",
    # Base entities
    "Model",
    "Signal",
    "StrategyConfig",
    "TrainingData",
    "TrainingResult",
    "EvaluationResult",
    # Registry
    "StrategyRegistry",
]
