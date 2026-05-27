"""Strategy base domain interfaces.

Defines the contracts that all trading strategies must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from stonks_trading.domains.strategies.base.entities import (
    EvaluationResult,
    Model,
    Signal,
    StrategyConfig,
    TrainingData,
    TrainingResult,
)
from stonks_trading.domains.trading.value_objects import Symbol


class IStrategy(ABC):
    """Abstract base class for all trading strategies.

    Defines the interface that NEAT, FIBRAS, and any other strategy
    must implement. This allows the bot layer to be strategy-agnostic.
    """

    @abstractmethod
    async def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        position: dict[str, Any] | None,
    ) -> Signal | None:
        """Generate trading signal from market data.

        Args:
            symbol: Trading symbol
            candle: Current candle data (OHLCV + timestamp)
            features: Pre-computed features
            position: Current position state (or None if flat)

        Returns:
            Signal with action and confidence, or None if no signal
        """
        pass

    @abstractmethod
    async def compute_features(
        self,
        symbol: Symbol,
        candles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute technical features from candles.

        Args:
            symbol: Trading symbol
            candles: Historical candles (most recent last)

        Returns:
            Dictionary of computed features
        """
        pass

    @abstractmethod
    async def load_model(self, model_data: bytes) -> None:
        """Load model from serialized data.

        Args:
            model_data: Serialized model bytes
        """
        pass

    @abstractmethod
    async def save_model(self) -> bytes:
        """Serialize and return model data.

        Returns:
            Serialized model bytes
        """
        pass

    @abstractmethod
    def get_strategy_type(self) -> str:
        """Get strategy type identifier.

        Returns:
            Strategy type string (e.g., "neat_swing", "fibras")
        """
        pass

    @abstractmethod
    def get_required_data_frequency(self) -> str:
        """Get required market data frequency.

        Returns:
            Timeframe string (e.g., "1m", "5m", "1h")
        """
        pass


class ITrainableStrategy(IStrategy, ABC):
    """Abstract base class for trainable strategies.

    Extends IStrategy with training and evaluation capabilities.
    """

    @abstractmethod
    async def train(
        self,
        data: TrainingData,
        config: StrategyConfig,
    ) -> TrainingResult:
        """Train strategy on historical data.

        Args:
            data: Training data with candles and labels
            config: Training configuration

        Returns:
            Training result with metrics and artifacts
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_feature_schema(self) -> list[str]:
        """Get list of required features for this strategy.

        Returns:
            List of feature column names
        """
        pass
