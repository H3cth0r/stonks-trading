"""FastAPI routes for trading domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to domain functionality.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from stonks_trading.bots.base.context import BotContext
from stonks_trading.domains.instruments.services import (
    backfill_from_massive,
    get_job_status,
    set_job_status,
)
from stonks_trading.domains.trading import repositories as repo
from stonks_trading.domains.trading.adapters import ExchangeAdapterFactory
from stonks_trading.domains.trading.dtos import (
    ActivityListResponse,
    BackfillMassiveRequest,
    BackfillMassiveResponse,
    BalanceResponse,
    BotInstanceResponse,
    BotListResponse,
    BotRegisterRequest,
    BotStateResponse,
    GenomeActivateRequest,
    GenomeCreateRequest,
    GenomeListResponse,
    GenomeResponse,
    JobStatusResponse,
    MarketDataListResponse,
    MarketDataResponse,
    MarketPriceListResponse,
    MarketPriceResponse,
    NeatSignalRequest,
    NeatSignalResponse,
    OrderListResponse,
    PortfolioResponse,
    PositionListResponse,
    PositionResponse,
    PriceResponse,
    RiskEventAcknowledgeRequest,
    RiskEventListResponse,
    RiskEventResponse,
    TradeCreateRequest,
    TradeListResponse,
    TradeResponse,
    TrainingRunListResponse,
    TrainingRunResponse,
    VenueBalanceItemResponse,
    VenueBalanceListResponse,
    VenueBalanceResponse,
)
from stonks_trading.domains.trading.entities import Genome, Position
from stonks_trading.domains.trading.mappers import (
    ActivityMapper,
    BalanceMapper,
    BotInstanceMapper,
    BotStateMapper,
    GenomeMapper,
    OrderMapper,
    PositionMapper,
    RiskEventMapper,
    TradeMapper,
    TrainingRunMapper,
)
from stonks_trading.domains.trading.services import FeeCalculator, RiskChecker
from stonks_trading.domains.trading.use_cases import (
    EvaluateSignalUseCase,
    FetchBalancesUseCase,
    GetCandlesUseCase,
    GetMarketDataUseCase,
    GetMarketPricesUseCase,
    GetVenueBalancesUseCase,
    ListActivityUseCase,
    ListOrdersUseCase,
    ListTrainingRunsUseCase,
    PlaceOrderUseCase,
)
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.storage.duckdb_client import DuckDBClient

# Phase 10B - Backfill router
backfill_router = APIRouter(prefix="/backfill", tags=["backfill"])

# Create router
trades_router = APIRouter(prefix="/trades", tags=["trades"])
positions_router = APIRouter(prefix="/positions", tags=["positions"])
genomes_router = APIRouter(prefix="/genomes", tags=["genomes"])
risk_router = APIRouter(prefix="/risk", tags=["risk"])
market_router = APIRouter(prefix="/market", tags=["market"])
portfolio_router = APIRouter(prefix="/portfolio", tags=["portfolio"])
balances_router = APIRouter(prefix="/balances", tags=["balances"])
signal_router = APIRouter(prefix="/signals", tags=["signals"])

# Bot routers (Phase 5C)
bot_registry_router = APIRouter(prefix="/bots", tags=["bot-registry"])
bot_scoped_router = APIRouter(prefix="/bots/{bot_type}/{instance_id}", tags=["bot-scoped"])

# Phase 6 routers
activity_router = APIRouter(prefix="/activity", tags=["activity"])
orders_router = APIRouter(prefix="/orders", tags=["orders"])
training_router = APIRouter(prefix="/training", tags=["training"])


# =============================================================================
# Bot Context Dependency
# =============================================================================


async def get_bot_context(
    bot_type: str = Path(..., min_length=1, max_length=50),
    instance_id: str = Path(..., min_length=1, max_length=100),
) -> BotContext:
    """FastAPI dependency to validate and extract bot context.

    Validates that the bot instance exists in the registry.
    Raises 404 if not found.
    """
    instance = await repo.get_bot_instance(bot_type, instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot {bot_type}/{instance_id} not found",
        )
    return BotContext(bot_type=bot_type, instance_id=instance_id)


# =============================================================================
# Trade Routes
# =============================================================================


@trades_router.post(
    "",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trade(request: TradeCreateRequest) -> TradeResponse:
    """Execute a new trade via exchange adapter.

    Uses configured adapter (dry_run or live) to place order.
    Orchestrates through PlaceOrderUseCase per CLEAN architecture.
    """
    adapter = ExchangeAdapterFactory.create_adapter()

    try:
        # Create use case with injected adapter and services
        use_case = PlaceOrderUseCase(
            adapter=adapter,
            risk_checker=RiskChecker(),
            fee_calculator=FeeCalculator(),
        )

        # Get current position and daily trades
        current_position = await repo.get_position_by_symbol(Symbol(value=request.symbol.upper()))
        daily_trades = await repo.count_trades_today()

        # Execute through use case (all business logic)
        price = Money(amount=request.price, currency="USDT") if request.price else None
        result = await use_case.execute(
            symbol=Symbol(value=request.symbol.upper()),
            side=request.side,
            quantity=request.quantity,
            price=price,
            current_position=current_position,
            daily_trade_count=daily_trades,
            minutes_since_last_trade=999,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Trade execution failed",
            )

        if result.trade:
            return TradeMapper.to_response(result.trade)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trade executed but no trade returned",
        )
    finally:
        await adapter.close()


@trades_router.get(
    "",
    response_model=TradeListResponse,
)
async def list_trades(
    symbol: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TradeListResponse:
    """List trades with optional filtering."""
    if symbol:
        trades = await repo.list_trades_by_symbol(Symbol(value=symbol), limit=limit)
    else:
        trades = await repo.list_trades(limit=limit, offset=offset)
    trade_responses = TradeMapper.to_response_list(trades)
    return TradeListResponse(trades=trade_responses, total=len(trade_responses))


@trades_router.get(
    "/{trade_id}",
    response_model=TradeResponse,
)
async def get_trade(trade_id: int) -> TradeResponse:
    """Get trade by ID."""
    trade = await repo.get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade {trade_id} not found",
        )
    return TradeMapper.to_response(trade)


# =============================================================================
# Position Routes
# =============================================================================


@positions_router.get(
    "",
    response_model=PositionListResponse,
)
async def list_positions() -> PositionListResponse:
    """List all open positions."""
    positions = await list_all_positions()
    position_responses = PositionMapper.to_response_list(positions)
    return PositionListResponse(positions=position_responses)


@positions_router.get(
    "/{symbol}",
    response_model=PositionResponse,
)
async def get_position(symbol: str) -> PositionResponse:
    """Get position for specific symbol."""
    position = await repo.get_position_by_symbol(Symbol(value=symbol.upper()))
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position for {symbol} not found",
        )
    return PositionMapper.to_response(position)


# Position list helper - delegates to repository
async def list_all_positions() -> list[Position]:
    """List all positions - delegates to repository."""
    return await repo.list_positions()


# =============================================================================
# Genome Routes
# =============================================================================

# Note: These endpoints are kept for backward compatibility.
# New code should use /api/v1/models instead (Phase 10H).


@genomes_router.post(
    "",
    response_model=GenomeResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_genome(request: GenomeCreateRequest) -> GenomeResponse:
    """Save a trained genome.

    DEPRECATED: Use POST /api/v1/models instead.
    """
    genome = Genome(
        genome_data=b"",  # Will be filled from request in Phase 4
        fitness=request.fitness,
        generation=request.generation,
        symbol=Symbol(value=request.symbol) if request.symbol else None,
        fee_rate=request.fee_rate,
        slippage_bps=request.slippage_bps,
        mode=request.mode,
    )
    saved_genome = await repo.save_genome(genome)
    return GenomeMapper.to_response(saved_genome)


@genomes_router.get(
    "",
    response_model=GenomeListResponse,
    deprecated=True,
)
async def list_genomes(
    symbol: str | None = None,
    active_only: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
) -> GenomeListResponse:
    """List genomes with optional filtering."""
    if active_only:
        genome = await repo.get_active_genome(Symbol(value=symbol) if symbol else None)
        genomes = [genome] if genome else []
    else:
        genome_symbol = Symbol(value=symbol) if symbol else None
        genomes = await repo.list_genomes(symbol=genome_symbol, limit=limit)
    genome_responses = GenomeMapper.to_response_list(genomes)
    return GenomeListResponse(genomes=genome_responses, total=len(genome_responses))


@genomes_router.get(
    "/active",
    response_model=GenomeResponse,
    deprecated=True,
)
async def get_active_genome() -> GenomeResponse:
    """Get currently active genome for trading.

    DEPRECATED: Use GET /api/v1/models?is_active=true instead.
    """
    genome = await repo.get_active_genome()
    if not genome:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active genome found",
        )
    return GenomeMapper.to_response(genome)


@genomes_router.post(
    "/activate",
    response_model=GenomeResponse,
    deprecated=True,
)
async def activate_genome(request: GenomeActivateRequest) -> GenomeResponse:
    """Activate a genome for live trading.

    DEPRECATED: Use POST /api/v1/models/{id}/activate instead.
    """
    success = await repo.activate_genome(request.genome_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome {request.genome_id} not found",
        )
    genome = await repo.get_genome_by_id(request.genome_id)
    if not genome:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome {request.genome_id} not found after activation",
        )
    return GenomeMapper.to_response(genome)


@genomes_router.get(
    "/{genome_id}",
    response_model=GenomeResponse,
    deprecated=True,
)
async def get_genome(genome_id: int) -> GenomeResponse:
    """Get genome by ID.

    DEPRECATED: Use GET /api/v1/models/{model_id} instead.
    """
    genome = await repo.get_genome_by_id(genome_id)
    if not genome:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome {genome_id} not found",
        )
    return GenomeMapper.to_response(genome)


# =============================================================================
# Risk Routes
# =============================================================================


@risk_router.get(
    "/events",
    response_model=RiskEventListResponse,
)
async def list_risk_events(
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> RiskEventListResponse:
    """List risk events with filtering."""
    events = await repo.list_risk_events(severity=severity, acknowledged=acknowledged, limit=limit)
    event_responses = RiskEventMapper.to_response_list(events)
    return RiskEventListResponse(events=event_responses, total=len(event_responses))


@risk_router.post(
    "/events/{event_id}/acknowledge",
    response_model=RiskEventResponse,
)
async def acknowledge_risk_event(
    event_id: int,
    request: RiskEventAcknowledgeRequest,
) -> RiskEventResponse:
    """Acknowledge a risk event."""
    event = await repo.acknowledge_risk_event(event_id, request.user, request.action)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk event {event_id} not found",
        )
    return RiskEventMapper.to_response(event)


@risk_router.get(
    "/status",
    response_model=dict[str, Any],
)
async def get_risk_status() -> dict[str, Any]:
    """Get current risk status summary."""
    # Placeholder - full implementation in Phase 4 with exchange adapters
    return {
        "status": "ok",
        "drawdown": 0.0,
        "daily_trades": 0,
        "max_drawdown": 0.0,
    }


# =============================================================================
# Market Data Routes
# =============================================================================


@market_router.get(
    "/price/{symbol}",
    response_model=PriceResponse,
)
async def get_price(symbol: str) -> PriceResponse:
    """Get current price for symbol from exchange."""
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        use_case = GetMarketDataUseCase(adapter)
        price = await use_case.execute(Symbol(value=symbol))
        return PriceResponse(
            symbol=symbol.upper(),
            price=price.amount,
            timestamp=datetime.utcnow(),
        )
    finally:
        await adapter.close()


@market_router.get(
    "/candles/{symbol}",
    response_model=MarketDataListResponse,
)
async def get_candles(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=50000),
) -> MarketDataListResponse:
    """Get OHLCV candles for symbol from DuckDB (historical data).

    First checks DuckDB for historical data, falls back to exchange
    adapter for recent/live data if DuckDB is empty.
    """
    symbol_obj = Symbol(value=symbol.upper())
    candles: list[MarketDataResponse] = []

    # Strategy: Query DuckDB for historical + Binance for recent data
    candles: list[MarketDataResponse] = []
    now = datetime.utcnow()

    # Determine what we need from each source
    # DuckDB: Historical data up to last hour
    # Binance: Recent data (last hour to now) for live trading
    duckdb_end = end if end and end < now - timedelta(hours=1) else now - timedelta(hours=1)
    effective_start = start or datetime(1970, 1, 1)
    needs_binance = not end or end > now - timedelta(hours=1)
    binance_start = max(effective_start, now - timedelta(hours=2)) if needs_binance else None

    # Query DuckDB for historical data
    if not end or effective_start < now - timedelta(hours=1):
        duckdb = DuckDBClient()
        duckdb.connect()
        try:
            duckdb_data = duckdb.get_data_range(
                symbol_obj,
                effective_start,
                duckdb_end,
            )
            if duckdb_data:
                # For large datasets, sample evenly to get representative data across time range
                if len(duckdb_data) > limit:
                    # Sample evenly across the time range
                    step = len(duckdb_data) // limit
                    sampled_data = duckdb_data[::step][:limit]
                else:
                    sampled_data = duckdb_data

                candles = [
                    MarketDataResponse(
                        symbol=symbol.upper(),
                        timestamp=row["timestamp"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                    )
                    for row in sampled_data
                ]
        finally:
            duckdb.close()

    # Query Binance for recent/live data if needed
    if binance_start and len(candles) < limit:
        remaining = limit - len(candles)
        adapter = ExchangeAdapterFactory.create_adapter()
        try:
            use_case = GetCandlesUseCase(adapter)
            exchange_candles = await use_case.execute(
                symbol=symbol_obj,
                start=binance_start,
                end=end or now,
                limit=remaining,
            )
            if exchange_candles:
                # Append Binance candles
                binance_candle_list = [
                    MarketDataResponse(
                        symbol=symbol.upper(),
                        timestamp=datetime.fromtimestamp(c["timestamp"] / 1000),
                        open=c["open"],
                        high=c["high"],
                        low=c["low"],
                        close=c["close"],
                        volume=c["volume"],
                    )
                    for c in exchange_candles
                ]
                # Merge and deduplicate by timestamp
                candles_by_ts = {c.timestamp: c for c in candles}
                for c in binance_candle_list:
                    candles_by_ts[c.timestamp] = c
                candles = sorted(candles_by_ts.values(), key=lambda x: x.timestamp)[-limit:]
        finally:
            await adapter.close()

    # If no data from either source, return empty
    if not candles:
        # Try Binance as fallback for entire range
        adapter = ExchangeAdapterFactory.create_adapter()
        try:
            use_case = GetCandlesUseCase(adapter)
            exchange_candles = await use_case.execute(
                symbol=symbol_obj,
                start=start,
                end=end,
                limit=limit,
            )
            candles = [
                MarketDataResponse(
                    symbol=symbol.upper(),
                    timestamp=datetime.fromtimestamp(c["timestamp"] / 1000),
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                    volume=c["volume"],
                )
                for c in exchange_candles
            ]
        finally:
            await adapter.close()

    return MarketDataListResponse(
        symbol=symbol.upper(),
        candles=candles,
    )


@market_router.get(
    "/prices",
    response_model=MarketPriceListResponse,
)
async def get_market_prices_endpoint(
    symbols: str | None = Query(default=None),
) -> MarketPriceListResponse:
    """Get current prices for multiple symbols.

    Thin route - delegates to GetMarketPricesUseCase for business logic.
    """
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        # Parse symbols or use defaults
        symbol_list = []
        if symbols:
            symbol_list = [Symbol(value=s.strip().upper()) for s in symbols.split(",")]
        else:
            symbol_list = [Symbol(value="BTC_USDT")]

        # Delegate to use case (business logic)
        use_case = GetMarketPricesUseCase(adapter)
        price_dicts = await use_case.execute(symbol_list)

        # Map to response DTOs
        prices = [MarketPriceResponse(**p) for p in price_dicts]
        return MarketPriceListResponse(prices=prices)
    finally:
        await adapter.close()


# =============================================================================
# Portfolio Routes
# =============================================================================


@portfolio_router.get(
    "",
    response_model=PortfolioResponse,
)
async def get_portfolio() -> PortfolioResponse:
    """Get complete portfolio summary with real balances."""
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        use_case = FetchBalancesUseCase(adapter)
        balances = await use_case.execute()

        total_value = sum(b.total for b in balances)
        cash_value = next((b.total for b in balances if b.asset == "USDT"), 0.0)
        positions_value = total_value - cash_value

        # Get positions from database
        positions = await list_all_positions()
        position_responses = PositionMapper.to_response_list(positions)

        return PortfolioResponse(
            total_value=total_value,
            cash_value=cash_value,
            positions_value=positions_value,
            positions=position_responses,
        )
    finally:
        await adapter.close()


@portfolio_router.get(
    "/balance",
    response_model=BalanceResponse,
)
async def get_balance() -> BalanceResponse:
    """Get account balances from exchange."""
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        use_case = FetchBalancesUseCase(adapter)
        balances = await use_case.execute()
        return BalanceMapper.to_response(balances)
    finally:
        await adapter.close()


@balances_router.get(
    "",
    response_model=VenueBalanceListResponse,
)
async def get_balances_endpoint() -> VenueBalanceListResponse:
    """Get all venue balances.

    Thin route - delegates to GetVenueBalancesUseCase for business logic.
    """
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        # Delegate to use case (business logic)
        use_case = GetVenueBalancesUseCase(adapter)
        venue_dicts = await use_case.execute()

        # Map to response DTOs
        venues = []
        for v in venue_dicts:
            items = [VenueBalanceItemResponse(**item) for item in v["balances"]]
            venues.append(
                VenueBalanceResponse(
                    venue=v["venue"],
                    balances=items,
                    synced_at=v["synced_at"],
                )
            )

        return VenueBalanceListResponse(venues=venues)
    finally:
        await adapter.close()


@balances_router.get(
    "/usdt",
    response_model=dict[str, float],
)
async def get_usdt_balance() -> dict[str, float]:
    """Get USDT balance for deployment validation.

    Returns simple {balance: X.XX} format for easy checking.
    """
    adapter = ExchangeAdapterFactory.create_adapter()
    try:
        use_case = FetchBalancesUseCase(adapter)
        balances = await use_case.execute()

        usdt_balance = next((b.total for b in balances if b.asset == "USDT"), 0.0)

        return {"balance": usdt_balance}
    finally:
        await adapter.close()


# =============================================================================
# Signal Routes
# =============================================================================


@signal_router.post(
    "/evaluate",
    response_model=NeatSignalResponse,
)
async def evaluate_signal(request: NeatSignalRequest) -> NeatSignalResponse:
    """Evaluate NEAT signal and return trading decision.

    This endpoint allows testing NEAT signal evaluation without
    executing actual trades.
    """
    # Delegate to use case for business logic
    use_case = EvaluateSignalUseCase(
        risk_checker=RiskChecker(),
        decision_threshold=0.6,
    )

    result = use_case.evaluate(
        buy_prob=request.buy_prob,
        sell_prob=request.sell_prob,
        current_position=None,  # Signal evaluation is position-agnostic
        portfolio_value=Money(amount=request.portfolio_value or 10000.0, currency="USDT"),
        daily_trade_count=0,
        minutes_since_last_trade=999,
    )

    return NeatSignalResponse(
        action=result.action.value if result.action else None,
        confidence=result.confidence,
        should_trade=result.should_trade,
        reason=result.reason,
    )


# =============================================================================
# Bot Registry Routes
# =============================================================================


@bot_registry_router.get(
    "",
    response_model=BotListResponse,
)
async def list_bots() -> BotListResponse:
    """List all registered bot instances."""
    bots = await repo.list_all_bot_instances()
    bot_responses = BotInstanceMapper.to_response_list(bots)
    return BotListResponse(bots=bot_responses, total=len(bot_responses))


@bot_registry_router.get(
    "/{bot_type}",
    response_model=BotListResponse,
)
async def list_bot_instances(bot_type: str) -> BotListResponse:
    """List all instances of a specific bot type."""
    instances = await repo.list_bot_instances_by_type(bot_type)
    instance_responses = BotInstanceMapper.to_response_list(instances)
    return BotListResponse(bots=instance_responses, total=len(instance_responses))


@bot_registry_router.post(
    "",
    response_model=BotInstanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_bot(request: BotRegisterRequest) -> BotInstanceResponse:
    """Register a new bot instance."""
    instance = await repo.register_bot_instance(
        bot_type=request.bot_type,
        instance_id=request.instance_id,
        symbols=request.symbols,
        mode=request.mode,
        config=request.config,
    )
    return BotInstanceMapper.to_response(instance)


# =============================================================================
# Bot-Scoped Routes
# =============================================================================


@bot_scoped_router.get(
    "/state",
    response_model=BotStateResponse,
)
async def get_bot_state(
    context: BotContext = Depends(get_bot_context),  # noqa: B008
) -> BotStateResponse:
    """Get current state for a bot instance."""
    state = await repo.load_bot_state(context)
    # Get bot status from registry
    instance = await repo.get_bot_instance(context.bot_type, context.instance_id)
    status = instance.status if instance else "unknown"
    return BotStateMapper.to_response(
        bot_type=context.bot_type,
        instance_id=context.instance_id,
        state=state,
        status=status,
    )


@bot_scoped_router.get(
    "/trades",
    response_model=TradeListResponse,
)
async def list_bot_trades(
    context: BotContext = Depends(get_bot_context),  # noqa: B008
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
) -> TradeListResponse:
    """List trades for a specific bot."""
    symbol_obj = Symbol(value=symbol.upper()) if symbol else None
    trades = await repo.list_trades_by_bot(context, symbol=symbol_obj, limit=limit)
    trade_responses = TradeMapper.to_response_list(trades)
    return TradeListResponse(trades=trade_responses, total=len(trade_responses))


@bot_scoped_router.get(
    "/positions",
    response_model=PositionListResponse,
)
async def list_bot_positions(
    context: BotContext = Depends(get_bot_context),  # noqa: B008
) -> PositionListResponse:
    """List all positions for a specific bot."""
    positions = await repo.list_positions_by_bot(context)
    position_responses = PositionMapper.to_response_list(positions)
    return PositionListResponse(positions=position_responses)


# =============================================================================
# Phase 6 Routes - Activity, Orders, Training
# =============================================================================


@activity_router.get(
    "",
    response_model=ActivityListResponse,
)
async def list_activity_endpoint(
    bot_type: str | None = Query(default=None),
    instance_id: str | None = Query(default=None),
    types: list[str] | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> ActivityListResponse:
    """List unified activity timeline (trades, orders, risk events)."""
    bot_context = None
    if bot_type and instance_id:
        bot_context = BotContext(bot_type=bot_type, instance_id=instance_id)

    use_case = ListActivityUseCase()
    activities, next_cursor = await use_case.execute(
        bot_context=bot_context,
        types=types,
        cursor=cursor,
        limit=limit,
    )

    activity_responses = ActivityMapper.to_response_list(activities)
    return ActivityListResponse(
        activities=activity_responses,
        cursor=next_cursor,
        total=len(activity_responses),
    )


@orders_router.get(
    "",
    response_model=OrderListResponse,
)
async def list_orders_endpoint(
    bot_type: str | None = Query(default=None),
    instance_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> OrderListResponse:
    """List orders with optional filtering."""
    bot_context = None
    if bot_type and instance_id:
        bot_context = BotContext(bot_type=bot_type, instance_id=instance_id)

    symbol_obj = Symbol(value=symbol.upper()) if symbol else None

    use_case = ListOrdersUseCase()
    orders = await use_case.execute(
        bot_context=bot_context,
        status=status,
        symbol=symbol_obj,
        limit=limit,
        offset=offset,
    )

    order_responses = OrderMapper.to_response_list(orders)
    return OrderListResponse(orders=order_responses, total=len(order_responses))


@training_router.get(
    "",
    response_model=TrainingRunListResponse,
)
async def list_training_runs_endpoint(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TrainingRunListResponse:
    """List training runs with optional filtering."""
    symbol_obj = Symbol(value=symbol.upper()) if symbol else None

    use_case = ListTrainingRunsUseCase()
    runs = await use_case.execute(
        status=status,
        symbol=symbol_obj,
        limit=limit,
        offset=offset,
    )

    run_responses = TrainingRunMapper.to_response_list(runs)
    return TrainingRunListResponse(runs=run_responses, total=len(run_responses))


@training_router.get(
    "/{run_id}",
    response_model=TrainingRunResponse,
)
async def get_training_run_endpoint(
    run_id: int = Path(..., ge=1),
) -> TrainingRunResponse:
    """Get a specific training run by ID."""
    run = await repo.get_training_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training run {run_id} not found",
        )
    return TrainingRunMapper.to_response(run)


# =============================================================================
# Backfill Routes (Phase 10B)
# =============================================================================


@backfill_router.post(
    "/massive",
    response_model=BackfillMassiveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def backfill_massive(request: BackfillMassiveRequest) -> BackfillMassiveResponse:
    """Start a Massive backfill job.

    Returns job_id for status polling.
    """
    import asyncio

    estimated_chunks = (request.days // 30) + 1
    estimated_minutes = (estimated_chunks * 65) // 60

    # Generate job ID upfront for response
    job_id = str(uuid.uuid4()) if hasattr(uuid, "uuid4") else f"job-{id(request)}"

    # Initialize job status as running
    await set_job_status(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "progress": 0.0,
            "symbol": request.symbol,
            "total_chunks": estimated_chunks,
            "candles_downloaded": 0,
            "error": None,
        },
    )

    # Start backfill in background with same job_id
    asyncio.create_task(backfill_from_massive(request.symbol, request.days, job_id=job_id))

    return BackfillMassiveResponse(
        job_id=job_id,
        symbol=request.symbol,
        days=request.days,
        estimated_chunks=estimated_chunks,
        estimated_duration_minutes=estimated_minutes,
    )


@backfill_router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
)
async def get_backfill_job(job_id: str) -> JobStatusResponse:
    """Get status of a backfill job."""
    job_status = await get_job_status(job_id)
    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    # Add BaseResponse required fields
    job_status["success"] = True
    job_status["timestamp"] = datetime.utcnow()
    job_status["message"] = None
    return JobStatusResponse(**job_status)


# =============================================================================
# Main Router Assembly
# =============================================================================


def get_trading_router() -> APIRouter:
    """Assemble all trading routes into main router."""
    router = APIRouter(tags=["trading"])

    router.include_router(trades_router)
    router.include_router(positions_router)
    router.include_router(genomes_router)
    router.include_router(risk_router)
    router.include_router(market_router)
    router.include_router(portfolio_router)
    router.include_router(balances_router)
    router.include_router(signal_router)
    router.include_router(bot_registry_router)
    router.include_router(bot_scoped_router)
    # Phase 6 routes
    router.include_router(activity_router)
    router.include_router(orders_router)
    router.include_router(training_router)
    # Phase 10B - Backfill routes
    router.include_router(backfill_router)

    return router
