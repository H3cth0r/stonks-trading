"""Portfolio domain use cases.

Orchestration for portfolio operations.
"""

from stonks_trading.domains.portfolio.entities import Allocation, Portfolio
from stonks_trading.domains.portfolio.services import PortfolioValuator, Rebalancer


class GetPortfolioUseCase:
    """Use case for getting portfolio.

    Orchestrates retrieving portfolio state.
    """

    def __init__(self):
        self.valuator = PortfolioValuator()

    async def execute(
        self,
        bot_type: str,
        bot_instance_id: str,
    ) -> Portfolio:
        """Execute portfolio retrieval.

        Args:
            bot_type: Bot type identifier
            bot_instance_id: Bot instance identifier

        Returns:
            Portfolio entity
        """
        from stonks_trading.domains.portfolio.repositories import get_portfolio

        portfolio = await get_portfolio(bot_type, bot_instance_id)
        return portfolio


class RebalancePortfolioUseCase:
    """Use case for rebalancing portfolio.

    Orchestrates portfolio rebalancing.
    """

    def __init__(self):
        self.rebalancer = Rebalancer()

    async def execute(
        self,
        portfolio: Portfolio,
        allocations: list[Allocation],
        prices: dict[str, float],
    ) -> list[dict]:
        """Execute portfolio rebalance.

        Args:
            portfolio: Current portfolio
            allocations: Target allocations
            prices: Current prices by symbol

        Returns:
            List of trades to execute
        """
        return self.rebalancer.calculate_rebalance_trades(portfolio, allocations, prices)


class UpdateAllocationUseCase:
    """Use case for updating allocation targets.

    Orchestrates allocation updates.
    """

    async def execute(
        self,
        portfolio_id: int,
        symbol: str,
        target_pct: float,
    ) -> Allocation:
        """Execute allocation update.

        Args:
            portfolio_id: Portfolio ID
            symbol: Trading symbol
            target_pct: New target percentage

        Returns:
            Updated Allocation
        """
        allocation = Allocation(
            symbol=symbol,
            target_pct=target_pct,
            current_pct=0,  # Will be recalculated
            rebalance_threshold=0.05,
            portfolio_id=portfolio_id,
        )
        return allocation
