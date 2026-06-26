"""Massive data adapter for historical OHLCV data.

Fetches 1-minute aggregate data from Massive API.
Rate limited to 5 calls/minute with 65s wait between chunks.
"""

import time
from datetime import datetime, timedelta

import httpx

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.ingest.adapter import Candle, MarketDataAdapter
from stonks_trading.shared.logger import logger


class MassiveAdapter(MarketDataAdapter):
    """Massive market data adapter for historical backfill.

    Fetches 1-minute OHLCV data from Massive's v2 aggs API.
    Free tier provides up to 2 years of historical data.

    Rate Limits:
    - 5 API calls per minute
    - 30-day windows per call

    Example:
        adapter = MassiveAdapter(api_key="your-key")
        candles = await adapter.backfill(symbol, start, end)
    """

    BASE_URL = "https://api.massive.com"
    RATE_LIMIT_CALLS = 5
    RATE_LIMIT_WAIT = 65  # seconds

    def __init__(self, api_key: str) -> None:
        """Initialize Massive adapter.

        Args:
            api_key: Massive API key
        """
        super().__init__(venue="massive")
        self._api_key = api_key

    def _to_venue_symbol(self, symbol: Symbol) -> str:
        """Convert canonical symbol to Massive format.

        BTC_USD -> X:BTCUSD
        """
        return f"X:{symbol.value.replace('_USD', 'USD')}"

    def _from_venue_symbol(self, venue_symbol: str) -> Symbol:
        """Convert Massive format to canonical symbol.

        X:BTCUSD -> BTC_USD
        """
        base = venue_symbol.replace("X:", "").replace("USD", "")
        return Symbol(value=f"{base}_USD")

    async def backfill(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Backfill historical data from Massive.

        Chunks requests into 30-day windows to comply with rate limits.
        2 years of data = ~24 chunks = ~26 minutes total time.

        Args:
            symbol: Canonical symbol
            start: Start datetime
            end: End datetime

        Returns:
            List of normalized candles
        """
        candles: list[Candle] = []
        current = start
        chunk_count = 0

        while current < end:
            chunk_end = min(current + timedelta(days=30), end)
            str_start = current.strftime("%Y-%m-%d")
            str_end = chunk_end.strftime("%Y-%m-%d")

            # Rate limiting
            if chunk_count > 0 and chunk_count % self.RATE_LIMIT_CALLS == 0:
                logger.info("Rate limit reached, waiting...")
                time.sleep(self.RATE_LIMIT_WAIT)

            chunk_candles = await self._fetch_chunk(symbol, str_start, str_end)
            candles.extend(chunk_candles)
            chunk_count += 1

            logger.info(
                "Fetched chunk",
                symbol=symbol.value,
                chunk=chunk_count,
                candles=len(chunk_candles),
            )

            current = chunk_end + timedelta(days=1)

        return candles

    async def _fetch_chunk(
        self,
        symbol: Symbol,
        start: str,
        end: str,
    ) -> list[Candle]:
        """Fetch single 30-day chunk."""
        ticker = self._to_venue_symbol(symbol)
        url = f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}"
        params: httpx.QueryParams = {
            "adjusted": True,
            "sort": "asc",
            "limit": 50000,
            "apiKey": self._api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=60.0)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        return [
            Candle(
                symbol=symbol.value,
                venue="massive",
                timestamp=datetime.fromtimestamp(r["t"] / 1000),
                open=float(r["o"]),
                high=float(r["h"]),
                low=float(r["l"]),
                close=float(r["c"]),
                volume=float(r["v"]),
                closed=True,
            )
            for r in results
        ]

    async def connect(self, symbols: list[Symbol]) -> None:
        """Not implemented - Massive is for backfill only."""
        raise NotImplementedError("Massive adapter does not support streaming")

    async def disconnect(self) -> None:
        """Cleanup - no-op for Massive."""
        pass
