"""Live data models for real-time visualization.

Provides immutable data classes for equity points and trade markers
that are emitted via WebSocket to the dashboard.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """A single equity data point for charting.

    Immutable and hashable for efficient caching.
    """

    timestamp: datetime
    equity: float
    cash: float
    positions_value: float
    bot_type: str
    instance_id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "bot_type": self.bot_type,
            "instance_id": self.instance_id,
        }


@dataclass(frozen=True, slots=True)
class TradeMarker:
    """A trade event marker for equity chart overlay.

    Immutable and hashable for efficient caching.
    """

    timestamp: datetime
    trade_type: str  # "BUY" or "SELL"
    price: float
    quantity: float
    symbol: str
    equity_after: float
    bot_type: str
    instance_id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "trade_type": self.trade_type,
            "price": self.price,
            "quantity": self.quantity,
            "symbol": self.symbol,
            "equity_after": self.equity_after,
            "bot_type": self.bot_type,
            "instance_id": self.instance_id,
        }


@dataclass(frozen=True, slots=True)
class BotStateSnapshot:
    """Complete bot state snapshot for WebSocket broadcast.

    Immutable and hashable for efficient caching.
    """

    timestamp: datetime
    bot_type: str
    instance_id: str
    status: str
    equity: float
    cash: float
    positions: list[dict[str, Any]]
    recent_trades: list[dict[str, Any]]
    unrealized_pnl: float
    realized_pnl: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "bot_type": self.bot_type,
            "instance_id": self.instance_id,
            "status": self.status,
            "equity": self.equity,
            "cash": self.cash,
            "positions": self.positions,
            "recent_trades": self.recent_trades,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
        }
