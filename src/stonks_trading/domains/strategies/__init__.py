"""Strategy base domain - interfaces and abstractions for multi-strategy architecture.

This domain provides the foundation for supporting multiple trading strategies
(NEAT, FIBRAS, etc.) with a common interface.
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
    "IStrategy",
    "ITrainableStrategy",
    "Model",
    "Signal",
    "StrategyConfig",
    "TrainingData",
    "TrainingResult",
    "EvaluationResult",
    "StrategyRegistry",
]
