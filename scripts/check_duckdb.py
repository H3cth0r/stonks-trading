#!/usr/bin/env python3
"""Check DuckDB data storage status.

This script verifies that DuckDB is properly storing OHLCV data
and displays statistics about the stored data.
"""

import sys
from datetime import timedelta

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


def main() -> int:
    """Check DuckDB status."""
    client = DuckDBClient()
    client.connect()

    try:
        stats = client.get_stats()

        print("\n=== DuckDB Status ===")
        print(f"Database: {stats['db_path']}")
        print(f"Size: {stats['db_size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"Total rows: {stats['total_rows']}")

        if stats['symbols']:
            print("\nSymbol coverage:")
            for sym in stats['symbols']:
                print(f"  - {sym['symbol']}: {sym['row_count']} rows")
                print(f"    Range: {sym['earliest']} to {sym['latest']}")

                # Check if we have 30 days of data
                if sym['earliest'] and sym['latest']:
                    from datetime import datetime, timezone
                    earliest = sym['earliest']
                    latest = sym['latest']
                    if earliest.tzinfo is None:
                        earliest = earliest.replace(tzinfo=timezone.utc)
                    if latest.tzinfo is None:
                        latest = latest.replace(tzinfo=timezone.utc)
                    days = (latest - earliest).days
                    print(f"    Duration: {days} days")
                    if days >= 30:
                        print(f"    ✅ Has 30+ days of data")
                    else:
                        print(f"    ⚠️  Only {days} days (need 30 for full feature computation)")
        else:
            print("\n⚠️  No data in database")
            return 1

        # Check recent data availability
        print("\n=== Recent Data Check ===")
        for sym in stats['symbols']:
            symbol = Symbol(value=sym['symbol'])
            recent = client.get_recent_data(symbol, lookback=timedelta(days=1))
            print(f"  {sym['symbol']}: {len(recent)} rows in last 24 hours")

        return 0

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
