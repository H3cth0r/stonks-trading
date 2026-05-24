"""Bot context for multi-bot isolation.

Re-export from domains/trading/value_objects.py where the actual
class is defined (required for Phase 5A repositories).
"""

from stonks_trading.domains.trading.value_objects import BotContext

__all__ = ["BotContext"]
