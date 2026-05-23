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


class BotFactory:
    """Factory for creating bot instances.

    Centralizes bot instantiation and ensures proper initialization
    of context, symbols, and mode. Uses BotRegistry to resolve types.

    Example:
        bot = BotFactory.create(
            bot_type="neat_swing",
            instance_id="instance-1",
            symbols=["BTC_USD", "ETH_USD"],
            mode="dry_run",
            config_path="config.txt",  # Passed to bot constructor
        )
    """

    @classmethod
    def create(
        cls,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        **kwargs: Any,
    ) -> BaseBot[Any, Any]:
        """Create a bot instance.

        Args:
            bot_type: Registered bot type identifier.
            instance_id: Unique instance identifier.
            symbols: List of trading symbols (e.g., ["BTC_USD"]).
            mode: Trading mode ("dry_run" or "live").
            **kwargs: Additional arguments passed to bot constructor.

        Returns:
            Configured bot instance.

        Raises:
            ValueError: If bot_type is not registered or mode is invalid.
        """
        # Resolve bot class from registry
        bot_class = BotRegistry.get(bot_type)

        # Construct domain objects (factory responsibility, not caller)
        context = BotContext(bot_type=bot_type, instance_id=instance_id)
        symbol_objects = [Symbol(value=s) for s in symbols]
        mode_enum = TradingMode(mode)

        # Instantiate with proper types
        return bot_class(
            context=context,
            symbols=symbol_objects,
            mode=mode_enum,
            **kwargs,
        )

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
]
