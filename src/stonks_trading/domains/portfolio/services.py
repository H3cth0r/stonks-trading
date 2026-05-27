"""Portfolio domain services.

Pure business logic for portfolio operations.
"""

from typing import Any

from stonks_trading.domains.portfolio.entities import Allocation, Portfolio
from stonks_trading.domains.trading.value_objects import Money


class PortfolioValuator:
    """Service for portfolio valuation.

    Calculates current portfolio value from positions.
    """

    def __init__(self) -> None:
        pass

    def calculate_position_value(
        self,
        quantity: float,
        current_price: float,
    ) -> Money:
        """Calculate value of a position.

        Args:
            quantity: Position quantity
            current_price: Current price per unit

        Returns:
            Position value
        """
        return Money(amount=quantity * current_price, currency="USDT")

    def calculate_total_value(
        self,
        cash: Money,
        positions: list[dict[str, Any]],
        prices: dict[str, float],
    ) -> Money:
        """Calculate total portfolio value.

        Args:
            cash: Cash holdings
            positions: List of position dicts
            prices: Current prices dict by symbol

        Returns:
            Total portfolio value
        """
        positions_value = 0.0
        for pos in positions:
            symbol = pos.get("symbol", "")
            qty = pos.get("quantity", 0)
            price = prices.get(symbol, 0)
            positions_value += qty * price

        return Money(amount=cash.amount + positions_value, currency=cash.currency)


class Rebalancer:
    """Service for portfolio rebalancing.

    Calculates trades needed to rebalance portfolio.
    """

    def __init__(self, threshold: float = 0.05):
        """Initialize with rebalance threshold.

        Args:
            threshold: Drift threshold to trigger rebalance
        """
        self.threshold = threshold

    def calculate_target_position(
        self,
        total_equity: float,
        target_pct: float,
        current_price: float,
    ) -> float:
        """Calculate target quantity for a position.

        Args:
            total_equity: Total portfolio equity
            target_pct: Target allocation percentage
            current_price: Current price per unit

        Returns:
            Target quantity
        """
        target_value = total_equity * target_pct
        return target_value / current_price if current_price > 0 else 0

    def calculate_rebalance_trades(
        self,
        portfolio: Portfolio,
        allocations: list[Allocation],
        prices: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Calculate trades needed to rebalance.

        Args:
            portfolio: Current portfolio
            allocations: Target allocations
            prices: Current prices by symbol

        Returns:
            List of trade dicts (symbol, side, quantity)
        """
        trades = []
        total = portfolio.total_value.amount

        for alloc in allocations:
            if not alloc.needs_rebalance():
                continue

            price = prices.get(alloc.symbol, 0)
            if price <= 0:
                continue

            target_value = total * alloc.target_pct
            current_value = total * alloc.current_pct
            diff_value = target_value - current_value

            if abs(diff_value) < total * 0.01:  # Min trade size 1%
                continue

            quantity = abs(diff_value) / price
            side = "buy" if diff_value > 0 else "sell"

            trades.append(
                {
                    "symbol": alloc.symbol,
                    "side": side,
                    "quantity": quantity,
                }
            )

        return trades
