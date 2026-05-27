"""Unit tests for capital use cases."""

import pytest

from stonks_trading.domains.capital.repositories import (
    create_pool,
    get_bot_allocation,
)
from stonks_trading.domains.capital.use_cases import (
    AllocateCapitalUseCase,
    DeallocateCapitalUseCase,
    RebalanceCapitalUseCase,
)
from stonks_trading.domains.trading.value_objects import Money


class TestAllocateCapitalUseCase:
    """Tests for AllocateCapitalUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = AllocateCapitalUseCase()
        assert use_case is not None

    @pytest.mark.asyncio
    async def test_execute_allocates_capital(self):
        """Execute allocates capital from pool to bot."""
        await create_pool(pool_id="use_case_pool", name="Use Case Pool", initial_capital=10000.0)
        use_case = AllocateCapitalUseCase()

        allocation = await use_case.execute(
            bot_type="neat_swing",
            bot_instance_id="bot_alloc",
            pool_id="use_case_pool",
            amount=5000.0,
            currency="USDT",
        )

        assert allocation.bot_type == "neat_swing"
        assert allocation.allocated_amount.amount == 5000.0


class TestDeallocateCapitalUseCase:
    """Tests for DeallocateCapitalUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = DeallocateCapitalUseCase()
        assert use_case is not None

    @pytest.mark.asyncio
    async def test_execute_deallocates_capital(self):
        """Execute deallocates capital from bot to pool."""
        await create_pool(pool_id="dealloc_use_pool", name="Dealloc Use Pool", initial_capital=10000.0)
        alloc_use_case = AllocateCapitalUseCase()
        await alloc_use_case.execute(
            bot_type="neat_swing",
            bot_instance_id="bot_dealloc_use",
            pool_id="dealloc_use_pool",
            amount=3000.0,
        )

        dealloc_use_case = DeallocateCapitalUseCase()
        result = await dealloc_use_case.execute(
            bot_type="neat_swing",
            bot_instance_id="bot_dealloc_use",
            pool_id="dealloc_use_pool",
        )

        assert result is True


class TestRebalanceCapitalUseCase:
    """Tests for RebalanceCapitalUseCase."""

    def test_creation(self):
        """Use case can be instantiated."""
        use_case = RebalanceCapitalUseCase()
        assert use_case is not None

    @pytest.mark.asyncio
    async def test_execute_raises_for_missing_pool(self):
        """Execute raises ValueError for missing pool."""
        use_case = RebalanceCapitalUseCase()

        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(
                pool_id="nonexistent_pool",
                rebalance_targets=[
                    {"bot_type": "neat_swing", "instance_id": "bot1", "target_pct": 0.5}
                ],
            )

    @pytest.mark.asyncio
    async def test_execute_rebalances_to_targets(self):
        """Execute rebalances capital to target percentages."""
        await create_pool(pool_id="rebal_pool", name="Rebal Pool", initial_capital=10000.0)
        use_case = RebalanceCapitalUseCase()

        results = await use_case.execute(
            pool_id="rebal_pool",
            rebalance_targets=[
                {"bot_type": "neat_swing", "instance_id": "bot_rebal", "target_pct": 0.5}
            ],
        )

        assert len(results) == 1
        assert results[0].bot_type == "neat_swing"
        assert results[0].allocated_amount.amount == 5000.0
