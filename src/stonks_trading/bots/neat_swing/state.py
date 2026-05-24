"""NEAT Swing Bot State.

NEAT-specific bot state for tracking positions, equity, and trading metrics.
Matches the state tracking in NEAT/main.py TradingEnv.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stonks_trading.bots.base.state import BaseBotState
from stonks_trading.domains.trading.entities import Position
from stonks_trading.domains.trading.value_objects import Symbol


@dataclass
class NeatSwingState(BaseBotState):
    """NEAT swing trading bot state.

    Tracks positions, equity curve, trade counts, and risk metrics
    exactly as in NEAT/main.py TradingEnv.reset().

    Attributes:
        positions: Symbol -> Position mapping for open positions.
        trades_today: Number of trades executed today.
        last_trade_time: Timestamp of last trade for interval enforcement.
        peak_equity: Peak equity for drawdown calculation.
        current_equity: Current equity value.
        daily_loss_pct: Daily loss percentage for safe mode.
        in_safe_mode: Whether bot is in safe mode (trading halted).
        last_realized_loss_time: Timestamp of last realized loss.
    """

    positions: dict[Symbol, Position] = field(default_factory=dict)
    trades_today: int = 0
    last_trade_time: datetime | None = None
    peak_equity: float = 10000.0
    current_equity: float = 10000.0
    daily_loss_pct: float = 0.0
    in_safe_mode: bool = False
    last_realized_loss_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for persistence.

        Returns:
            Dictionary representation of state for BotStateRepository.
        """
        return {
            "positions": {
                k.value: {
                    "quantity": v.quantity,
                    "entry_price": float(v.entry_price.amount) if v.entry_price else None,
                    "current_price": float(v.current_price.amount) if v.current_price else None,
                    "unrealized_pnl": v.unrealized_pnl,
                    "bot_type": v.bot_type,
                    "bot_instance_id": v.bot_instance_id,
                }
                for k, v in self.positions.items()
            },
            "trades_today": self.trades_today,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "peak_equity": self.peak_equity,
            "current_equity": self.current_equity,
            "daily_loss_pct": self.daily_loss_pct,
            "in_safe_mode": self.in_safe_mode,
            "last_realized_loss_time": (
                self.last_realized_loss_time.isoformat() if self.last_realized_loss_time else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NeatSwingState":
        """Deserialize state from dictionary.

        Args:
            data: Dictionary from BotStateRepository.load().

        Returns:
            Reconstructed NeatSwingState instance.
        """
        state = cls()

        state.trades_today = data.get("trades_today", 0)
        state.peak_equity = data.get("peak_equity", 10000.0)
        state.current_equity = data.get("current_equity", 10000.0)
        state.daily_loss_pct = data.get("daily_loss_pct", 0.0)
        state.in_safe_mode = data.get("in_safe_mode", False)

        last_trade_time = data.get("last_trade_time")
        if last_trade_time:
            state.last_trade_time = datetime.fromisoformat(last_trade_time)

        last_realized_loss_time = data.get("last_realized_loss_time")
        if last_realized_loss_time:
            state.last_realized_loss_time = datetime.fromisoformat(last_realized_loss_time)

        positions_data = data.get("positions", {})
        for symbol_value, pos_data in positions_data.items():
            from stonks_trading.domains.trading.entities import Position
            from stonks_trading.domains.trading.value_objects import Money

            entry_price = None
            if pos_data.get("entry_price") is not None:
                entry_price = Money(amount=pos_data["entry_price"], currency="USDT")

            current_price = None
            if pos_data.get("current_price") is not None:
                current_price = Money(amount=pos_data["current_price"], currency="USDT")

            position = Position(
                symbol=Symbol(value=symbol_value),
                quantity=pos_data.get("quantity", 0.0),
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=pos_data.get("unrealized_pnl", 0.0),
                bot_type=pos_data.get("bot_type", "neat_swing"),
                bot_instance_id=pos_data.get("bot_instance_id", "default"),
            )
            state.positions[Symbol(value=symbol_value)] = position

        return state

    def update_equity(self, new_equity: float) -> None:
        """Update equity and track peak for drawdown calculation.

        Args:
            new_equity: Current equity value.
        """
        self.current_equity = new_equity
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity

    def record_trade(self) -> None:
        """Record a trade for daily count and interval tracking."""
        self.trades_today += 1
        self.last_trade_time = datetime.utcnow()

    def reset_daily_metrics(self) -> None:
        """Reset daily metrics (called at start of new trading day)."""
        self.trades_today = 0
        self.daily_loss_pct = 0.0
        self.in_safe_mode = False
