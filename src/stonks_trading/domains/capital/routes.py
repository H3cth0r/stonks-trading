"""FastAPI routes for capital management domain.

HTTP concerns only - no business logic.
Provides API endpoints for capital allocation operations.
"""

from fastapi import APIRouter, HTTPException, Path, Query, status

from stonks_trading.domains.capital.dtos import (
    AllocateCapitalRequest,
    AllocateCapitalResponse,
    CapitalAllocationListResponse,
    CapitalAllocationResponse,
    CapitalPoolResponse,
    CapitalPoolsListResponse,
    CreateCapitalPoolRequest,
    DeallocateCapitalRequest,
    DeallocateCapitalResponse,
    ErrorResponse,
    RebalanceRequest,
    RebalanceResponse,
)
from stonks_trading.domains.capital.mappers import (
    CapitalAllocationMapper,
    CapitalPoolMapper,
)
from stonks_trading.domains.capital.repositories import (
    allocate_to_bot,
    create_pool,
    deallocate_from_bot,
    get_all_allocations,
    get_all_pools,
    get_bot_allocation,
    get_pool,
)
from stonks_trading.domains.capital.use_cases import (
    RebalanceCapitalUseCase,
)
from stonks_trading.domains.trading.value_objects import Money

# =============================================================================
# Router Factory Pattern
# =============================================================================


