"""Mappers for converting between domain entities and API DTOs.

Mappers are used ONLY by the API layer - not imported by the bot.
They handle conversion between internal domain representation
and external API format.
"""

from stonks_trading.domains.trading.dtos import (
    BalanceItem,
    BalanceResponse,
    BotInstanceResponse,
    BotStateResponse,
    GenomeResponse,
    MarketDataResponse,
    PositionResponse,
    RiskEventResponse,
    TradeResponse,
)
from stonks_trading.domains.trading.entities import (
    Balance,
    BotInstance,
    BotState,
    Genome,
    MarketData,
    Position,
    RiskEvent,
    Trade,
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
            mode=entity.mode.value if hasattr(entity.mode, 'value') else str(entity.mode),
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
