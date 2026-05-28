"""Instrument domain - consolidated market data + instrument registry.

Formerly separate market_data and instruments domains, now unified.
"""

from stonks_trading.domains.instruments.entities import (
    Candle,
    Instrument,
    OrderBook,
    Tick,
    TimeRange,
)
from stonks_trading.domains.instruments.services import (
    backfill_from_massive,
    disable_instrument,
    enable_instrument,
    get_instrument,
    get_instrument_status,
    get_job_status,
    list_instruments,
    register_instrument,
    set_job_status,
    update_instrument_data,
)

__all__ = [
    # Instrument registry
    "Instrument",
    "register_instrument",
    "get_instrument",
    "list_instruments",
    "enable_instrument",
    "disable_instrument",
    "get_instrument_status",
    # Market data
    "Candle",
    "OrderBook",
    "Tick",
    "TimeRange",
    # Backfill operations
    "backfill_from_massive",
    "set_job_status",
    "get_job_status",
]
