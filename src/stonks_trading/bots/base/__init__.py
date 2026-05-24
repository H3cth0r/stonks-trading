"""Base classes for multi-bot trading architecture.

This module provides the abstract base classes that all trading bots
must implement. It enables a pluggable architecture where new bot
types can be registered without modifying existing code.

Example:
    from stonks_trading.bots.base import BaseBot, BotContext, BaseStrategy

    @BotRegistry.register("my_strategy")
    class MyBot(BaseBot[MyState, MyStrategy]):
        ...
"""

from stonks_trading.bots.base.bot import BaseBot
from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.base.state import BaseBotState
from stonks_trading.bots.base.strategy import BaseStrategy

__all__ = ["BaseBot", "BotContext", "BaseBotState", "BaseStrategy"]
