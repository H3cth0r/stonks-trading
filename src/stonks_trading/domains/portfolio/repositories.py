"""Repository functions for portfolio domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from stonks_trading.domains.portfolio.entities import Portfolio
from stonks_trading.domains.trading.value_objects import Money


async def get_portfolio(
    bot_type: str,
    bot_instance_id: str,
    current_equity: float = 10000.0,
    currency: str = "USDT",
) -> Portfolio:
    """Get portfolio for bot instance.

    Args:
        bot_type: Bot type identifier
        bot_instance_id: Bot instance identifier
        current_equity: Current total equity
        currency: Currency of the equity

    Returns:
        Portfolio entity
    """
    return Portfolio(
        bot_type=bot_type,
        bot_instance_id=bot_instance_id,
        total_value=Money(amount=current_equity, currency=currency),
        cash=Money(amount=current_equity, currency=currency),  # Cash position tracked separately
        positions={},
        id=None,
    )


async def save_portfolio(portfolio: Portfolio) -> Portfolio:
    """Save portfolio (placeholder for future persistence).

    Args:
        portfolio: Portfolio entity

    Returns:
        Portfolio with ID assigned
    """
    # For now, portfolio is computed dynamically
    # Full persistence will be added in Phase 10F
    if portfolio.id is None:
        portfolio.id = 1  # Placeholder
    return portfolio
