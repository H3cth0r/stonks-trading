"""Capital domain - capital allocation for trading bots.

Provides entities and use cases for capital management.
"""

from stonks_trading.domains.capital.entities import CapitalAllocation, CapitalPool
from stonks_trading.domains.capital.repositories import (
    allocate_to_bot,
    create_pool,
    deallocate_from_bot,
    get_all_allocations,
    get_all_pools,
    get_bot_allocation,
    get_pool,
    update_allocation,
)
from stonks_trading.domains.capital.use_cases import (
    AllocateCapitalUseCase,
    DeallocateCapitalUseCase,
    RebalanceCapitalUseCase,
)

__all__ = [
    "CapitalPool",
    "CapitalAllocation",
    "create_pool",
    "get_pool",
    "get_all_pools",
    "allocate_to_bot",
    "deallocate_from_bot",
    "get_bot_allocation",
    "get_all_allocations",
    "update_allocation",
    "AllocateCapitalUseCase",
    "DeallocateCapitalUseCase",
    "RebalanceCapitalUseCase",
]
