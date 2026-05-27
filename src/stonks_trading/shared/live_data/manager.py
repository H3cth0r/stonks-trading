"""Live data manager for real-time visualization.

Manages equity history and trade markers in Redis, broadcasting updates
to connected WebSocket clients.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from stonks_trading.shared.live_data.models import BotStateSnapshot, EquityPoint, TradeMarker
from stonks_trading.shared.logger import logger
from stonks_trading.shared.redis_client import get_equity_history, push_equity


class LiveDataManager:
    """Manages live data publishing to WebSocket clients.

    Singleton per bot instance. Stores equity history in Redis
    and broadcasts state snapshots to registered WebSocket connections.
    """

    def __init__(self, bot_type: str, instance_id: str):
        """Initialize live data manager.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier
        """
        self.bot_type = bot_type
        self.instance_id = instance_id
        self._subscribers: list[Callable[[BotStateSnapshot], None]] = []
        self._equity_history: list[EquityPoint] = []
        self._trade_markers: list[TradeMarker] = []
        self._lock = asyncio.Lock()

    def subscribe(self, callback: Callable[[BotStateSnapshot], None]) -> None:
        """Subscribe to live data updates.

        Args:
            callback: Function to call with each state snapshot
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[BotStateSnapshot], None]) -> None:
        """Unsubscribe from live data updates.

        Args:
            callback: Function to remove from subscribers
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def record_equity(
        self, equity: float, cash: float, positions_value: float
    ) -> EquityPoint:
        """Record equity point and broadcast to subscribers.

        Args:
            equity: Current total equity
            cash: Current cash balance
            positions_value: Current positions value

        Returns:
            Created equity point
        """
        point = EquityPoint(
            timestamp=datetime.now(UTC),
            equity=equity,
            cash=cash,
            positions_value=positions_value,
            bot_type=self.bot_type,
            instance_id=self.instance_id,
        )

        async with self._lock:
            self._equity_history.append(point)
            self._trade_markers = [
                m for m in self._trade_markers if m not in self._trade_markers[-100:]
            ]

            # Persist to Redis
            try:
                await push_equity(self.bot_type, self.instance_id, equity)
            except Exception as e:
                logger.warning(f"Failed to persist equity to Redis: {e}")

        # Create snapshot and broadcast
        snapshot = BotStateSnapshot(
            timestamp=point.timestamp,
            bot_type=self.bot_type,
            instance_id=self.instance_id,
            status="running",
            equity=equity,
            cash=cash,
            positions=[],
            recent_trades=[m.to_dict() for m in self._trade_markers[-20:]],
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )
        self._broadcast(snapshot)

        return point

    async def record_trade(
        self,
        trade_type: str,
        price: float,
        quantity: float,
        symbol: str,
        equity_after: float,
    ) -> TradeMarker:
        """Record trade marker and broadcast to subscribers.

        Args:
            trade_type: "BUY" or "SELL"
            price: Execution price
            quantity: Trade quantity
            symbol: Trading symbol
            equity_after: Equity after trade

        Returns:
            Created trade marker
        """
        marker = TradeMarker(
            timestamp=datetime.now(UTC),
            trade_type=trade_type,
            price=price,
            quantity=quantity,
            symbol=symbol,
            equity_after=equity_after,
            bot_type=self.bot_type,
            instance_id=self.instance_id,
        )

        async with self._lock:
            self._trade_markers.append(marker)
            self._trade_markers = self._trade_markers[-100:]

        # Broadcast immediately
        snapshot = BotStateSnapshot(
            timestamp=marker.timestamp,
            bot_type=self.bot_type,
            instance_id=self.instance_id,
            status="running",
            equity=equity_after,
            cash=0.0,
            positions=[],
            recent_trades=[m.to_dict() for m in self._trade_markers[-20:]],
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )
        self._broadcast(snapshot)

        return marker

    async def get_equity_history(
        self,
        limit: int = 1000,
    ) -> list[EquityPoint]:
        """Get equity history from Redis.

        Args:
            limit: Maximum number of points

        Returns:
            List of equity points (oldest first)
        """
        values = await get_equity_history(self.bot_type, self.instance_id, limit)
        if not values:
            return self._equity_history[-limit:]
        return self._equity_history[-limit:]

    async def get_trade_markers(self, limit: int = 100) -> list[TradeMarker]:
        """Get trade markers.

        Args:
            limit: Maximum number of markers

        Returns:
            List of trade markers (most recent last)
        """
        async with self._lock:
            return self._trade_markers[-limit:]

    def _broadcast(self, snapshot: BotStateSnapshot) -> None:
        """Broadcast snapshot to all subscribers.

        Args:
            snapshot: State snapshot to broadcast
        """
        for callback in self._subscribers:
            try:
                callback(snapshot)
            except Exception as e:
                logger.error(f"Live data subscriber error: {e}")

    async def get_current_state(self, status: str = "running") -> BotStateSnapshot:
        """Get current state snapshot.

        Args:
            status: Current bot status

        Returns:
            Current state snapshot
        """
        equity = self._equity_history[-1].equity if self._equity_history else 0.0
        cash = self._equity_history[-1].cash if self._equity_history else 0.0

        return BotStateSnapshot(
            timestamp=datetime.now(UTC),
            bot_type=self.bot_type,
            instance_id=self.instance_id,
            status=status,
            equity=equity,
            cash=cash,
            positions=[],
            recent_trades=[m.to_dict() for m in self._trade_markers[-20:]],
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )
