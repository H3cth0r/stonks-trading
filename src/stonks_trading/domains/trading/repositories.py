"""Repository functions for trading domain.

Standalone functions (no classes, no ABC, no inheritance).
Tortoise ORM handles connection pooling; use transactions for test isolation.

Each repository function operates on a single entity type and performs
data access only - no business logic.
"""

from datetime import datetime, timedelta
from typing import Any

from stonks_trading.domains.trading.entities import (
    BotDecision,
    BotInstance,
    DataGap,
    GenerationMetric,
    Genome,
    Order,
    Position,
    RiskEvent,
    SystemConfig,
    Trade,
    TrainingRun,
)
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import BotContext, Money, Symbol
from stonks_trading.shared.postgres_models import (
    BotDecisionModel,
    BotInstanceModel,
    BotStateModel,
    DataGapModel,
    GenerationMetricModel,
    GenomeModel,
    OrderModel,
    PositionModel,
    RiskEventModel,
    SystemConfigModel,
    TradeModel,
    TradeSide,
    TrainingRunModel,
)

# Default context for backward compatibility (Phase 5)
DEFAULT_CONTEXT = BotContext(bot_type="neat_swing", instance_id="default")

# =============================================================================
# Trade Repository Functions
# =============================================================================


async def save_trade_with_context(trade: Trade, context: BotContext) -> Trade:
    """Persist trade with bot context using Tortoise ORM."""
    model = await TradeModel.create(
        symbol=trade.symbol.value,
        side=TradeSide(trade.side.value),
        fill_price=trade.fill_price.amount,
        quantity=trade.quantity,
        fee=trade.fee.amount,
        fee_currency=trade.fee.currency,
        realized_pnl=trade.realized_pnl.amount if trade.realized_pnl else None,
        order_id=trade.order_id,
        intended_price=trade.intended_price.amount if trade.intended_price else None,
        slippage_bps=trade.slippage_bps,
        quote_quantity=trade.quote_quantity,
        fee_rate=trade.fee_rate,
        mode=TradingMode(trade.mode.value)
        if isinstance(trade.mode, TradingMode)
        else TradingMode(trade.mode)
        if trade.mode
        else TradingMode.BACKTEST,
        genome_id=trade.genome_id,
        entry_price=trade.entry_price.amount if trade.entry_price else None,
        latency_ms=trade.latency_ms,
        exchange=trade.exchange,
        strategy=trade.strategy,
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    )
    trade.id = model.id
    return trade


async def save_trade(trade: Trade) -> Trade:
    """Persist trade using Tortoise ORM (legacy wrapper with default context)."""
    context = DEFAULT_CONTEXT
    if (
        trade.bot_type != DEFAULT_CONTEXT.bot_type
        or trade.bot_instance_id != DEFAULT_CONTEXT.instance_id
    ):
        context = BotContext(bot_type=trade.bot_type, instance_id=trade.bot_instance_id)
    return await save_trade_with_context(trade, context)


async def get_trade_by_id(trade_id: int) -> Trade | None:
    """Retrieve trade by ID."""
    model = await TradeModel.get_or_none(id=trade_id)
    if not model:
        return None
    return _model_to_trade(model)


