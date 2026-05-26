"""Capital domain entities.

Pure dataclasses with zero framework dependencies.
Represents capital management concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from stonks_trading.domains.trading.value_objects import Money


@dataclass
class CapitalPool:
    """Capital pool entity representing available capital.

    Tracks total, available, and reserved capital.
    """

    pool_id: str
    name: str
    total_capital: Money
    available_capital: Money
    reserved_capital: Money = field(default_factory=lambda: Money(amount=0.0, currency="USD"))
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def allocate(self, bot_type: str, bot_instance_id: str, amount: Money) -> None:
        """Allocate capital to a bot.

        Args:
            bot_type: Bot type identifier
            bot_instance_id: Bot instance identifier
            amount: Amount to allocate
        """
        if amount.amount > self.available_capital.amount:
            raise ValueError("Insufficient available capital")

        self.available_capital = Money(
            amount=self.available_capital.amount - amount.amount,
            currency=self.available_capital.currency,
        )
        self.reserved_capital = Money(
            amount=self.reserved_capital.amount + amount.amount,
            currency=self.reserved_capital.currency,
        )

    def deallocate(self, amount: Money) -> None:
        """Return capital to available pool.

        Args:
            amount: Amount to deallocate
        """
        if amount.amount > self.reserved_capital.amount:
            raise ValueError("Cannot deallocate more than reserved")

        self.reserved_capital = Money(
            amount=self.reserved_capital.amount - amount.amount,
            currency=self.reserved_capital.currency,
        )
        self.available_capital = Money(
            amount=self.available_capital.amount + amount.amount,
            currency=self.available_capital.currency,
        )

    def utilization_pct(self) -> float:
        """Calculate capital utilization percentage."""
        if self.total_capital.amount == 0:
            return 0.0
        return (self.reserved_capital.amount / self.total_capital.amount) * 100


@dataclass
class CapitalAllocation:
    """Capital allocation to a specific bot.

    Tracks allocated amount, current value, and ROI for a bot.
    """

    bot_type: str
    bot_instance_id: str
    allocated_amount: Money
    current_value: Money | None = None
    roi_pct: float | None = None
    id: int | None = None
    pool_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def current_return(self) -> Money | None:
        """Calculate current return (profit/loss)."""
        if self.current_value is None:
            return None
        return Money(
            amount=self.current_value.amount - self.allocated_amount.amount,
            currency=self.current_value.currency,
        )
