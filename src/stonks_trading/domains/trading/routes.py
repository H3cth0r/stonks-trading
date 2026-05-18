"""FastAPI routes for trading domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to domain functionality.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

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
    # In production, would call ExecuteTradeUseCase
    # Stub for Phase 1
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Trade execution not yet implemented",
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
    # Stub for Phase 1
    return TradeListResponse(trades=[], total=0)


@trades_router.get(
    "/{trade_id}",
    response_model=TradeResponse,
)
async def get_trade(trade_id: int) -> TradeResponse:
    """Get trade by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Trade {trade_id} not found",
    )


# =============================================================================
# Position Routes
# =============================================================================


@positions_router.get(
    "",
    response_model=PositionListResponse,
)
async def list_positions() -> PositionListResponse:
    """List all open positions."""
    # Stub for Phase 1
    return PositionListResponse(positions=[])


@positions_router.get(
    "/{symbol}",
    response_model=PositionResponse,
)
async def get_position(symbol: str) -> PositionResponse:
    """Get position for specific symbol."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Position for {symbol} not found",
    )


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
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Genome creation not yet implemented",
    )


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
    return GenomeListResponse(genomes=[], total=0)


@genomes_router.get(
    "/active",
    response_model=GenomeResponse,
)
async def get_active_genome() -> GenomeResponse:
    """Get currently active genome for trading."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No active genome found",
    )


@genomes_router.post(
    "/activate",
    response_model=GenomeResponse,
)
async def activate_genome(request: GenomeActivateRequest) -> GenomeResponse:
    """Activate a genome for live trading."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Genome activation not yet implemented",
    )


@genomes_router.get(
    "/{genome_id}",
    response_model=GenomeResponse,
)
async def get_genome(genome_id: int) -> GenomeResponse:
    """Get genome by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Genome {genome_id} not found",
    )


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
    return RiskEventListResponse(events=[], total=0)


@risk_router.post(
    "/events/{event_id}/acknowledge",
    response_model=RiskEventResponse,
)
async def acknowledge_risk_event(
    event_id: int,
    request: RiskEventAcknowledgeRequest,
) -> RiskEventResponse:
    """Acknowledge a risk event."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Risk event acknowledgment not yet implemented",
    )


@risk_router.get(
    "/status",
    response_model=dict[str, Any],
)
async def get_risk_status() -> dict[str, Any]:
    """Get current risk status summary."""
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
    # Stub for Phase 1
    return PriceResponse(
        symbol=symbol.upper(),
        price=50000.0,
        timestamp=datetime.utcnow(),
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
    return BalanceResponse(
        balances=[
            {"asset": "USDT", "free": 10000.0, "locked": 0.0, "total": 10000.0},
        ]
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
    router = APIRouter(prefix="/api/v1", tags=["trading"])

    router.include_router(trades_router)
    router.include_router(positions_router)
    router.include_router(genomes_router)
    router.include_router(risk_router)
    router.include_router(market_router)
    router.include_router(portfolio_router)
    router.include_router(signal_router)

    return router
