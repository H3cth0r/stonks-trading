"""NEAT Swing Bot implementation.

Implements the exact trading strategy from NEAT/main.py with:
- 7-element state vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
- DECISION_THRESHOLD = 0.6
- TRANSACTION_FEE = 0.001
- MIN_TRADE_INTERVAL = 15
- All-in / all-out trading logic
- RecurrentNetwork for temporal dynamics
"""

from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy

__all__ = ["NeatSwingBot", "NeatSwingState", "NeatSwingStrategy"]