"""FastAPI routes for instrument registry.

API layer - NOT imported by the bot container.
"""

from fastapi import APIRouter, HTTPException, Path, status

from stonks_trading.domains.instruments import (
    disable_instrument,
    enable_instrument,
    get_instrument,
    get_instrument_status,
    list_instruments,
    register_instrument,
)
from stonks_trading.domains.instruments.dtos import (
    InstrumentListResponse,
    InstrumentRequest,
    InstrumentResponse,
    InstrumentStatusResponse,
    InstrumentUpdateRequest,
)

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=InstrumentListResponse)
async def list_instruments_endpoint() -> InstrumentListResponse:
    """List all registered instruments."""
    instruments = await list_instruments()
    return InstrumentListResponse(
        instruments=[
            InstrumentResponse(
                symbol=i.symbol,
                name=i.name,
                enabled=i.enabled,
                auto_backfill=i.auto_backfill,
                backfill_days=i.backfill_days,
                status=i.status,
                created_at=i.created_at,
                updated_at=i.updated_at,
                last_backfill_at=i.last_backfill_at,
                backfill_job_id=i.backfill_job_id,
            )
            for i in instruments
        ],
        total=len(instruments),
    )


@router.post("", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
async def register_instrument_endpoint(
    request: InstrumentRequest,
) -> InstrumentResponse:
    """Register a new trading instrument.

    Triggers auto-backfill of historical data if enabled.
    """
    instrument = await register_instrument(
        symbol=request.symbol,
        name=request.name,
        auto_backfill=request.auto_backfill,
        backfill_days=request.backfill_days,
    )

    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        enabled=instrument.enabled,
        auto_backfill=instrument.auto_backfill,
        backfill_days=instrument.backfill_days,
        status=instrument.status,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
        last_backfill_at=instrument.last_backfill_at,
        backfill_job_id=instrument.backfill_job_id,
    )


@router.get("/{symbol}", response_model=InstrumentResponse)
async def get_instrument_endpoint(
    symbol: str = Path(..., min_length=1, description="Instrument symbol"),
) -> InstrumentResponse:
    """Get instrument details by symbol."""
    instrument = await get_instrument(symbol.upper())
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        enabled=instrument.enabled,
        auto_backfill=instrument.auto_backfill,
        backfill_days=instrument.backfill_days,
        status=instrument.status,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
        last_backfill_at=instrument.last_backfill_at,
        backfill_job_id=instrument.backfill_job_id,
    )


@router.put("/{symbol}", response_model=InstrumentResponse)
async def update_instrument_endpoint(
    symbol: str = Path(..., min_length=1),
    request: InstrumentUpdateRequest = None,
) -> InstrumentResponse:
    """Update instrument metadata."""

    instrument = await get_instrument(symbol.upper())
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    # Update fields
    if request.name is not None:
        instrument.name = request.name
    if request.auto_backfill is not None:
        instrument.auto_backfill = request.auto_backfill
    if request.backfill_days is not None:
        instrument.backfill_days = request.backfill_days

    from stonks_trading.domains.instruments.repositories import save_instrument

    instrument = await save_instrument(instrument)

    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        enabled=instrument.enabled,
        auto_backfill=instrument.auto_backfill,
        backfill_days=instrument.backfill_days,
        status=instrument.status,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
        last_backfill_at=instrument.last_backfill_at,
        backfill_job_id=instrument.backfill_job_id,
    )


@router.post("/{symbol}/enable", response_model=InstrumentResponse)
async def enable_instrument_endpoint(
    symbol: str = Path(..., min_length=1),
) -> InstrumentResponse:
    """Enable instrument for trading."""
    instrument = await enable_instrument(symbol.upper())
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        enabled=instrument.enabled,
        auto_backfill=instrument.auto_backfill,
        backfill_days=instrument.backfill_days,
        status=instrument.status,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
        last_backfill_at=instrument.last_backfill_at,
        backfill_job_id=instrument.backfill_job_id,
    )


@router.post("/{symbol}/disable", response_model=InstrumentResponse)
async def disable_instrument_endpoint(
    symbol: str = Path(..., min_length=1),
) -> InstrumentResponse:
    """Disable instrument from trading."""
    instrument = await disable_instrument(symbol.upper())
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        enabled=instrument.enabled,
        auto_backfill=instrument.auto_backfill,
        backfill_days=instrument.backfill_days,
        status=instrument.status,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
        last_backfill_at=instrument.last_backfill_at,
        backfill_job_id=instrument.backfill_job_id,
    )


@router.get("/{symbol}/status", response_model=InstrumentStatusResponse)
async def get_instrument_status_endpoint(
    symbol: str = Path(..., min_length=1),
) -> InstrumentStatusResponse:
    """Get instrument status including backfill progress."""
    status = await get_instrument_status(symbol.upper())
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    return InstrumentStatusResponse(**status)


@router.post("/{symbol}/backfill")
async def trigger_backfill_endpoint(
    symbol: str = Path(..., min_length=1),
) -> dict:
    """Manually trigger backfill for an instrument."""
    from stonks_trading.domains.instruments.services import trigger_backfill

    instrument = await get_instrument(symbol.upper())
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {symbol} not found",
        )

    instrument = await trigger_backfill(instrument)

    return {
        "message": f"Backfill started for {symbol}",
        "job_id": instrument.backfill_job_id,
        "status": instrument.status,
    }


@router.post("/{symbol}/update")
async def update_instrument_data_endpoint(
    symbol: str = Path(..., min_length=1),
) -> dict:
    """Fetch latest data for an instrument (incremental update).

    Downloads only missing data from last known candle to now.
    If backfill was interrupted, this will resume from where it left off.
    """
    from stonks_trading.domains.instruments.services import update_instrument_data

    result = await update_instrument_data(symbol.upper())

    return {
        "message": f"Update complete for {symbol}",
        "job_id": result.get("job_id"),
        "status": result.get("status"),
        "candles_downloaded": result.get("candles_downloaded"),
        "start_date": result.get("start_date"),
        "end_date": result.get("end_date"),
    }
