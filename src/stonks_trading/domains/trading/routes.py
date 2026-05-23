"""FastAPI routes for trading domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to domain functionality.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from stonks_trading.domains.trading import repositories as repo
from stonks_trading.domains.trading.adapters import ExchangeAdapterFactory
from stonks_trading.domains.trading.dtos import (
    BalanceResponse,
    GenomeActivateRequest,
    GenomeCreateRequest,
    GenomeListResponse,
    GenomeResponse,
    MarketDataListResponse,
    MarketDataResponse,
    NeatSignalRequest,
    NeatSignalResponse,
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
)
from stonks_trading.domains.trading.entities import Genome, Position
from stonks_trading.domains.trading.mappers import (
    BalanceMapper,
    GenomeMapper,
    PositionMapper,
    RiskEventMapper,
    TradeMapper,
)
from stonks_trading.domains.trading.services import FeeCalculator, RiskChecker
from stonks_trading.domains.trading.use_cases import (
    EvaluateSignalUseCase,
    FetchBalancesUseCase,
    GetCandlesUseCase,
    GetMarketDataUseCase,
    PlaceOrderUseCase,
)
from stonks_trading.domains.trading.value_objects import Money, Symbol

# Create router
trades_router = APIRouter(prefix="/trades", tags=["trades"])
positions_router = APIRouter(prefix="/positions", tags=["positions"])
genomes_router = APIRouter(prefix="/genomes", tags=["genomes"])
risk_router = APIRouter(prefix="/risk", tags=["risk"])
market_router = APIRouter(prefix="/market", tags=["market"])
portfolio_router = APIRouter(prefix="/portfolio", tags=["portfolio"])
signal_router = APIRouter(prefix="/signals", tags=["signals"])


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


@genomes_router.post(
    "",
    response_model=GenomeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_genome(request: GenomeCreateRequest) -> GenomeResponse:
    """Save a trained genome."""
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
)
async def get_active_genome() -> GenomeResponse:
    """Get currently active genome for trading."""
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
)
async def activate_genome(request: GenomeActivateRequest) -> GenomeResponse:
    """Activate a genome for live trading."""
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
)
async def get_genome(genome_id: int) -> GenomeResponse:
    """Get genome by ID."""
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
) -> MarketDataListResponse:
    """Get OHLCV candles for symbol from exchange."""
    adapter = ExchangeAdapterFactory.create_adapter()

    try:
        use_case = GetCandlesUseCase(adapter)
        candles = await use_case.execute(
            symbol=Symbol(value=symbol.upper()),
            start=start,
            end=end,
            limit=100,
        )

        # Convert to response format
        candle_responses = [
            MarketDataResponse(
                symbol=symbol.upper(),
                timestamp=datetime.fromtimestamp(c["timestamp"] / 1000),
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c["volume"],
            )
            for c in candles
        ]

        return MarketDataListResponse(
            symbol=symbol.upper(),
            candles=candle_responses,
        )
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
    router.include_router(signal_router)

    return router
