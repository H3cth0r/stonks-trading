"""Strategy base domain entities.

Pure dataclasses with zero framework dependencies.
Represents core concepts for multi-strategy architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Model:
    """Generic model entity for any strategy type.

    Stores serialized model data with metadata.
    Strategy-agnostic - works with NEAT, FIBRAS, or any future strategy.
    """

    model_data: bytes
    id: int | None = None
    strategy_type: str = ""
    symbol: str | None = None
    version: str | None = None
    fitness_score: float | None = None
    roi_validation: float | None = None
    roi_test: float | None = None
    max_drawdown: float | None = None
    num_trades: int | None = None
    total_return: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    # Phase 5: Bot activation context
    active_for_bot_type: str | None = None
    active_for_instance_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if model is currently active."""
        return self.activated_at is not None and self.deactivated_at is None


@dataclass
class Signal:
    """Trading signal from strategy.

    Produced by strategy.generate_signal().
    Contains action and confidence level.
    """

    action: str  # "buy", "sell", "hold"
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyConfig:
    """Configuration for strategy training.

    Contains all parameters needed to train a strategy.
    """

    strategy_type: str
    symbol: str
    fee_rate: float = 0.001
    slippage_bps: int = 0
    mode: str = "backtest"
    generations: int = 30
    pop_size: int = 150
    episode_steps: int = 20160
    decision_threshold: float = 0.6
    min_trade_interval: int = 15
    # Reward weights (Srivastava et al. adapted)
    w_return: float = 1.0
    w_risk: float = 0.5
    w_diff: float = 3.0
    w_treynor: float = 1.0


@dataclass
class TrainingData:
    """Training data with candles and labels.

    Contains historical market data used for training.
    """

    candles: list[dict[str, Any]]
    labels: list[str] | None = None  # Optional trade labels
    symbol: str = ""
    timeframe: str = "1m"
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass
class TrainingResult:
    """Result of training a strategy.

    Contains the trained model and metrics.
    """

    model: Model
    best_fitness: float
    best_roi_validation: float | None = None
    best_roi_test: float | None = None
    num_generations: int = 0
    training_time_seconds: float | None = None
    artifacts_uri: str | None = None


@dataclass
class EvaluationResult:
    """Result of evaluating a trained model.

    Contains performance metrics on test data.
    """

    model: Model
    total_return: float
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    roi_test: float | None = None
    num_trades: int | None = None
    win_rate: float | None = None
    evaluation_time_seconds: float | None = None
