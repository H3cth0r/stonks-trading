"""Repository functions for market data domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime

from stonks_trading.domains.market_data.entities import Candle, OrderBook
from stonks_trading.domains.trading.value_objects import Symbol


async def fetch_candles(
    symbol: Symbol,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[Candle]:
    """Fetch candles for symbol and time range.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe (1m, 5m, 1h, 1d)
        start: Start time
        end: End time

    Returns:
        List of Candle entities
    """
    # Implementation uses exchange adapter
    # This is a placeholder - actual implementation in Phase 10B
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
    """Fetch the most recent candle.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe

    Returns:
        Latest Candle or None
    """
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
    """Fetch order book for symbol.

    Args:
        symbol: Trading symbol
        limit: Number of levels

    Returns:
        OrderBook entity
    """
    # Placeholder - actual implementation in Phase 10B
    # This requires adapter.get_orderbook() which doesn't exist yet
    return OrderBook(
        symbol=symbol.value,
        bids=[],
        asks=[],
        timestamp=datetime.utcnow(),
    )
