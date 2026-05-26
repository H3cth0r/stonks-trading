"""Capital domain - capital allocation for trading bots.

Provides entities and use cases for capital management.
"""

from stonks_trading.domains.capital.entities import CapitalAllocation, CapitalPool
from stonks_trading.domains.capital.repositories import (
    allocate_to_bot,
    create_pool,
    deallocate_from_bot,
    get_bot_allocation,
    get_pool,
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
    "allocate_to_bot",
    "deallocate_from_bot",
    "get_bot_allocation",
    "AllocateCapitalUseCase",
    "DeallocateCapitalUseCase",
    "RebalanceCapitalUseCase",
]
