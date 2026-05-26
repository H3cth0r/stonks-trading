"""Strategy registry for dynamic strategy lookup.

Provides registration and lookup for strategy classes.
Enables the bot layer to work with any strategy type.
"""

from __future__ import annotations

from typing import Any


class StrategyRegistry:
    """Registry for strategy classes.

    Singleton registry that maps strategy type strings
    to strategy classes. Used by BotFactory to instantiate
    the correct strategy.
    """

    _strategies: dict[str, Any] = {}

    @classmethod
    def register(cls, strategy_type: str, strategy_class: Any) -> None:
        """Register a strategy class.

        Args:
            strategy_type: Unique identifier for strategy (snake_case)
            strategy_class: Strategy class implementing IStrategy
        """
        if strategy_type in cls._strategies:
            raise ValueError(f"Strategy {strategy_type} already registered")
        cls._strategies[strategy_type] = strategy_class

    @classmethod
    def get(cls, strategy_type: str) -> Any:
        """Get strategy class by type.

        Args:
            strategy_type: Strategy type identifier

        Returns:
            Strategy class

        Raises:
            KeyError: If strategy type not found
        """
        if strategy_type not in cls._strategies:
            raise KeyError(f"Strategy {strategy_type} not found in registry")
        return cls._strategies[strategy_type]

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategy types.

        Returns:
            List of strategy type identifiers
        """
        return list(cls._strategies.keys())

    @classmethod
    def is_registered(cls, strategy_type: str) -> bool:
        """Check if strategy type is registered.

        Args:
            strategy_type: Strategy type identifier

        Returns:
            True if registered
        """
        return strategy_type in cls._strategies

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._strategies.clear()
