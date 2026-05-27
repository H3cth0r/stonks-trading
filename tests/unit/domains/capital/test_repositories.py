"""Unit tests for capital repositories."""

import pytest

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
from stonks_trading.domains.trading.value_objects import Money


@pytest.mark.asyncio
class TestCreatePoolRepository:
    """Tests for create_pool repository function."""

    async def test_create_pool_returns_pool(self):
        """create_pool creates and returns a CapitalPool."""
        pool = await create_pool(
            pool_id="main_pool",
            name="Main Trading Pool",
            initial_capital=50000.0,
            currency="USDT",
        )

        assert pool.pool_id == "main_pool"
        assert pool.name == "Main Trading Pool"
        assert pool.total_capital.amount == 50000.0
        assert pool.available_capital.amount == 50000.0
        assert pool.reserved_capital.amount == 0.0

    async def test_get_pool_returns_existing(self):
        """get_pool retrieves an existing pool."""
        await create_pool(
            pool_id="test_pool",
            name="Test Pool",
            initial_capital=10000.0,
        )
        pool = await get_pool("test_pool")

        assert pool is not None
        assert pool.pool_id == "test_pool"

    async def test_get_pool_returns_none_for_missing(self):
        """get_pool returns None for non-existent pool."""
        pool = await get_pool("nonexistent")
        assert pool is None


@pytest.mark.asyncio
class TestAllocateToBotRepository:
    """Tests for allocate_to_bot repository function."""

    async def test_allocate_to_bot_creates_allocation(self):
        """allocate_to_bot creates a capital allocation."""
        await create_pool(pool_id="alloc_pool", name="Alloc Pool", initial_capital=10000.0)

        allocation = await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot1",
            pool_id="alloc_pool",
            amount=Money(amount=5000.0, currency="USDT"),
        )

        assert allocation.bot_type == "neat_swing"
        assert allocation.bot_instance_id == "bot1"
        assert allocation.allocated_amount.amount == 5000.0
        assert allocation.pool_id == "alloc_pool"

    async def test_allocate_to_bot_raises_for_missing_pool(self):
        """allocate_to_bot raises ValueError for missing pool."""
        with pytest.raises(ValueError, match="not found"):
            await allocate_to_bot(
                bot_type="neat_swing",
                bot_instance_id="bot1",
                pool_id="missing_pool",
                amount=Money(amount=1000.0, currency="USDT"),
            )


@pytest.mark.asyncio
class TestDeallocateFromBotRepository:
    """Tests for deallocate_from_bot repository function."""

    async def test_deallocate_from_bot_returns_true(self):
        """deallocate_from_bot returns True on success."""
        await create_pool(pool_id="dealloc_pool", name="Dealloc Pool", initial_capital=10000.0)
        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_dealloc",
            pool_id="dealloc_pool",
            amount=Money(amount=3000.0, currency="USDT"),
        )

        result = await deallocate_from_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_dealloc",
            pool_id="dealloc_pool",
        )

        assert result is True

    async def test_deallocate_from_bot_returns_false_for_missing(self):
        """deallocate_from_bot returns False for missing allocation."""
        result = await deallocate_from_bot(
            bot_type="neat_swing",
            bot_instance_id="nonexistent_bot",
            pool_id="some_pool",
        )
        assert result is False


@pytest.mark.asyncio
class TestGetBotAllocationRepository:
    """Tests for get_bot_allocation repository function."""

    async def test_get_bot_allocation_returns_allocation(self):
        """get_bot_allocation retrieves existing allocation."""
        await create_pool(pool_id="get_alloc_pool", name="Get Alloc Pool", initial_capital=10000.0)
        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_get",
            pool_id="get_alloc_pool",
            amount=Money(amount=2000.0, currency="USDT"),
        )

        allocation = await get_bot_allocation(bot_type="neat_swing", bot_instance_id="bot_get")

        assert allocation is not None
        assert allocation.bot_type == "neat_swing"
        assert allocation.allocated_amount.amount == 2000.0

    async def test_get_bot_allocation_returns_none_for_missing(self):
        """get_bot_allocation returns None for non-existent allocation."""
        allocation = await get_bot_allocation(bot_type="neat_swing", bot_instance_id="missing")
        assert allocation is None


@pytest.mark.asyncio
class TestGetAllPoolsRepository:
    """Tests for get_all_pools repository function."""

    async def test_get_all_pools_returns_list(self):
        """get_all_pools returns list of pools."""
        await create_pool(pool_id="pool1", name="Pool 1", initial_capital=10000.0)
        await create_pool(pool_id="pool2", name="Pool 2", initial_capital=20000.0)

        pools = await get_all_pools()
        pool_ids = [p.pool_id for p in pools]

        assert "pool1" in pool_ids
        assert "pool2" in pool_ids


@pytest.mark.asyncio
class TestGetAllAllocationsRepository:
    """Tests for get_all_allocations repository function."""

    async def test_get_all_allocations_returns_all(self):
        """get_all_allocations returns all allocations when no filter."""
        await create_pool(pool_id="allocs_pool", name="Allocs Pool", initial_capital=10000.0)
        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_a",
            pool_id="allocs_pool",
            amount=Money(amount=1000.0, currency="USDT"),
        )

        allocs = await get_all_allocations()
        assert len(allocs) >= 1

    async def test_get_all_allocations_filters_by_pool(self):
        """get_all_allocations filters by pool_id when provided."""
        await create_pool(pool_id="filter_pool", name="Filter Pool", initial_capital=10000.0)

        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_filter",
            pool_id="filter_pool",
            amount=Money(amount=500.0, currency="USDT"),
        )

        allocs = await get_all_allocations(pool_id="filter_pool")
        assert all(allocation.pool_id == "filter_pool" for allocation in allocs)


@pytest.mark.asyncio
class TestUpdateAllocationRepository:
    """Tests for update_allocation repository function."""

    async def test_update_allocation_updates_current_value(self):
        """update_allocation updates current_value when provided."""
        await create_pool(pool_id="update_pool", name="Update Pool", initial_capital=10000.0)
        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_update",
            pool_id="update_pool",
            amount=Money(amount=1000.0, currency="USDT"),
        )

        updated = await update_allocation(
            bot_type="neat_swing",
            bot_instance_id="bot_update",
            current_value=Money(amount=1200.0, currency="USDT"),
        )

        assert updated is not None
        assert updated.current_value.amount == 1200.0

    async def test_update_allocation_updates_roi(self):
        """update_allocation updates roi_pct when provided."""
        await create_pool(pool_id="roi_pool", name="ROI Pool", initial_capital=10000.0)
        await allocate_to_bot(
            bot_type="neat_swing",
            bot_instance_id="bot_roi",
            pool_id="roi_pool",
            amount=Money(amount=1000.0, currency="USDT"),
        )

        updated = await update_allocation(
            bot_type="neat_swing",
            bot_instance_id="bot_roi",
            roi_pct=15.5,
        )

        assert updated is not None
        assert updated.roi_pct == 15.5

    async def test_update_allocation_returns_none_for_missing(self):
        """update_allocation returns None for non-existent allocation."""
        updated = await update_allocation(
            bot_type="neat_swing",
            bot_instance_id="missing",
            current_value=Money(amount=100.0, currency="USDT"),
        )
        assert updated is None
