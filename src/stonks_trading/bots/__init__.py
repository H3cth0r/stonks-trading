"""Multi-bot trading framework.

This module provides the infrastructure for running multiple independent
trading bot instances with different strategies. Each bot is isolated
by its BotContext and registered via the BotRegistry.

Example:
    from stonks_trading.bots import BotRegistry, BotFactory, BotContext

    # Factory creates bot instances
    bot = BotFactory.create(
        bot_type="neat_swing",
        instance_id="neat-swing-btc-1",
        symbols=["BTC_USD"],
        mode="dry_run",
    )

    # Start the bot
    await bot.start()
"""

from collections.abc import Callable
from typing import Any, TypeVar

from stonks_trading.bots.base.bot import BaseBot
from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.base.state import BaseBotState
from stonks_trading.bots.base.strategy import BaseStrategy
from stonks_trading.domains.trading.enums import TradingMode
from stonks_trading.domains.trading.value_objects import Symbol

# Type alias for generic BaseBot - registry doesn't care about specific types
BaseBotType = type[BaseBot[Any, Any]]

BotT = TypeVar("BotT", bound=BaseBot[Any, Any])

# Strategy factory type for dynamic strategy creation
StrategyFactory = Callable[[dict[str, Any]], BaseStrategy]


class BotRegistry:
    """Registry for bot type mappings.

    Maps bot_type strings to their implementing classes.
    Uses a class-level dictionary for global registration.

    Example:
        @BotRegistry.register("neat_swing")
        class NeatSwingBot(BaseBot[NeatSwingState, NeatSwingStrategy]):
            ...

        # Later retrieval
        bot_class = BotRegistry.get("neat_swing")
    """

    _bots: dict[str, BaseBotType] = {}

    @classmethod
    def register(cls, bot_type: str) -> Callable[[type[BotT]], type[BotT]]:
        """Decorator to register a bot class.

        Args:
            bot_type: Unique identifier for this bot type.

        Returns:
            Decorator function that registers the class.

        Raises:
            ValueError: If bot_type is already registered.
        """

        def decorator(bot_class: type[BotT]) -> type[BotT]:
            """Register the bot class."""
            if bot_type in cls._bots:
                raise ValueError(
                    f"Bot type '{bot_type}' already registered. "
                    f"Existing: {cls._bots[bot_type].__name__}"
                )
            cls._bots[bot_type] = bot_class
            return bot_class

        return decorator

    @classmethod
    def get(cls, bot_type: str) -> BaseBotType:
        """Get the bot class for a given type.

        Args:
            bot_type: Bot type identifier.

        Returns:
            Bot class implementing BaseBot.

        Raises:
            ValueError: If bot_type is not registered.
        """
        if bot_type not in cls._bots:
            raise ValueError(
                f"Unknown bot type: '{bot_type}'. Registered types: {list(cls._bots.keys())}"
            )
        return cls._bots[bot_type]

    @classmethod
    def list_bots(cls) -> list[str]:
        """List all registered bot types.

        Returns:
            List of registered bot type identifiers.
        """
        return list(cls._bots.keys())

    @classmethod
    def is_registered(cls, bot_type: str) -> bool:
        """Check if a bot type is registered.

        Args:
            bot_type: Bot type identifier.

        Returns:
            True if registered, False otherwise.
        """
        return bot_type in cls._bots

    @classmethod
    def unregister(cls, bot_type: str) -> None:
        """Unregister a bot type.

        Primarily for testing. Use with caution in production.

        Args:
            bot_type: Bot type to unregister.
        """
        cls._bots.pop(bot_type, None)


class StrategyRegistry:
    """Registry for live trading strategy factories.

    Maps strategy type strings to factory functions that create
    strategy instances. Used by BotFactory to instantiate strategies
    for live trading.

    Example:
        def create_neat_strategy(config: dict[str, Any]) -> BaseStrategy:
            return NeatSwingStrategy(config_path=config.get("config_path"))

        StrategyRegistry.register("neat_swing", create_neat_strategy)

        # Later retrieval
        strategy = StrategyRegistry.create("neat_swing", {"config_path": "config-neat.txt"})
    """

    _strategies: dict[str, StrategyFactory] = {}

    @classmethod
    def register(cls, strategy_type: str, factory: StrategyFactory) -> None:
        """Register a strategy factory.

        Args:
            strategy_type: Unique identifier for strategy (snake_case)
            factory: Factory function that creates strategy instances
        """
        if strategy_type in cls._strategies:
            raise ValueError(f"Strategy {strategy_type} already registered")
        cls._strategies[strategy_type] = factory

    @classmethod
    def create(cls, strategy_type: str, config: dict[str, Any] | None = None) -> BaseStrategy:
        """Create a strategy instance by type.

        Args:
            strategy_type: Strategy type identifier
            config: Configuration dict passed to factory

        Returns:
            Strategy instance

        Raises:
            KeyError: If strategy type not found
        """
        if strategy_type not in cls._strategies:
            raise KeyError(f"Strategy {strategy_type} not found in registry")
        return cls._strategies[strategy_type](config or {})

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


