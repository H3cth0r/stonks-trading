#!/usr/bin/env python3
"""Historical data backfill script.

Backfills historical OHLCV data from Binance to DuckDB.
Useful for initial data loading or filling gaps.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.ingest.binance import BinanceAdapter
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


async def backfill_symbol(
    symbol: str,
    days: int,
    use_testnet: bool = True,
    duckdb_path: str = "data/neat.db",
) -> int:
    """Backfill a single symbol.

    Args:
        symbol: Symbol to backfill (e.g., BTC_USD)
        days: Number of days to backfill
        use_testnet: Use Binance testnet
        duckdb_path: Path to DuckDB database

    Returns:
        Number of candles fetched
    """
    target = Symbol(value=symbol)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"Backfilling {symbol} from {start} to {end}...")

    adapter = BinanceAdapter(use_testnet=use_testnet)
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    try:
        candles = await adapter.backfill(target, start, end)
        count = duckdb.insert_candles_batch(candles)

        print(f"Backfilled {count} candles for {symbol}")
        return count

    except Exception as e:
        logger.error("Backfill failed", symbol=symbol, error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 0
    finally:
        await adapter.disconnect()
        duckdb.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Backfill historical OHLCV data")
    parser.add_argument("--symbol", required=True, help="Symbol to backfill (e.g., BTC_USD)")
    parser.add_argument("--days", type=int, default=7, help="Number of days to backfill")
    parser.add_argument("--testnet", action="store_true", default=True, help="Use Binance testnet")
    parser.add_argument("--production", action="store_true", help="Use Binance production")
    parser.add_argument("--duckdb-path", default="data/neat.db", help="Path to DuckDB database")

    args = parser.parse_args()

    use_testnet = not args.production if args.production else args.testnet

    count = asyncio.run(backfill_symbol(
        symbol=args.symbol,
        days=args.days,
        use_testnet=use_testnet,
        duckdb_path=args.duckdb_path,
    ))

    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
