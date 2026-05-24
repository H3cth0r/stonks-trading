"""Mappers for converting between domain entities and API DTOs.

Mappers are used ONLY by the API layer - not imported by the bot.
They handle conversion between internal domain representation
and external API format.
"""

from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.dtos import (
    ActivityItemResponse,
    BalanceItem,
    BalanceResponse,
    BotInstanceResponse,
    BotStateResponse,
    CheckpointResponse,
    GenomeResponse,
    MarketDataResponse,
    OrderResponse,
    PositionResponse,
    RiskEventResponse,
    TradeResponse,
    TrainingRunResponse,
    VenueBalanceItemResponse,
    VenueBalanceResponse,
)
from stonks_trading.domains.trading.entities import (
    ActivityItem,
    Balance,
    BotInstance,
    Checkpoint,
    Genome,
    MarketData,
    Order,
    Position,
    RiskEvent,
    Trade,
    TrainingRun,
)
from stonks_trading.domains.trading.value_objects import Money


class TradeMapper:
    """Maps between Trade entity and API DTOs."""

    @staticmethod
    def to_response(entity: Trade) -> TradeResponse:
        """Convert domain entity to API response DTO."""
        return TradeResponse(
            id=entity.id or 0,
            symbol=entity.symbol.value,
            side=entity.side.value,
            fill_price=entity.fill_price.amount,
            quantity=entity.quantity,
            fee=entity.fee.amount,
            created_at=entity.created_at,
            order_id=entity.order_id,
        )

    @staticmethod
    def to_response_list(entities: list[Trade]) -> list[TradeResponse]:
        """Convert list of entities to response DTOs."""
        return [TradeMapper.to_response(e) for e in entities]


