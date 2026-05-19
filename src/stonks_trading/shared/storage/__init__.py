"""Storage layer module.

Provides clients for the three-layer storage architecture:
- DuckDB: Local analytical cache (hot layer)
- Tigris S3: Parquet archival (cold layer)
- Cache Manager: Coordinates between layers
"""

from stonks_trading.shared.storage.duckdb_client import DuckDBClient
from stonks_trading.shared.storage.tigris_client import TigrisClient

__all__ = ["DuckDBClient", "TigrisClient"]