async def list_trades_by_symbol(
    symbol: Symbol,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> list[Trade]:
    """List trades for symbol with optional date filter."""
    query = TradeModel.filter(symbol=symbol.value)
    if start:
        query = query.filter(created_at__gte=start)
    if end:
        query = query.filter(created_at__lte=end)
    models = await query.limit(limit).order_by("-created_at")
    return [_model_to_trade(m) for m in models]


async def list_trades_by_bot(
    context: BotContext,
    symbol: Symbol | None = None,
    limit: int = 100,
) -> list[Trade]:
    """List trades for a specific bot context."""
    query = TradeModel.filter(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    )
    if symbol:
        query = query.filter(symbol=symbol.value)
    models = await query.limit(limit).order_by("-created_at")
    return [_model_to_trade(m) for m in models]


async def list_trades(limit: int = 100, offset: int = 0) -> list[Trade]:
    """List all trades with pagination (legacy wrapper with default context)."""
    models = (
        await TradeModel.filter(
            bot_type=DEFAULT_CONTEXT.bot_type,
            bot_instance_id=DEFAULT_CONTEXT.instance_id,
        )
        .offset(offset)
        .limit(limit)
        .order_by("-created_at")
    )
    return [_model_to_trade(m) for m in models]


def _model_to_trade(model: TradeModel) -> Trade:
    """Convert TradeModel to Trade entity."""
    return Trade(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        side=Side(model.side.value),
        fill_price=Money(amount=model.fill_price, currency=model.fee_currency),
        quantity=model.quantity,
        fee=Money(amount=model.fee, currency=model.fee_currency),
        fee_currency=model.fee_currency,
        realized_pnl=Money(amount=model.realized_pnl, currency=model.fee_currency)
        if model.realized_pnl
        else None,
        order_id=model.order_id,
        intended_price=Money(amount=model.intended_price, currency=model.fee_currency)
        if model.intended_price
        else None,
        slippage_bps=model.slippage_bps,
        quote_quantity=model.quote_quantity,
        fee_rate=model.fee_rate,
        mode=model.mode,  # type: ignore[arg-type]
        genome_id=model.genome_id,
        entry_price=Money(amount=model.entry_price, currency=model.fee_currency)
        if model.entry_price
        else None,
        latency_ms=model.latency_ms,
        exchange=model.exchange,
        strategy=model.strategy,
        created_at=model.created_at,
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
    )


async def count_trades_today() -> int:
    """Count trades executed today (since midnight UTC)."""
    now = datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    count = await TradeModel.filter(created_at__gte=start_of_day).count()
    return count


# =============================================================================
# Position Repository Functions
# =============================================================================


async def get_position_by_bot_and_symbol(context: BotContext, symbol: Symbol) -> Position | None:
    """Get open position for symbol within bot context."""
    model = await PositionModel.get_or_none(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
        symbol=symbol.value,
    )
    if not model:
        return None
    return _model_to_position(model)


async def get_position_by_symbol(symbol: Symbol) -> Position | None:
    """Get open position for symbol (legacy wrapper with default context)."""
    return await get_position_by_bot_and_symbol(DEFAULT_CONTEXT, symbol)


async def save_position_with_context(position: Position, context: BotContext) -> Position:
    """Save position within bot context. Creates new or updates existing."""
    existing = await PositionModel.get_or_none(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
        symbol=position.symbol.value,
    )
    if existing:
        existing.quantity = position.quantity
        existing.entry_price = float(position.entry_price.amount) if position.entry_price else None  # type: ignore[assignment]
        existing.current_price = (
            float(position.current_price.amount) if position.current_price else None  # type: ignore[assignment]
        )
        existing.unrealized_pnl = position.unrealized_pnl
        await existing.save()
        position.id = existing.id
    else:
        model = await PositionModel.create(
            symbol=position.symbol.value,
            quantity=position.quantity,
            entry_price=float(position.entry_price.amount) if position.entry_price else None,
            current_price=float(position.current_price.amount) if position.current_price else None,
            unrealized_pnl=position.unrealized_pnl,
            bot_type=context.bot_type,
            bot_instance_id=context.instance_id,
        )
        position.id = model.id
    return position


async def save_position(position: Position) -> Position:
    """Save position (legacy wrapper with default context)."""
    context = DEFAULT_CONTEXT
    if (
        position.bot_type != DEFAULT_CONTEXT.bot_type
        or position.bot_instance_id != DEFAULT_CONTEXT.instance_id
    ):
        context = BotContext(bot_type=position.bot_type, instance_id=position.bot_instance_id)
    return await save_position_with_context(position, context)


async def close_position_by_bot(context: BotContext, symbol: Symbol) -> bool:
    """Close position for symbol within bot context."""
    model = await PositionModel.get_or_none(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
        symbol=symbol.value,
    )
    if not model:
        return False
    model.quantity = 0.0
    await model.save()
    return True


async def close_position(symbol: Symbol) -> bool:
    """Close position for symbol (legacy wrapper with default context)."""
    return await close_position_by_bot(DEFAULT_CONTEXT, symbol)


async def list_positions_by_bot(context: BotContext) -> list[Position]:
    """List all positions for a specific bot context."""
    models = await PositionModel.filter(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    )
    return [_model_to_position(m) for m in models]


async def list_positions() -> list[Position]:
    """List all positions (legacy wrapper with default context)."""
    models = await PositionModel.filter(
        bot_type=DEFAULT_CONTEXT.bot_type,
        bot_instance_id=DEFAULT_CONTEXT.instance_id,
    )
    return [_model_to_position(m) for m in models]


def _model_to_position(model: PositionModel) -> Position:
    """Convert PositionModel to Position entity."""
    return Position(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        quantity=model.quantity,
        entry_price=Money(amount=model.entry_price, currency="USD") if model.entry_price else None,
        current_price=Money(amount=model.current_price, currency="USD")
        if model.current_price
        else None,
        unrealized_pnl=model.unrealized_pnl,
        created_at=datetime.utcnow(),  # PositionModel tracks updated_at only
        updated_at=model.updated_at,
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
    )


# =============================================================================
# Genome Repository Functions
# =============================================================================


async def save_genome(genome: Genome) -> Genome:
    """Persist genome with metadata."""
    model = await GenomeModel.create(
        symbol=genome.symbol.value if genome.symbol else None,
        genome_data=genome.genome_data,
        fitness=genome.fitness,
        generation=genome.generation,
        model_family=genome.model_family,
        artifact_uri=genome.artifact_uri,
        trainer_git_sha=genome.trainer_git_sha,
        feature_schema_id=genome.feature_schema_id,
        is_active=genome.is_active,
        roi_validation=genome.roi_validation,
        roi_test=genome.roi_test,
        max_drawdown=genome.max_drawdown,
        num_trades=genome.trades_count,
        total_return=genome.total_return,
        fitness_score=genome.fitness,
        fee_rate_used=genome.fee_rate_used,
        trained_at=genome.trained_at or datetime.utcnow(),
        activated_at=genome.activated_at,
        deactivated_at=genome.deactivated_at,
    )
    genome.id = model.id
    return genome


async def get_genome_by_id(genome_id: int) -> Genome | None:
    """Retrieve genome by ID."""
    model = await GenomeModel.get_or_none(id=genome_id)
    if not model:
        return None
    return _model_to_genome(model)


async def get_active_genome(symbol: Symbol | None = None) -> Genome | None:
    """Get currently active genome for trading."""
    query = GenomeModel.filter(is_active=True)
    if symbol:
        query = query.filter(symbol=symbol.value)
    model = await query.first()
    if not model:
        return None
    return _model_to_genome(model)


async def list_genomes(
    symbol: Symbol | None = None,
    limit: int = 100,
) -> list[Genome]:
    """List genomes with optional symbol filter."""
    query = GenomeModel.all()
    if symbol:
        query = query.filter(symbol=symbol.value)
    models = await query.limit(limit).order_by("-id")
    return [_model_to_genome(m) for m in models]


async def activate_genome(genome_id: int) -> bool:
    """Activate genome for live trading. Deactivates others."""
    # Deactivate all genomes for the same symbol first
    model = await GenomeModel.get_or_none(id=genome_id)
    if not model:
        return False

    # Deactivate others with same symbol
    if model.symbol:
        await GenomeModel.filter(symbol=model.symbol, is_active=True).update(is_active=False)

    # Activate this one
    model.is_active = True
    await model.save()
    return True


def _model_to_genome(model: GenomeModel) -> Genome:
    """Convert GenomeModel to Genome entity."""
    return Genome(
        id=model.id,
        genome_data=model.genome_data or b"",
        fitness=model.fitness_score or model.fitness,  # type: ignore[attr-defined]
        generation=0,
        symbol=Symbol(value=model.symbol) if model.symbol else None,
        model_family=model.model_family,
        artifact_uri=model.artifact_uri,
        trainer_git_sha=model.trainer_git_sha,
        feature_schema_id=model.feature_schema_id,
        is_active=model.is_active,
        roi_validation=model.roi_validation,
        roi_test=model.roi_test,
        max_drawdown=model.max_drawdown or 0.0,
        total_return=model.total_return or 0.0,
        trades_count=model.num_trades or 0,
        fee_rate_used=model.fee_rate_used,
        trained_at=model.trained_at,
        activated_at=model.activated_at,
        deactivated_at=model.deactivated_at,
        created_at=model.trained_at or datetime.utcnow(),  # Genome uses trained_at
    )


# =============================================================================
# Risk Event Repository Functions
# =============================================================================


async def save_risk_event(event: RiskEvent) -> RiskEvent:
    """Persist risk event for audit trail."""
    model = await RiskEventModel.create(
        event_type=event.event_type,
        severity=event.severity,
        message=event.message,
        symbol=event.symbol.value if event.symbol else None,
        value=event.value,
        threshold=event.threshold,
        notified=event.notified,
        mode=TradingMode(event.mode.value)
        if isinstance(event.mode, TradingMode)
        else TradingMode.DRY_RUN,
        metric_name=event.metric_name,
        metric_value=event.metric_value,
        portfolio_value=float(event.portfolio_value.amount) if event.portfolio_value else None,
        position_value=float(event.position_value.amount) if event.position_value else None,
    )
    event.id = model.id
    return event


async def list_risk_events(
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> list[RiskEvent]:
    """List risk events with filters."""
    query = RiskEventModel.all()
    if severity:
        query = query.filter(severity=severity)
    if acknowledged is not None:
        query = query.filter(acknowledged_at__isnull=not acknowledged)
    models = await query.limit(limit).order_by("-created_at")
    return [_model_to_risk_event(m) for m in models]


async def list_risk_events_by_bot(
    context: BotContext,
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> list[RiskEvent]:
    """List risk events filtered by bot context."""
    query = RiskEventModel.filter(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    )
    if severity:
        query = query.filter(severity=severity)
    if acknowledged is not None:
        query = query.filter(acknowledged_at__isnull=not acknowledged)
    models = await query.limit(limit).order_by("-created_at")
    return [_model_to_risk_event(m) for m in models]


async def acknowledge_risk_event(
    event_id: int,
    user: str,
    action: str | None = None,
) -> RiskEvent | None:
    """Mark risk event as acknowledged."""
    model = await RiskEventModel.get_or_none(id=event_id)
    if not model:
        return None
    model.acknowledged_at = datetime.utcnow()
    model.acknowledged_by = user
    model.action_taken = action  # type: ignore[assignment]
    await model.save()
    return _model_to_risk_event(model)


def _model_to_risk_event(model: RiskEventModel) -> RiskEvent:
    """Convert RiskEventModel to RiskEvent entity."""
    return RiskEvent(
        id=model.id,
        event_type=model.event_type,
        severity=model.severity,
        message=model.message,
        symbol=Symbol(value=model.symbol) if model.symbol else None,
        value=model.value,
        threshold=model.threshold,
        notified=model.notified,
        mode=model.mode,  # type: ignore[arg-type]
        metric_name=model.metric_name,
        metric_value=model.metric_value,
        portfolio_value=Money(amount=model.portfolio_value, currency="USD")
        if model.portfolio_value
        else None,
        position_value=Money(amount=model.position_value, currency="USD")
        if model.position_value
        else None,
        created_at=model.created_at,
        acknowledged_at=model.acknowledged_at,
        acknowledged_by=model.acknowledged_by,
        action_taken=model.action_taken,
    )


# =============================================================================
# Order Repository Functions
# =============================================================================


async def save_order(order: Order) -> Order:
    """Persist order."""
    model = await OrderModel.create(
        symbol=order.symbol.value,
        side=TradeSide(order.side.value),
        requested_qty=order.quantity,
        status=order.status,
        order_type=order.order_type,
        client_order_id=order.client_order_id,
        venue_order_id=order.venue_order_id,
        filled_qty=order.filled_quantity,
        avg_fill_price=float(order.avg_fill_price.amount) if order.avg_fill_price else None,
        mode=TradingMode(order.mode.value)
        if isinstance(order.mode, TradingMode)
        else TradingMode(order.mode),
        genome_id=order.genome_id,
        price=float(order.price.amount) if order.price else None,
    )
    order.id = model.id
    return order


async def get_order_by_id(order_id: int) -> Order | None:
    """Get order by ID."""
    model = await OrderModel.get_or_none(id=order_id)
    if not model:
        return None
    return _model_to_order(model)


async def get_order_by_venue_id(venue_order_id: str) -> Order | None:
    """Get order by venue order ID."""
    model = await OrderModel.get_or_none(venue_order_id=venue_order_id)
    if not model:
        return None
    return _model_to_order(model)


async def update_order_status(
    order_id: int,
    status: str,
    filled_qty: float | None = None,
    avg_fill_price: float | None = None,
) -> Order | None:
    """Update order status."""
    model = await OrderModel.get_or_none(id=order_id)
    if not model:
        return None
    model.status = status
    if filled_qty is not None:
        model.filled_qty = filled_qty
    if avg_fill_price is not None:
        model.avg_fill_price = avg_fill_price
    if status == "filled":
        model.filled_at = datetime.utcnow()
    await model.save()
    return _model_to_order(model)


def _model_to_order(model: OrderModel) -> Order:
    """Convert OrderModel to Order entity."""
    return Order(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        side=Side(model.side.value),
        quantity=model.requested_qty,
        order_type=model.order_type,  # type: ignore[attr-defined]
        status=model.status,
        client_order_id=model.client_order_id,
        venue_order_id=model.venue_order_id,
        filled_quantity=model.filled_qty,
        avg_fill_price=Money(amount=model.avg_fill_price, currency="USDT")
        if model.avg_fill_price
        else None,
        mode=model.mode,  # type: ignore[arg-type]
        genome_id=model.genome_id,
        price=Money(amount=model.price, currency="USDT") if model.price else None,  # type: ignore[attr-defined]
        created_at=model.created_at,
        updated_at=model.updated_at,
        filled_at=model.filled_at,  # type: ignore[attr-defined]
    )


# =============================================================================
# Bot Decision Repository Functions
# =============================================================================


async def save_bot_decision(decision: BotDecision) -> BotDecision:
    """Persist bot decision."""
    model = await BotDecisionModel.create(
        symbol=decision.symbol.value,
        genome_id=decision.genome_id,
        buy_prob=decision.buy_prob,
        sell_prob=decision.sell_prob,
        action=decision.action,
        reason=decision.reason,
        mode=TradingMode(decision.mode.value)
        if isinstance(decision.mode, TradingMode)
        else TradingMode(decision.mode),
        candle_close_at=decision.candle_close_at,
        executed=decision.executed,
        trade_id=decision.trade_id,
    )
    decision.id = model.id
    return decision


async def list_decisions_by_symbol(
    symbol: Symbol,
    limit: int = 100,
) -> list[BotDecision]:
    """List bot decisions for symbol."""
    models = (
        await BotDecisionModel.filter(symbol=symbol.value).limit(limit).order_by("-candle_close_at")
    )
    return [_model_to_bot_decision(m) for m in models]


def _model_to_bot_decision(model: BotDecisionModel) -> BotDecision:
    """Convert BotDecisionModel to BotDecision entity."""
    return BotDecision(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        genome_id=model.genome_id,
        buy_prob=model.buy_prob,
        sell_prob=model.sell_prob,
        action=model.action,
        reason=model.reason,
        mode=model.mode,  # type: ignore[arg-type]
        candle_close_at=model.candle_close_at,
        executed=model.executed,
        trade_id=model.trade_id,
    )


# =============================================================================
# Training Run Repository Functions
# =============================================================================


async def save_training_run(run: TrainingRun) -> TrainingRun:
    """Persist training run."""
    model = await TrainingRunModel.create(
        symbol=run.symbol.value if run.symbol else None,
        model_family=run.model_family,
        artifact_prefix_uri=run.artifact_prefix_uri,
        trainer_git_sha=run.trainer_git_sha,
        generations=run.generations,
        best_fitness=run.best_fitness,
        best_roi_validation=run.best_roi_validation,
        best_roi_test=run.best_roi_test,
        episode_steps=run.episode_steps,
        pop_size=run.pop_size,
        fee_rate=run.fee_rate,
        status=run.status,
        config_snapshot=run.config_snapshot,
    )
    run.id = model.id
    return run


async def update_training_run_status(
    run_id: int,
    status: str,
    best_fitness: float | None = None,
    finished_at: datetime | None = None,
) -> TrainingRun | None:
    """Update training run status."""
    model = await TrainingRunModel.get_or_none(id=run_id)
    if not model:
        return None
    model.status = status
    if best_fitness is not None:
        model.best_fitness = best_fitness
    if finished_at:
        model.finished_at = finished_at
    await model.save()
    return _model_to_training_run(model)


async def get_training_run(run_id: int) -> TrainingRun | None:
    """Get training run by ID."""
    model = await TrainingRunModel.get_or_none(id=run_id)
    if not model:
        return None
    return _model_to_training_run(model)


def _model_to_training_run(model: TrainingRunModel) -> TrainingRun:
    """Convert TrainingRunModel to TrainingRun entity."""
    return TrainingRun(
        id=model.id,
        symbol=Symbol(value=model.symbol) if model.symbol else None,
        model_family=model.model_family,
        artifact_prefix_uri=model.artifact_prefix_uri,
        trainer_git_sha=model.trainer_git_sha,
        generations=model.generations,
        best_fitness=model.best_fitness,
        best_roi_validation=model.best_roi_validation,
        best_roi_test=model.best_roi_test,
        episode_steps=model.episode_steps,
        pop_size=model.pop_size,
        fee_rate=model.fee_rate,
        status=model.status,
        config_snapshot=model.config_snapshot,  # type: ignore[attr-defined]
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


# =============================================================================
# Generation Metric Repository Functions
# =============================================================================


async def save_generation_metric(metric: GenerationMetric) -> GenerationMetric:
    """Persist generation metric."""
    model = await GenerationMetricModel.create(
        run_id=metric.run_id,
        generation=metric.generation,
        best_fitness=metric.best_fitness,
        mean_fitness=metric.mean_fitness,
        worst_fitness=metric.worst_fitness,
        num_species=metric.num_species,
        num_genomes=metric.num_genomes,
        best_roi_validation=metric.best_roi_validation,
        stagnation_count=metric.stagnation_count,
        num_trades_best=metric.num_trades_best,
        max_drawdown_best=metric.max_drawdown_best,
    )
    metric.id = model.id
    return metric


async def list_metrics_by_run(run_id: int) -> list[GenerationMetric]:
    """List metrics for a training run."""
    models = await GenerationMetricModel.filter(run_id=run_id).order_by("generation")
    return [_model_to_generation_metric(m) for m in models]


def _model_to_generation_metric(model: GenerationMetricModel) -> GenerationMetric:
    """Convert GenerationMetricModel to GenerationMetric entity."""
    return GenerationMetric(
        id=model.id,
        run_id=model.run_id,  # type: ignore[attr-defined]
        generation=model.generation,
        best_fitness=model.best_fitness,
        mean_fitness=model.mean_fitness,
        worst_fitness=model.worst_fitness or 0.0,
        num_species=model.num_species or 0,
        num_genomes=model.num_genomes or 0,
        best_roi_validation=model.best_roi_validation,
        stagnation_count=model.stagnation_count,
        num_trades_best=model.num_trades_best,
        max_drawdown_best=model.max_drawdown_best,
        created_at=model.created_at,
    )


# =============================================================================
# Data Gap Repository Functions
# =============================================================================


async def save_data_gap(gap: DataGap) -> DataGap:
    """Persist data gap."""
    model = await DataGapModel.create(
        symbol=gap.symbol.value,
        gap_start=gap.gap_start,
        gap_end=gap.gap_end,
        gap_type=gap.gap_type,
        backfilled=gap.backfilled,
        filled_at=gap.filled_at,
    )
    gap.id = model.id
    return gap


async def mark_gap_filled(gap_id: int) -> bool:
    """Mark data gap as filled."""
    model = await DataGapModel.get_or_none(id=gap_id)
    if not model:
        return False
    model.backfilled = True
    model.filled_at = datetime.utcnow()
    await model.save()
    return True


def _model_to_data_gap(model: DataGapModel) -> DataGap:
    """Convert DataGapModel to DataGap entity."""
    return DataGap(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        gap_start=model.gap_start,
        gap_end=model.gap_end,
        gap_type=model.gap_type,
        backfilled=model.backfilled,
        detected_at=model.created_at,
        filled_at=model.filled_at,
    )


# =============================================================================
# System Config Repository Functions
# =============================================================================


async def get_config(key: str) -> SystemConfig | None:
    """Get system config by key."""
    model = await SystemConfigModel.get_or_none(key=key)
    if not model:
        return None
    return SystemConfig(key=model.key, value=model.value, id=model.id, updated_at=model.updated_at)


async def set_config(key: str, value: Any) -> SystemConfig:
    """Set system config value."""
    model, _ = await SystemConfigModel.update_or_create(
        key=key,
        defaults={"value": value},
    )
    return SystemConfig(key=model.key, value=model.value, id=model.id, updated_at=model.updated_at)


# =============================================================================
# Bot Instance Repository (Phase 5)
# =============================================================================


class BotInstanceRepository:
    """Repository for bot instance registry."""

    @staticmethod
    async def register(
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        config: dict[str, Any] | None = None,
    ) -> BotInstance:
        """Register a new bot instance."""
        model = await BotInstanceModel.create(
            bot_type=bot_type,
            instance_id=instance_id,
            symbols=symbols,
            mode=mode,
            config=config,
            status="stopped",
        )
        return BotInstance(
            bot_type=model.bot_type,
            instance_id=model.instance_id,
            symbols=model.symbols,
            mode=TradingMode(model.mode),
            id=model.id,
            status=model.status,
            config=model.config,
            last_seen_at=model.last_seen_at,
            created_at=model.created_at,
        )

    @staticmethod
    async def get(bot_type: str, instance_id: str) -> BotInstance | None:
        """Get bot instance by type and ID."""
        model = await BotInstanceModel.get_or_none(
            bot_type=bot_type,
            instance_id=instance_id,
        )
        if not model:
            return None
        return BotInstance(
            bot_type=model.bot_type,
            instance_id=model.instance_id,
            symbols=model.symbols,
            mode=TradingMode(model.mode),
            id=model.id,
            status=model.status,
            config=model.config,
            last_seen_at=model.last_seen_at,
            created_at=model.created_at,
        )

    @staticmethod
    async def update_status(bot_type: str, instance_id: str, status: str) -> bool:
        """Update bot instance status."""
        model = await BotInstanceModel.get_or_none(
            bot_type=bot_type,
            instance_id=instance_id,
        )
        if not model:
            return False
        model.status = status  # type: ignore[assignment]
        await model.save()
        return True

    @staticmethod
    async def list_all() -> list[BotInstance]:
        """List all bot instances."""
        models = await BotInstanceModel.all()
        return [
            BotInstance(
                bot_type=m.bot_type,
                instance_id=m.instance_id,
                symbols=m.symbols,
                mode=TradingMode(m.mode),
                id=m.id,
                status=m.status,
                config=m.config,
                last_seen_at=m.last_seen_at,
                created_at=m.created_at,
            )
            for m in models
        ]

    @staticmethod
    async def list_by_type(bot_type: str) -> list[BotInstance]:
        """List bot instances by type."""
        models = await BotInstanceModel.filter(bot_type=bot_type)
        return [
            BotInstance(
                bot_type=m.bot_type,
                instance_id=m.instance_id,
                symbols=m.symbols,
                mode=TradingMode(m.mode),
                id=m.id,
                status=m.status,
                config=m.config,
                last_seen_at=m.last_seen_at,
                created_at=m.created_at,
            )
            for m in models
        ]


# =============================================================================
# Bot State Repository (Phase 5)
# =============================================================================


class BotStateRepository:
    """Repository for bot state persistence."""

    @staticmethod
    async def save(context: BotContext, state: dict[str, Any]) -> None:
        """Save bot state for context."""
        await BotStateModel.create(
            bot_type=context.bot_type,
            bot_instance_id=context.instance_id,
            state_json=state,
        )

    @staticmethod
    async def load(context: BotContext) -> dict[str, Any] | None:
        """Load most recent bot state for context."""
        model = (
            await BotStateModel.filter(
                bot_type=context.bot_type,
                bot_instance_id=context.instance_id,
            )
            .order_by("-created_at")
            .first()
        )
        return model.state_json if model else None


# =============================================================================
# Order Repository (Phase 6)
# =============================================================================


async def list_orders(
    bot_context: BotContext | None = None,
    status: str | None = None,
    symbol: Symbol | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Order]:
    """List orders with optional filtering.

    Pure data access - no business logic. Filtering is query parameter only.
    """
    query = OrderModel.all()

    if bot_context:
        query = query.filter(
            bot_type=bot_context.bot_type,
            bot_instance_id=bot_context.instance_id,
        )

    if status:
        query = query.filter(status=status)

    if symbol:
        query = query.filter(symbol=symbol.value)

    models = await query.order_by("-created_at").offset(offset).limit(limit)

    return [_model_to_order(m) for m in models]


async def get_order_by_client_id(client_order_id: str) -> Order | None:
    """Get order by client order ID."""
    model = await OrderModel.get_or_none(client_order_id=client_order_id)
    if not model:
        return None
    return _model_to_order(model)


def _model_to_order(model: OrderModel) -> Order:
    """Convert OrderModel to Order entity - pure transformation, no logic."""
    return Order(
        id=model.id,
        client_order_id=model.client_order_id,
        venue_order_id=model.venue_order_id,
        symbol=Symbol(model.symbol),
        side=Side(model.side.value) if hasattr(model.side, "value") else Side.BUY,
        order_type="market",
        status=model.status,
        quantity=model.requested_qty,
        filled_quantity=model.filled_qty,
        price=None,
        fill_price=model.avg_fill_price,
        mode=TradingMode(model.mode.value) if hasattr(model.mode, "value") else TradingMode.DRY_RUN,
        created_at=model.created_at,
        updated_at=model.updated_at,
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
    )


# =============================================================================
# Training Run Repository (Phase 6)
# =============================================================================


async def list_training_runs(
    status: str | None = None,
    symbol: Symbol | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TrainingRun]:
    """List training runs with optional filtering.

    Pure data access - no business logic.
    """
    query = TrainingRunModel.all()

    if status:
        query = query.filter(status=status)

    if symbol:
        query = query.filter(symbol=symbol.value)

    models = await query.order_by("-started_at").offset(offset).limit(limit)

    return [_model_to_training_run(m) for m in models]


# =============================================================================
# Genome Repository Extensions (Phase 6)
# =============================================================================


async def prune_genomes(
    retention_days: int = 30,
    keep_active: bool = True,
    dry_run: bool = True,
) -> tuple[int, list[int]]:
    """Prune old genomes based on retention policy.

    Pure data access - policy logic is in use case.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    query = GenomeModel.filter(created_at__lt=cutoff_date)

    if keep_active:
        query = query.filter(is_active=False)

    models = await query.all()
    pruned_ids = [m.id for m in models if m.id is not None]

    if not dry_run:
        for model in models:
            await model.delete()

    return len(pruned_ids), pruned_ids
