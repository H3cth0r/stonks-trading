"""Repository functions for capital domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from stonks_trading.domains.capital.entities import CapitalAllocation, CapitalPool
from stonks_trading.domains.trading.value_objects import Money

# In-memory store for capital pools (placeholder for Phase 10F persistence)
_capital_pools: dict[str, CapitalPool] = {}
_capital_allocations: dict[str, CapitalAllocation] = {}


async def create_pool(
    pool_id: str,
    name: str,
    initial_capital: float,
    currency: str = "USDT",
) -> CapitalPool:
    """Create a new capital pool.

    Args:
        pool_id: Unique pool identifier
        name: Pool name
        initial_capital: Initial capital amount
        currency: Currency code

    Returns:
        Created CapitalPool
    """
    pool = CapitalPool(
        pool_id=pool_id,
        name=name,
        total_capital=Money(amount=initial_capital, currency=currency),
        available_capital=Money(amount=initial_capital, currency=currency),
        reserved_capital=Money(amount=0.0, currency=currency),
    )
    _capital_pools[pool_id] = pool
    return pool


async def get_pool(pool_id: str) -> CapitalPool | None:
    """Get capital pool by ID.

    Args:
        pool_id: Pool identifier

    Returns:
        CapitalPool or None if not found
    """
    return _capital_pools.get(pool_id)


async def allocate_to_bot(
    bot_type: str,
    bot_instance_id: str,
    pool_id: str,
    amount: Money,
) -> CapitalAllocation:
    """Allocate capital to a bot from a pool.

    Args:
        bot_type: Bot type identifier
        bot_instance_id: Bot instance identifier
        pool_id: Pool to allocate from
        amount: Amount to allocate

    Returns:
        Created CapitalAllocation
    """
    pool = _capital_pools.get(pool_id)
    if not pool:
        raise ValueError(f"Pool {pool_id} not found")

    pool.allocate(bot_type, bot_instance_id, amount)

    allocation = CapitalAllocation(
        bot_type=bot_type,
        bot_instance_id=bot_instance_id,
        allocated_amount=amount,
        current_value=Money(amount=amount.amount, currency=amount.currency),
        pool_id=pool_id,
    )
    key = f"{bot_type}:{bot_instance_id}"
    _capital_allocations[key] = allocation
    return allocation


async def deallocate_from_bot(
    bot_type: str,
    bot_instance_id: str,
    pool_id: str,
) -> bool:
    """Deallocate capital from a bot back to pool.

    Args:
        bot_type: Bot type identifier
        bot_instance_id: Bot instance identifier
        pool_id: Pool to return capital to

    Returns:
        True if successful
    """
    pool = _capital_pools.get(pool_id)
    if not pool:
        return False

    key = f"{bot_type}:{bot_instance_id}"
    allocation = _capital_allocations.get(key)
    if not allocation:
        return False

    pool.deallocate(allocation.allocated_amount)
    del _capital_allocations[key]
    return True


async def get_bot_allocation(
    bot_type: str,
    bot_instance_id: str,
) -> CapitalAllocation | None:
    """Get capital allocation for a bot.

    Args:
        bot_type: Bot type identifier
        bot_instance_id: Bot instance identifier

    Returns:
        CapitalAllocation or None if not found
    """
    key = f"{bot_type}:{bot_instance_id}"
    return _capital_allocations.get(key)


async def get_all_pools() -> list[CapitalPool]:
    """Get all capital pools.

    Returns:
        List of all CapitalPools
    """
    return list(_capital_pools.values())


async def get_all_allocations(pool_id: str | None = None) -> list[CapitalAllocation]:
    """Get all capital allocations.

    Args:
        pool_id: Optional filter by pool ID

    Returns:
        List of CapitalAllocations
    """
    if pool_id is None:
        return list(_capital_allocations.values())
    return [a for a in _capital_allocations.values() if a.pool_id == pool_id]


async def update_allocation(
    bot_type: str,
    bot_instance_id: str,
    current_value: Money | None = None,
    roi_pct: float | None = None,
) -> CapitalAllocation | None:
    """Update capital allocation with current value and ROI.

    Args:
        bot_type: Bot type identifier
        bot_instance_id: Bot instance identifier
        current_value: New current value
        roi_pct: New ROI percentage

    Returns:
        Updated CapitalAllocation or None if not found
    """
    key = f"{bot_type}:{bot_instance_id}"
    allocation = _capital_allocations.get(key)
    if not allocation:
        return None

    if current_value is not None:
        allocation.current_value = current_value
    if roi_pct is not None:
        allocation.roi_pct = roi_pct

    return allocation
