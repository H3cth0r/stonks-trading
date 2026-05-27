"""Portfolio domain entities.

Pure dataclasses with zero framework dependencies.
Represents portfolio and allocation concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.value_objects import Money


@dataclass
class Portfolio:
    """Portfolio entity representing a bot's holdings.

    Tracks total value, cash, and positions.
    """

    bot_type: str
    bot_instance_id: str
    total_value: Money
    cash: Money
    positions: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def position_value(self) -> Money:
        """Calculate total value of all positions."""
        total = sum(
            p.get("market_value", 0) if isinstance(p, dict) else 0 for p in self.positions.values()
        )
        return Money(amount=total, currency=self.total_value.currency)

    def total_equity(self) -> Money:
        """Calculate total equity (cash + positions)."""
        return Money(
            amount=self.cash.amount + self.position_value().amount,
            currency=self.total_value.currency,
        )


@dataclass
class Allocation:
    """Capital allocation for a symbol in the portfolio.

    Tracks target and current allocation percentages.
    """

    symbol: str
    target_pct: float
    current_pct: float = 0.0
    rebalance_threshold: float = 0.05  # 5% threshold
    id: int | None = None
    portfolio_id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def needs_rebalance(self) -> bool:
        """Check if allocation needs rebalancing."""
        diff = abs(self.target_pct - self.current_pct)
        return diff > self.rebalance_threshold

    def drift(self) -> float:
        """Calculate drift from target."""
        return self.current_pct - self.target_pct