def get_capital_router() -> APIRouter:
    """Create and configure capital management router.

    Follows the router factory pattern from other domains.
    """
    router = APIRouter(prefix="/capital", tags=["capital"])

    # -------------------------------------------------------------------------
    # Capital Pool Endpoints
    # -------------------------------------------------------------------------

    @router.get(
        "/pools",
        response_model=CapitalPoolsListResponse,
        responses={500: {"model": ErrorResponse, "description": "Internal error"}},
    )
    async def list_capital_pools() -> CapitalPoolsListResponse:
        """List all capital pools.

        Returns all capital pools with their current utilization.
        """
        pools = await get_all_pools()
        return CapitalPoolMapper.to_list_response(pools)

    @router.post(
        "/pools",
        response_model=CapitalPoolResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            409: {"model": ErrorResponse, "description": "Pool already exists"},
        },
    )
    async def create_capital_pool(
        request: CreateCapitalPoolRequest,
    ) -> CapitalPoolResponse:
        """Create a new capital pool.

        Args:
            request: Pool creation parameters

        Returns:
            Created capital pool
        """
        try:
            pool = await create_pool(
                pool_id=request.pool_id,
                name=request.name,
                initial_capital=request.initial_capital,
                currency=request.currency,
            )
            return CapitalPoolMapper.to_response(pool)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e

    @router.get(
        "/pools/{pool_id}",
        response_model=CapitalPoolResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Pool not found"},
        },
    )
    async def get_capital_pool(
        pool_id: str = Path(..., description="Pool identifier"),
    ) -> CapitalPoolResponse:
        """Get a specific capital pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Capital pool details
        """
        pool = await get_pool(pool_id)
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pool {pool_id} not found",
            )
        return CapitalPoolMapper.to_response(pool)

    # -------------------------------------------------------------------------
    # Capital Allocation Endpoints
    # -------------------------------------------------------------------------

    @router.get(
        "/allocations",
        response_model=CapitalAllocationListResponse,
    )
    async def list_capital_allocations(
        pool_id: str | None = Query(default=None, description="Filter by pool ID"),
    ) -> CapitalAllocationListResponse:
        """List all capital allocations.

        Args:
            pool_id: Optional filter by pool ID

        Returns:
            List of capital allocations
        """
        allocations = await get_all_allocations(pool_id=pool_id)
        return CapitalAllocationMapper.to_list_response(allocations)

    @router.post(
        "/bots/{bot_type}/{instance_id}/allocate",
        response_model=AllocateCapitalResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            404: {"model": ErrorResponse, "description": "Pool not found"},
        },
    )
    async def allocate_capital(
        request: AllocateCapitalRequest,
        bot_type: str = Path(..., description="Bot type (e.g., 'neat_swing')", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
        pool_id: str = Query(..., description="Pool to allocate from"),
    ) -> AllocateCapitalResponse:
        """Allocate capital to a bot from a pool.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier
            pool_id: Pool to allocate from
            request: Allocation parameters

        Returns:
            Created allocation
        """
        try:
            allocation = await allocate_to_bot(
                bot_type=bot_type,
                bot_instance_id=instance_id,
                pool_id=pool_id,
                amount=Money(amount=request.amount, currency=request.currency),
            )
            return CapitalAllocationMapper.to_allocate_response(allocation)
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_msg,
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            ) from e

    @router.post(
        "/bots/{bot_type}/{instance_id}/deallocate",
        response_model=DeallocateCapitalResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Allocation not found"},
        },
    )
    async def deallocate_capital(
        bot_type: str = Path(..., description="Bot type", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
        pool_id: str = Query(..., description="Pool to return capital to"),
        request: DeallocateCapitalRequest | None = None,
    ) -> DeallocateCapitalResponse:
        """Deallocate capital from a bot back to pool.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier
            pool_id: Pool to return capital to
            request: Request body (optional)

        Returns:
            Deallocation result
        """
        allocation = await get_bot_allocation(bot_type, instance_id)
        if not allocation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No allocation found for {bot_type}/{instance_id}",
            )

        deallocated_amount = allocation.allocated_amount.amount
        success = await deallocate_from_bot(bot_type, instance_id, pool_id)

        return DeallocateCapitalResponse(
            bot_type=bot_type,
            bot_instance_id=instance_id,
            pool_id=pool_id,
            deallocated_amount=deallocated_amount if success else 0.0,
            currency=allocation.allocated_amount.currency,
            success=success,
            message="Deallocation successful" if success else "Deallocation failed",
        )

    @router.get(
        "/bots/{bot_type}/{instance_id}/allocation",
        response_model=CapitalAllocationResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Allocation not found"},
        },
    )
    async def get_bot_allocation_endpoint(
        bot_type: str = Path(..., description="Bot type", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
    ) -> CapitalAllocationResponse:
        """Get capital allocation for a specific bot.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier

        Returns:
            Bot's capital allocation
        """
        allocation = await get_bot_allocation(bot_type, instance_id)
        if not allocation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No allocation found for {bot_type}/{instance_id}",
            )
        return CapitalAllocationMapper.to_response(allocation)

    # -------------------------------------------------------------------------
    # Rebalancing Endpoints
    # -------------------------------------------------------------------------

    @router.post(
        "/pools/{pool_id}/rebalance",
        response_model=RebalanceResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            404: {"model": ErrorResponse, "description": "Pool not found"},
        },
    )
    async def rebalance_capital(
        pool_id: str = Path(..., description="Pool to rebalance"),
        request: RebalanceRequest | None = None,
    ) -> RebalanceResponse:
        """Rebalance capital across bots in a pool.

        Args:
            pool_id: Pool to rebalance
            request: Rebalance targets with target percentages

        Returns:
            Rebalance results
        """
        if not request:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rebalance targets required",
            )

        rebalance_targets = [
            {
                "bot_type": t.bot_type,
                "instance_id": t.instance_id,
                "target_pct": t.target_pct / 100.0,
            }
            for t in request.rebalance_targets
        ]

        use_case = RebalanceCapitalUseCase()
        try:
            allocations = await use_case.execute(
                pool_id=pool_id,
                rebalance_targets=rebalance_targets,
            )
            return RebalanceResponse(
                pool_id=pool_id,
                total_rebalanced=len(allocations),
                allocations=[CapitalAllocationMapper.to_response(a) for a in allocations],
                message=f"Successfully rebalanced {len(allocations)} allocations",
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e

    return router


# =============================================================================
# Legacy router export for backward compatibility
# =============================================================================

router = get_capital_router()
