"""DuckDB client for local analytical cache.

Provides fast local storage for OHLCV data and computed features.
DuckDB serves as the "hot" cache layer in the three-tier storage architecture:
- Hot: DuckDB (local, fast queries)
- Warm: Neon Postgres (source of truth)
- Cold: Tigris S3 (archival, Parquet)

The DuckDB cache can always be rebuilt from Neon + Tigris data.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.logger import logger


class DuckDBClient:
    """DuckDB client for local feature and OHLCV cache.

    Maintains a rolling window of recent data (configurable, default 30 days)
    for fast feature computation and backtesting. Data is stored locally
    in a DuckDB database file with Parquet-like columnar storage.

    The schema includes both raw OHLCV data and pre-computed features
    (trend_1h, rsi_1h, rsi_15m, roc, bb_width) for efficient querying.

    Example:
        client = DuckDBClient(db_path="data/neat.db")
        client.connect()
        client.insert_candle(candle, features)
        recent_data = client.get_recent_data(Symbol(value="BTC_USD"))
        client.close()
    """

    def __init__(self, db_path: str = "data/neat.db") -> None:
        """Initialize DuckDB client.

        Creates the parent directory if it doesn't exist.

        Args:
            db_path: Path to DuckDB database file. Default is "data/neat.db"
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        """Initialize DuckDB connection and schema.

        Opens a connection to the DuckDB database and creates the
        required tables if they don't exist.

        Raises:
            duckdb.Error: If connection fails
        """
        self._conn = duckdb.connect(str(self.db_path))
        self._init_schema()
        logger.info(
            "DuckDB connection established",
            db_path=str(self.db_path),
        )

    def _init_schema(self) -> None:
        """Create tables if not exist.

        Initializes the following tables:
        - ohlcv_1m: 1-minute OHLCV data with pre-computed features
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        # OHLCV with pre-computed features
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_1m (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                trend_1h DOUBLE,
                rsi_1h DOUBLE,
                rsi_15m DOUBLE,
                roc DOUBLE,
                bb_width DOUBLE,
                PRIMARY KEY (symbol, timestamp)
            )
        """)

    def insert_candle(
        self,
        candle: Candle,
        features: dict[str, float] | None = None,
    ) -> None:
        """Insert candle with pre-computed features.

        Inserts a single candle into the ohlcv_1m table. If a candle
        with the same symbol and timestamp already exists, it will be
        replaced (UPSERT behavior).

        Args:
            candle: Normalized candle to insert
            features: Optional pre-computed features dictionary containing
                     trend_1h, rsi_1h, rsi_15m, roc, bb_width

        Raises:
            RuntimeError: If not connected to DuckDB
            duckdb.Error: If insert fails
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        features = features or {}

        self._conn.execute("""
            INSERT OR REPLACE INTO ohlcv_1m
            (symbol, timestamp, open, high, low, close, volume,
             trend_1h, rsi_1h, rsi_15m, roc, bb_width)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            candle.symbol,
            candle.timestamp,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            features.get("trend_1h"),
            features.get("rsi_1h"),
            features.get("rsi_15m"),
            features.get("roc"),
            features.get("bb_width"),
        ))

    def insert_candles_batch(
        self,
        candles: list[Candle],
        features_list: list[dict[str, float]] | None = None,
    ) -> int:
        """Insert multiple candles in a batch.

        More efficient than calling insert_candle for each candle
        when loading historical data.

        Args:
            candles: List of candles to insert
            features_list: Optional list of feature dictionaries, one per candle

        Returns:
            Number of candles inserted

        Raises:
            RuntimeError: If not connected to DuckDB
            ValueError: If features_list provided but length doesn't match candles
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        if features_list and len(features_list) != len(candles):
            raise ValueError("features_list length must match candles length")

        # Prepare data for bulk insert
        data = []
        for i, candle in enumerate(candles):
            features = features_list[i] if features_list else {}
            data.append((
                candle.symbol,
                candle.timestamp,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                features.get("trend_1h"),
                features.get("rsi_1h"),
                features.get("rsi_15m"),
                features.get("roc"),
                features.get("bb_width"),
            ))

        # Use executemany for bulk insert
        self._conn.executemany("""
            INSERT OR REPLACE INTO ohlcv_1m
            (symbol, timestamp, open, high, low, close, volume,
             trend_1h, rsi_1h, rsi_15m, roc, bb_width)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)

        return len(candles)

    def get_recent_data(
        self,
        symbol: Symbol,
        lookback: timedelta = timedelta(days=30),
    ) -> list[dict[str, Any]]:
        """Get recent OHLCV + features for a symbol.

        Queries the last N days of data for a symbol, including
        both raw OHLCV and computed features.

        Args:
            symbol: Symbol to query
            lookback: Time range to query (default: 30 days)

        Returns:
            List of dictionaries containing candle data and features,
            ordered by timestamp ascending (oldest first)

        Raises:
            RuntimeError: If not connected to DuckDB
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        since = datetime.utcnow() - lookback

        result = self._conn.execute("""
            SELECT * FROM ohlcv_1m
            WHERE symbol = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (symbol.value, since))

        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    def get_data_range(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Get OHLCV + features for a specific time range.

        Args:
            symbol: Symbol to query
            start: Start time (inclusive)
            end: End time (inclusive)

        Returns:
            List of dictionaries containing candle data and features,
            ordered by timestamp ascending

        Raises:
            RuntimeError: If not connected to DuckDB
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        result = self._conn.execute("""
            SELECT * FROM ohlcv_1m
            WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (symbol.value, start, end))

        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    def get_latest_timestamp(self, symbol: Symbol) -> datetime | None:
        """Get the timestamp of the most recent candle for a symbol.

        Used to determine where to start backfilling when starting
        the ingestion pipeline.

        Args:
            symbol: Symbol to query

        Returns:
            Timestamp of most recent candle, or None if no data

        Raises:
            RuntimeError: If not connected to DuckDB
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        result = self._conn.execute("""
            SELECT MAX(timestamp) FROM ohlcv_1m
            WHERE symbol = ?
        """, (symbol.value,))

        row = result.fetchone()
        return row[0] if row and row[0] else None

    def prune_old_data(
        self,
        retention: timedelta = timedelta(days=35),
    ) -> int:
        """Remove data older than retention period.

        Maintains the rolling window by deleting data older than
        the specified retention period. Should be called periodically
        (e.g., every 6 hours) to prevent unbounded growth.

        Args:
            retention: How long to keep data (default: 35 days)

        Returns:
            Number of rows deleted

        Raises:
            RuntimeError: If not connected to DuckDB
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        cutoff = datetime.utcnow() - retention

        result = self._conn.execute("""
            DELETE FROM ohlcv_1m
            WHERE timestamp < ?
        """, (cutoff,))

        deleted = result.rowcount

        logger.info(
            "Pruned old data from DuckDB",
            cutoff=cutoff.isoformat(),
            rows_deleted=deleted,
        )

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns information about the database including
        row counts, date ranges, and table sizes.

        Returns:
            Dictionary with database statistics

        Raises:
            RuntimeError: If not connected to DuckDB
        """
        if not self._conn:
            raise RuntimeError("Not connected to DuckDB")

        # Get row count
        row_count_result = self._conn.execute(
            "SELECT COUNT(*) FROM ohlcv_1m"
        ).fetchone()
        row_count = row_count_result[0] if row_count_result else 0

        # Get symbol counts
        symbol_counts = self._conn.execute("""
            SELECT symbol, COUNT(*) as count,
                   MIN(timestamp) as earliest,
                   MAX(timestamp) as latest
            FROM ohlcv_1m
            GROUP BY symbol
        """).fetchall()

        # Get database file size
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_rows": row_count,
            "db_path": str(self.db_path),
            "db_size_bytes": db_size,
            "symbols": [
                {
                    "symbol": row[0],
                    "row_count": row[1],
                    "earliest": row[2],
                    "latest": row[3],
                }
                for row in symbol_counts
            ],
        }

    def close(self) -> None:
        """Close connection.

        Closes the DuckDB connection and releases resources.
        Safe to call multiple times.
        """
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("DuckDB connection closed")
