"""Market data ingestion module.

Provides adapters for ingesting real-time and historical market data
from various exchanges. Supports WebSocket streaming and REST API backfill.
"""

from stonks_trading.shared.ingest.adapter import Candle, MarketDataAdapter
from stonks_trading.shared.ingest.binance import BinanceAdapter
from stonks_trading.shared.ingest.massive import MassiveAdapter

__all__ = ["Candle", "MarketDataAdapter", "BinanceAdapter", "MassiveAdapter"]
