"""NEAT Swing Bot implementation.

Implements the exact trading strategy from NEAT/main.py with:
- 7-element state vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
- DECISION_THRESHOLD = 0.6
- TRANSACTION_FEE = 0.001
- MIN_TRADE_INTERVAL = 15
- All-in / all-out trading logic
- RecurrentNetwork for temporal dynamics
"""

from typing import Any

from stonks_trading.bots.base.strategy import BaseStrategy
from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy


def create_neat_swing_strategy(config: dict[str, Any]) -> BaseStrategy:
    """Factory function for NeatSwingStrategy.

    Creates a NeatSwingStrategy instance with configuration from the given dict.

    Args:
        config: Configuration dict with optional 'config_path' key.

    Returns:
        NeatSwingStrategy instance.
    """
    config_path = config.get("config_path", "config-neat.txt")
    return NeatSwingStrategy(config_path=config_path)


__all__ = [
    "NeatSwingBot",
    "NeatSwingState",
    "NeatSwingStrategy",
    "create_neat_swing_strategy",
]
