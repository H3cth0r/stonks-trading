"""Repository functions for instrument domain.

Combines instrument registry + market data repositories.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from stonks_trading.domains.instruments.entities import Candle, Instrument, OrderBook
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.logger import logger

# =============================================================================
# Instrument Registry Repositories
# =============================================================================

_INSTRUMENTS: dict[str, Instrument] = {}


async def save_instrument(instrument: Instrument) -> Instrument:
    """Save instrument to registry."""
    _INSTRUMENTS[instrument.symbol] = instrument
    logger.info(f"Instrument saved: {instrument.symbol}")
    return instrument


async def get_instrument(symbol: str) -> Instrument | None:
    """Get instrument by symbol."""
    return _INSTRUMENTS.get(symbol.upper())


async def list_instruments(enabled: bool | None = None) -> list[Instrument]:
    """List all registered instruments."""
    instruments = list(_INSTRUMENTS.values())
    if enabled is not None:
        instruments = [i for i in instruments if i.enabled == enabled]
    return sorted(instruments, key=lambda i: i.symbol)


async def delete_instrument(symbol: str) -> bool:
    """Delete instrument from registry."""
    if symbol.upper() in _INSTRUMENTS:
        del _INSTRUMENTS[symbol.upper()]
        return True
    return False


async def update_instrument_status(symbol: str, status: str, **kwargs: Any) -> Instrument | None:
    """Update instrument status and metadata."""
    instrument = _INSTRUMENTS.get(symbol.upper())
    if not instrument:
        return None

    instrument.status = status
    instrument.updated_at = datetime.utcnow()

    for key, value in kwargs.items():
        if hasattr(instrument, key):
            setattr(instrument, key, value)

    _INSTRUMENTS[symbol.upper()] = instrument
    return instrument


# =============================================================================
# Market Data Repositories
# =============================================================================


async def fetch_candles(
    symbol: Symbol,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[Candle]:
    """Fetch candles for symbol and time range."""
    from stonks_trading.domains.trading.adapters import ExchangeAdapterFactory

    adapter = ExchangeAdapterFactory.create_adapter()
    candles_raw = await adapter.get_klines(
        symbol=symbol,
        interval=timeframe,
        limit=1000,
        start_time=int(start.timestamp() * 1000),
        end_time=int(end.timestamp() * 1000),
    )

    candles = []
    for c in candles_raw:
        candles.append(
            Candle(
                timestamp=datetime.utcfromtimestamp(c["timestamp"] / 1000),
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c["volume"],
                symbol=symbol.value,
            )
        )
    return candles


async def fetch_latest_candle(
    symbol: Symbol,
    timeframe: str = "1m",
) -> Candle | None:
    """Fetch the most recent candle."""
    from stonks_trading.domains.trading.adapters import ExchangeAdapterFactory

    adapter = ExchangeAdapterFactory.create_adapter()
    candles_raw = await adapter.get_klines(
        symbol=symbol,
        interval=timeframe,
        limit=1,
    )

    if not candles_raw:
        return None

    c = candles_raw[-1]
    return Candle(
        timestamp=datetime.utcfromtimestamp(c["timestamp"] / 1000),
        open=c["open"],
        high=c["high"],
        low=c["low"],
        close=c["close"],
        volume=c["volume"],
        symbol=symbol.value,
    )


async def fetch_orderbook(
    symbol: Symbol,
    limit: int = 20,
) -> OrderBook:
    """Fetch order book for symbol."""
    return OrderBook(
        symbol=symbol.value,
        bids=[],
        asks=[],
        timestamp=datetime.utcnow(),
    )
