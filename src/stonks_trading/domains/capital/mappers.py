"""Mappers for capital management domain.

Converts between entities and DTOs.
Pure transformation - no business logic.
"""

from stonks_trading.domains.capital.dtos import (
    AllocateCapitalResponse,
    CapitalAllocationListResponse,
    CapitalAllocationResponse,
    CapitalPoolResponse,
    CapitalPoolsListResponse,
    DeallocateCapitalResponse,
    RebalanceResponse,
)
from stonks_trading.domains.capital.entities import CapitalAllocation, CapitalPool


class CapitalPoolMapper:
    """Map between CapitalPool entity and response DTOs."""

    @staticmethod
    def to_response(entity: CapitalPool) -> CapitalPoolResponse:
        """Convert CapitalPool entity to response DTO."""
        return CapitalPoolResponse(
            id=entity.id,
            pool_id=entity.pool_id,
            name=entity.name,
            total_capital=entity.total_capital.amount,
            available_capital=entity.available_capital.amount,
            reserved_capital=entity.reserved_capital.amount,
            currency=entity.total_capital.currency,
            min_allocation=100.0,
            rebalance_threshold_pct=5.0,
            is_active=True,
            utilization_pct=entity.utilization_pct(),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def to_list_response(entities: list[CapitalPool]) -> CapitalPoolsListResponse:
        """Convert list of CapitalPool entities to list response."""
        pools = [CapitalPoolMapper.to_response(e) for e in entities]
        total_capital = sum(p.total_capital for p in pools)
        return CapitalPoolsListResponse(
            pools=pools,
            total=len(pools),
            total_capital=total_capital,
        )


class CapitalAllocationMapper:
    """Map between CapitalAllocation entity and response DTOs."""

    @staticmethod
    def to_response(entity: CapitalAllocation) -> CapitalAllocationResponse:
        """Convert CapitalAllocation entity to response DTO."""
        current_return = entity.current_return()
        unrealized_pnl: float | None = None
        if current_return is not None and entity.current_value is not None:
            unrealized_pnl = current_return.amount

        return CapitalAllocationResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            pool_id=entity.pool_id or "",
            allocated_amount=entity.allocated_amount.amount,
            current_value=entity.current_value.amount if entity.current_value else None,
            unrealized_pnl=unrealized_pnl,
            roi_pct=entity.roi_pct,
            status="active" if entity.roi_pct is not None else "pending",
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def to_allocate_response(entity: CapitalAllocation) -> AllocateCapitalResponse:
        """Convert CapitalAllocation entity to allocate response DTO."""
        return AllocateCapitalResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            pool_id=entity.pool_id or "",
            allocated_amount=entity.allocated_amount.amount,
            currency=entity.allocated_amount.currency,
            current_value=entity.current_value.amount if entity.current_value else None,
            roi_pct=entity.roi_pct,
            status="active",
            created_at=entity.created_at,
        )

    @staticmethod
    def to_deallocate_response(
        entity: CapitalAllocation | None,
        success: bool,
        deallocated_amount: float = 0.0,
    ) -> DeallocateCapitalResponse:
        """Convert deallocation result to response DTO."""
        return DeallocateCapitalResponse(
            bot_type=entity.bot_type if entity else "",
            bot_instance_id=entity.bot_instance_id if entity else "",
            pool_id=entity.pool_id or "" if entity else "",
            deallocated_amount=deallocated_amount,
            currency=entity.allocated_amount.currency if entity else "USDT",
            success=success,
            message="Deallocation successful" if success else "Deallocation failed",
        )

    @staticmethod
    def to_list_response(entities: list[CapitalAllocation]) -> CapitalAllocationListResponse:
        """Convert list of CapitalAllocation entities to list response."""
        return CapitalAllocationListResponse(
            allocations=[CapitalAllocationMapper.to_response(e) for e in entities],
            total=len(entities),
        )

    @staticmethod
    def to_rebalance_response(
        pool_id: str,
        entities: list[CapitalAllocation],
        total_rebalanced: int,
    ) -> RebalanceResponse:
        """Convert rebalance result to response DTO."""
        return RebalanceResponse(
            pool_id=pool_id,
            total_rebalanced=total_rebalanced,
            allocations=[CapitalAllocationMapper.to_response(e) for e in entities],
            message=f"Rebalanced {total_rebalanced} allocations",
        )