class PositionMapper:
    """Maps between Position entity and API DTOs."""

    @staticmethod
    def to_response(
        entity: Position,
        current_price: Money | None = None,
    ) -> PositionResponse:
        """Convert domain entity to API response DTO.

        Args:
            entity: Position entity
            current_price: Current market price for P&L calc
        """
        unrealized_pnl = 0.0
        market_value = 0.0

        if current_price and entity.is_open():
            unrealized_pnl = entity.calculate_unrealized_pnl_pct(current_price)
            market_value = entity.calculate_market_value(current_price).amount

        return PositionResponse(
            id=entity.id or 0,
            symbol=entity.symbol.value,
            quantity=entity.quantity,
            entry_price=entity.entry_price.amount if entity.entry_price else None,
            unrealized_pnl_pct=unrealized_pnl,
            market_value=market_value,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def to_response_list(
        entities: list[Position],
        prices: dict[str, Money] | None = None,
    ) -> list[PositionResponse]:
        """Convert list of entities to response DTOs."""
        prices = prices or {}
        return [PositionMapper.to_response(e, prices.get(e.symbol.value)) for e in entities]


class GenomeMapper:
    """Maps between Genome entity and API DTOs."""

    @staticmethod
    def to_response(entity: Genome) -> GenomeResponse:
        """Convert domain entity to API response DTO."""
        return GenomeResponse(
            id=entity.id or 0,
            symbol=entity.symbol.value if entity.symbol else None,
            fitness=entity.fitness,
            generation=entity.generation,
            fee_rate=entity.fee_rate,
            slippage_bps=entity.slippage_bps,
            mode=entity.mode,
            is_active=entity.is_active,
            created_at=entity.created_at,
        )

    @staticmethod
    def to_response_list(entities: list[Genome]) -> list[GenomeResponse]:
        """Convert list of entities to response DTOs."""
        return [GenomeMapper.to_response(e) for e in entities]


class RiskEventMapper:
    """Maps between RiskEvent entity and API DTOs."""

    @staticmethod
    def to_response(entity: RiskEvent) -> RiskEventResponse:
        """Convert domain entity to API response DTO."""
        return RiskEventResponse(
            id=entity.id or 0,
            event_type=entity.event_type,
            severity=entity.severity,
            message=entity.message,
            symbol=entity.symbol.value if entity.symbol else None,
            metric_name=entity.metric_name,
            metric_value=entity.metric_value,
            threshold_value=entity.threshold_value,
            created_at=entity.created_at,
            acknowledged_at=entity.acknowledged_at,
        )

    @staticmethod
    def to_response_list(entities: list[RiskEvent]) -> list[RiskEventResponse]:
        """Convert list of entities to response DTOs."""
        return [RiskEventMapper.to_response(e) for e in entities]


class MarketDataMapper:
    """Maps between MarketData entity and API DTOs."""

    @staticmethod
    def to_response(entity: MarketData) -> MarketDataResponse:
        """Convert domain entity to API response DTO."""
        return MarketDataResponse(
            symbol=entity.symbol.value,
            timestamp=entity.timestamp,
            open=entity.open,
            high=entity.high,
            low=entity.low,
            close=entity.close,
            volume=entity.volume,
        )

    @staticmethod
    def to_response_list(entities: list[MarketData]) -> list[MarketDataResponse]:
        """Convert list of entities to response DTOs."""
        return [MarketDataMapper.to_response(e) for e in entities]


class BalanceMapper:
    """Maps between Balance entity and API DTOs."""

    @staticmethod
    def to_item(entity: Balance) -> BalanceItem:
        """Convert domain entity to balance item DTO."""
        return BalanceItem(
            asset=entity.asset,
            free=entity.free,
            locked=entity.locked,
            total=entity.total,
        )

    @staticmethod
    def to_response(entities: list[Balance]) -> BalanceResponse:
        """Convert list of balance entities to response DTO."""
        return BalanceResponse(balances=[BalanceMapper.to_item(e) for e in entities])


class BotInstanceMapper:
    """Maps between BotInstance entity and API DTOs."""

    @staticmethod
    def to_response(entity: BotInstance) -> BotInstanceResponse:
        """Convert domain entity to API response DTO."""
        return BotInstanceResponse(
            id=entity.id or 0,
            bot_type=entity.bot_type,
            instance_id=entity.instance_id,
            symbols=entity.symbols,
            mode=entity.mode.value if hasattr(entity.mode, "value") else str(entity.mode),
            status=entity.status,
            created_at=entity.created_at,
            last_seen_at=entity.last_seen_at,
        )

    @staticmethod
    def to_response_list(entities: list[BotInstance]) -> list[BotInstanceResponse]:
        """Convert list of entities to response DTOs."""
        return [BotInstanceMapper.to_response(e) for e in entities]


class BotStateMapper:
    """Maps between BotState entity and API DTOs."""

    @staticmethod
    def to_response(
        bot_type: str,
        instance_id: str,
        state: dict[str, Any] | None,
        status: str = "unknown",
    ) -> BotStateResponse:
        """Convert domain entity to API response DTO."""
        return BotStateResponse(
            bot_type=bot_type,
            instance_id=instance_id,
            status=status,
            state=state or {},
        )


class ActivityMapper:
    """Maps between ActivityItem entity and API DTOs."""

    @staticmethod
    def to_response(entity: ActivityItem) -> ActivityItemResponse:
        """Convert domain entity to API response DTO."""
        return ActivityItemResponse(
            id=entity.id or 0,
            type=entity.type,
            timestamp=entity.timestamp,
            symbol=entity.symbol.value if entity.symbol else None,
            data=entity.data,
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
        )

    @staticmethod
    def to_response_list(entities: list[ActivityItem]) -> list[ActivityItemResponse]:
        """Convert list of entities to response DTOs."""
        return [ActivityMapper.to_response(e) for e in entities]


class OrderMapper:
    """Maps between Order entity and API DTOs."""

    @staticmethod
    def to_response(entity: Order) -> OrderResponse:
        """Convert domain entity to API response DTO."""
        return OrderResponse(
            order_id=entity.client_order_id or entity.venue_order_id or "unknown",
            symbol=entity.symbol.value if entity.symbol else "",
            side=entity.side.value if hasattr(entity.side, "value") else str(entity.side),
            order_type=entity.order_type,
            status=entity.status,
            quantity=entity.quantity,
            filled_quantity=entity.filled_quantity,
            price=entity.price.amount if entity.price else None,
            fill_price=entity.avg_fill_price.amount if entity.avg_fill_price else None,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
        )

    @staticmethod
    def to_response_list(entities: list[Order]) -> list[OrderResponse]:
        """Convert list of entities to response DTOs."""
        return [OrderMapper.to_response(e) for e in entities]


class VenueBalanceMapper:
    """Maps between Balance entity and Venue API DTOs."""

    @staticmethod
    def to_item(entity: Balance) -> VenueBalanceItemResponse:
        """Convert domain entity to venue balance item DTO."""
        return VenueBalanceItemResponse(
            asset=entity.asset,
            free=entity.free,
            locked=entity.locked,
            total=entity.total,
        )

    @staticmethod
    def to_response(
        balances: list[Balance],
        venue: str,
        synced_at: datetime,
    ) -> VenueBalanceResponse:
        """Convert list of balance entities to venue response DTO."""
        return VenueBalanceResponse(
            venue=venue,
            balances=[VenueBalanceMapper.to_item(b) for b in balances],
            synced_at=synced_at,
        )


class TrainingRunMapper:
    """Maps between TrainingRun entity and API DTOs."""

    @staticmethod
    def to_response(entity: TrainingRun) -> TrainingRunResponse:
        """Convert domain entity to API response DTO."""
        return TrainingRunResponse(
            id=entity.id or 0,
            symbol=entity.symbol.value if entity.symbol else "",
            status=entity.status,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            best_fitness=entity.best_fitness,
            best_validation_roi=entity.best_roi_validation,
            generations_completed=entity.generations,
            git_sha=entity.trainer_git_sha or "unknown",
            config={
                "model_family": entity.model_family,
                "episode_steps": entity.episode_steps,
                "pop_size": entity.pop_size,
                "fee_rate": entity.fee_rate,
            },
            bot_type="neat_swing",  # Default - bot context may be added later
            bot_instance_id="default",
        )

    @staticmethod
    def to_response_list(entities: list[TrainingRun]) -> list[TrainingRunResponse]:
        """Convert list of entities to response DTOs."""
        return [TrainingRunMapper.to_response(e) for e in entities]


class CheckpointMapper:
    """Maps between Checkpoint entity and API DTOs."""

    @staticmethod
    def to_response(entity: Checkpoint) -> CheckpointResponse:
        """Convert domain entity to API response DTO."""
        return CheckpointResponse(
            generation=entity.generation,
            artifact_uri=entity.artifact_uri,
            size_bytes=entity.size_bytes,
            created_at=entity.created_at,
            fitness=entity.fitness,
        )

    @staticmethod
    def to_response_list(entities: list[Checkpoint]) -> list[CheckpointResponse]:
        """Convert list of entities to response DTOs."""
        return [CheckpointMapper.to_response(e) for e in entities]
