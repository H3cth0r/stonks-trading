"""Base strategy for multi-bot architecture.

Abstract base class that all trading strategies must implement.
Separates feature computation from signal generation.
"""

from abc import ABC, abstractmethod
from typing import Any

from stonks_trading.domains.trading.entities import Signal
from stonks_trading.domains.trading.value_objects import Symbol


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.

    Contract:
    1. compute_features() - Transform market data into feature vectors
    2. generate_signal() - Produce trading signals from features

    Each bot instance has one strategy instance.
    Strategies are stateless; all state lives in the bot.

    Example:
        class NeatSwingStrategy(BaseStrategy):
            @property
            def name(self) -> str: return "neat_swing"

            @property
            def version(self) -> str: return "1.0.0"

            def compute_features(self, symbol, candles) -> dict[str, Any]:
                return {"trend": sma50 - sma200}

            def generate_signal(self, symbol, candle, features, position) -> Signal | None:
                return Signal(action="buy", confidence=0.8) if ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name (matches bot_type).

        Returns:
            Strategy identifier string.
        """
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Strategy version for compatibility checks.

        Returns:
            Semantic version string (e.g., "1.0.0").
        """
        ...

    @abstractmethod
    def compute_features(
        self,
        symbol: Symbol,
        candles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute features from market data.

        Args:
            symbol: Trading symbol being analyzed.
            candles: List of OHLCV candle data.

        Returns:
            Dictionary of computed features for signal generation.
        """
        ...

    @abstractmethod
    def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        current_position: Any | None,
    ) -> Signal | None:
        """Generate trading signal from features.

        Args:
            symbol: Trading symbol.
            candle: Current candle data.
            features: Features from compute_features().
            current_position: Current position for this symbol (if any).

        Returns:
            Signal if action should be taken, None otherwise.
        """
        ...
