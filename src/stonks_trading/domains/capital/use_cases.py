"""Capital domain use cases.

Orchestration for capital operations.
"""

from stonks_trading.domains.capital.entities import CapitalAllocation
from stonks_trading.domains.capital.repositories import (
    allocate_to_bot,
    deallocate_from_bot,
    get_bot_allocation,
    get_pool,
)
from stonks_trading.domains.trading.value_objects import Money


class AllocateCapitalUseCase:
    """Use case for allocating capital to a bot.

    Orchestrates capital allocation from pool to bot.
    """

    async def execute(
        self,
        bot_type: str,
        bot_instance_id: str,
        pool_id: str,
        amount: float,
        currency: str = "USDT",
    ) -> CapitalAllocation:
        """Execute capital allocation.

        Args:
            bot_type: Bot type identifier
            bot_instance_id: Bot instance identifier
            pool_id: Pool to allocate from
            amount: Amount to allocate
            currency: Currency code

        Returns:
            CapitalAllocation entity
        """
        money = Money(amount=amount, currency=currency)
        return await allocate_to_bot(bot_type, bot_instance_id, pool_id, money)


class DeallocateCapitalUseCase:
    """Use case for deallocating capital from a bot.

    Orchestrates capital return to pool.
    """

    async def execute(
        self,
        bot_type: str,
        bot_instance_id: str,
        pool_id: str,
    ) -> bool:
        """Execute capital deallocation.

        Args:
            bot_type: Bot type identifier
            bot_instance_id: Bot instance identifier
            pool_id: Pool to return capital to

        Returns:
            True if successful
        """
        return await deallocate_from_bot(bot_type, bot_instance_id, pool_id)


class RebalanceCapitalUseCase:
    """Use case for rebalancing capital between bots.

    Orchestrates capital reallocation.
    """

    async def execute(
        self,
        pool_id: str,
        rebalance_targets: list[dict],
    ) -> list[CapitalAllocation]:
        """Execute capital rebalance.

        Args:
            pool_id: Pool to rebalance
            rebalance_targets: List of dicts with bot_type, instance_id, target_pct

        Returns:
            List of updated CapitalAllocations
        """
        pool = await get_pool(pool_id)
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        total = pool.total_capital.amount
        results = []

        for target in rebalance_targets:
            bot_type = target["bot_type"]
            instance_id = target["instance_id"]
            target_pct = target["target_pct"]

            target_amount = total * target_pct

            # Get current allocation
            current = await get_bot_allocation(bot_type, instance_id)
            current_amount = current.allocated_amount.amount if current else 0

            diff = target_amount - current_amount

            if diff > 0:
                await allocate_to_bot(
                    bot_type,
                    instance_id,
                    pool_id,
                    Money(amount=diff, currency=pool.total_capital.currency),
                )
            elif diff < 0:
                # Would need deallocate logic here
                pass

            updated = await get_bot_allocation(bot_type, instance_id)
            if updated:
                results.append(updated)

        return results
