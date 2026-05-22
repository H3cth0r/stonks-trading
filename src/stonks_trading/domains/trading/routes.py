"""FastAPI routes for trading domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to domain functionality.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from stonks_trading.domains.trading import repositories as repo
from stonks_trading.domains.trading.dtos import (
    BalanceResponse,
    GenomeActivateRequest,
    GenomeCreateRequest,
    GenomeListResponse,
    GenomeResponse,
    MarketDataListResponse,
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
from stonks_trading.domains.trading.entities import Genome, Position, RiskEvent, Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.mappers import GenomeMapper, PositionMapper, RiskEventMapper, TradeMapper
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.postgres_models import PositionModel

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
    """Execute a new trade.

    Validates the trade request and executes through the trading use case.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Trade execution requires Phase 4 exchange adapters",
    )


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


# In-memory position list helper (until positions repo has list all)
async def list_all_positions() -> list[Position]:
    """List all positions - placeholder until DB query is available."""
    models = await PositionModel.all()
    return [
        Position(
            id=m.id,
            symbol=Symbol(value=m.symbol),
            quantity=m.quantity,
            entry_price=Money(amount=m.entry_price, currency="USD") if m.entry_price else None,
            current_price=Money(amount=m.current_price, currency="USD") if m.current_price else None,
            unrealized_pnl=m.unrealized_pnl,
            created_at=datetime.utcnow(),  # PositionModel tracks updated_at only
            updated_at=m.updated_at,
        )
        for m in models
    ]


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
    """Get current price for symbol."""
    # Placeholder - full implementation in Phase 4 with exchange adapters
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Market data requires Phase 4 exchange adapters",
    )


@market_router.get(
    "/candles/{symbol}",
    response_model=MarketDataListResponse,
)
async def get_candles(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> MarketDataListResponse:
    """Get OHLCV candles for symbol."""
    # Placeholder - full implementation in Phase 4 with data pipeline
    return MarketDataListResponse(
        symbol=symbol.upper(),
        candles=[],
    )


# =============================================================================
# Portfolio Routes
# =============================================================================


@portfolio_router.get(
    "",
    response_model=PortfolioResponse,
)
async def get_portfolio() -> PortfolioResponse:
    """Get complete portfolio summary."""
    # Placeholder - full implementation in Phase 4 with exchange adapters
    return PortfolioResponse(
        total_value=10000.0,
        cash_value=10000.0,
        positions_value=0.0,
        positions=[],
    )


@portfolio_router.get(
    "/balance",
    response_model=BalanceResponse,
)
async def get_balance() -> BalanceResponse:
    """Get account balances."""
    # Placeholder - full implementation in Phase 4 with exchange adapters
    return BalanceResponse(
        balances=[],
    )


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
    # Apply NEAT decision logic
    threshold = 0.6

    if request.buy_prob > threshold and request.buy_prob > request.sell_prob:
        return NeatSignalResponse(
            action="buy",
            confidence=request.buy_prob,
            should_trade=True,
        )
    elif request.sell_prob > threshold and request.sell_prob > request.buy_prob:
        return NeatSignalResponse(
            action="sell",
            confidence=request.sell_prob,
            should_trade=True,
        )
    else:
        return NeatSignalResponse(
            action=None,
            confidence=max(request.buy_prob, request.sell_prob),
            should_trade=False,
            reason="No signal exceeds threshold",
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