class BotFactory:
    """Factory for creating bot instances.

    Centralizes bot instantiation and ensures proper initialization
    of context, symbols, mode, and strategy. Uses BotRegistry to resolve
    bot types and StrategyRegistry to resolve strategy types.

    Example:
        bot = BotFactory.create(
            bot_type="neat_swing",
            instance_id="instance-1",
            symbols=["BTC_USD", "ETH_USD"],
            mode="dry_run",
            strategy_type="neat_swing",
            capital_allocation=50000.0,
        )
    """

    @classmethod
    def create(
        cls,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        strategy_type: str | None = None,
        capital_allocation: float | None = None,
        **kwargs: Any,
    ) -> BaseBot[Any, Any]:
        """Create a bot instance with strategy injection.

        The caller is responsible for creating the initial_state as different
        bot types require different state classes.

        Args:
            bot_type: Registered bot type identifier.
            instance_id: Unique instance identifier.
            symbols: List of trading symbols (e.g., ["BTC_USD"]).
            mode: Trading mode ("dry_run" or "live").
            strategy_type: Strategy type identifier (defaults to bot_type).
            capital_allocation: Initial capital allocation for this bot.
            **kwargs: Additional arguments passed to bot constructor.
                - initial_state: Bot-specific initial state (required)
                - strategy_config: Config dict for strategy factory

        Returns:
            Configured bot instance with injected strategy.

        Raises:
            ValueError: If bot_type is not registered or strategy_type is invalid.
        """
        # Resolve bot class from registry
        bot_class = BotRegistry.get(bot_type)

        # Construct domain objects (factory responsibility, not caller)
        context = BotContext(bot_type=bot_type, instance_id=instance_id)
        symbol_objects = [Symbol(value=s) for s in symbols]
        mode_enum = TradingMode(mode)

        # Get strategy factory from StrategyRegistry and create instance
        # Only use StrategyRegistry if strategy not passed and strategy_type is registered
        # This maintains backward compatibility with bots that have default strategies
        if "strategy" in kwargs:
            strategy = kwargs.pop("strategy")
        elif strategy_type is not None and StrategyRegistry.is_registered(strategy_type):
            strategy_config = kwargs.pop("strategy_config", {})
            strategy = StrategyRegistry.create(strategy_type, strategy_config)
        else:
            # Let bot use its default strategy (backward compatibility)
            strategy = None

        # Build kwargs for bot constructor
        bot_kwargs: dict[str, Any] = {
            "context": context,
            "symbols": symbol_objects,
            "mode": mode_enum,
            **kwargs,
        }

        # Only add strategy and capital_allocation if they are set
        if strategy is not None:
            bot_kwargs["strategy"] = strategy
        if capital_allocation is not None:
            bot_kwargs["capital_allocation"] = capital_allocation

        # Create bot with strategy injection
        # initial_state should be passed in kwargs - it's bot-type-specific
        bot = bot_class(**bot_kwargs)

        return bot

    @classmethod
    def create_context(
        cls,
        bot_type: str,
        instance_id: str,
    ) -> BotContext:
        """Create a BotContext without instantiating a bot.

        Useful for repository queries and manual bot construction.

        Args:
            bot_type: Bot type identifier.
            instance_id: Instance identifier.

        Returns:
            BotContext value object.
        """
        return BotContext(bot_type=bot_type, instance_id=instance_id)


__all__ = [
    "BaseBot",
    "BaseBotState",
    "BaseStrategy",
    "BotContext",
    "BotFactory",
    "BotRegistry",
    "BotT",
    "StrategyFactory",
    "StrategyRegistry",
]
