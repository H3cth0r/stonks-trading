#!/usr/bin/env python3
"""Manual Parquet sync utility.

Syncs DuckDB data to Tigris S3 as Parquet partitions.
Useful for manual archival or disaster recovery.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient
from stonks_trading.shared.storage.tigris_client import TigrisClient


def sync_symbol_to_tigris(
    symbol: str,
    year: int | None = None,
    month: int | None = None,
    duckdb_path: str = "data/neat.db",
) -> bool:
    """Sync a symbol's data to Tigris.

    Args:
        symbol: Symbol to sync (e.g., BTC_USD)
        year: Specific year to sync (default: current year)
        month: Specific month to sync (default: current month)
        duckdb_path: Path to DuckDB database

    Returns:
        True if successful
    """
    # Initialize clients
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    if not settings.s3_endpoint:
        print("Error: S3_ENDPOINT not configured", file=sys.stderr)
        return False

    tigris = TigrisClient(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )

    try:
        target = Symbol(value=symbol)

        # Default to current year/month if not specified
        now = datetime.now(timezone.utc)
        year = year or now.year
        month = month or now.month

        # Get data for the month
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        data = duckdb.get_data_range(target, start, end)

        if not data:
            print(f"No data for {symbol} in {year}-{month:02d}")
            return False

        # Convert to DataFrame
        import pandas as pd

        df = pd.DataFrame(data)
        if "timestamp" in df.columns:
            df = df.drop(columns=["timestamp"])

        # Upload to Tigris
        key = tigris.upload_ohlcv_partition(
            symbol=symbol.replace("_", ""),  # Binance format
            year=year,
            month=month,
            df=df,
        )

        print(f"Synced {len(df)} rows to Tigris: {key}")
        return True

    except Exception as e:
        logger.error("Sync failed", symbol=symbol, error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return False
    finally:
        duckdb.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync DuckDB data to Tigris S3")
    parser.add_argument("--symbol", required=True, help="Symbol to sync (e.g., BTC_USD)")
    parser.add_argument("--year", type=int, help="Year to sync (default: current)")
    parser.add_argument("--month", type=int, help="Month to sync (default: current)")
    parser.add_argument("--duckdb-path", default="data/neat.db", help="Path to DuckDB database")

    args = parser.parse_args()

    success = sync_symbol_to_tigris(
        symbol=args.symbol,
        year=args.year,
        month=args.month,
        duckdb_path=args.duckdb_path,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
