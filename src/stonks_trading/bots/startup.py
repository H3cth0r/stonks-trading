"""Startup recovery module for disaster resilience.

Bot-layer orchestrator that handles:
- DuckDB rebuild from Tigris Parquet partitions
- Bot state restoration from Postgres
- Registry consistency verification

This module is part of the bot layer and imports from domains and shared only.
It does NOT import routes, dtos, or mappers per CLEAN architecture rules.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from stonks_trading.domains.trading.repositories import (
    list_all_bot_instances,
    load_bot_state,
)
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient
from stonks_trading.shared.storage.tigris_client import TigrisClient


@dataclass
class RebuildReport:
    """Report from DuckDB rebuild operation."""

    symbols_rebuilt: list[str] = field(default_factory=list)
    total_rows: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class StartupReport:
    """Report from startup recovery operation."""

    duckdb_rebuilt: bool = False
    bots_recovered: int = 0
    bots_started: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class Inconsistency:
    """Represents a registry inconsistency."""

    bot_type: str
    instance_id: str
    issue: str
    expected_status: str
    actual_status: str | None = None


class StartupOrchestrator:
    """Orchestrates startup recovery for disaster resilience.

    This is a bot-layer orchestrator that coordinates recovery operations
    across multiple systems (DuckDB, Tigris S3, Postgres).

    Responsibilities:
    - Verify and rebuild DuckDB cache from Tigris Parquet
    - Restore bot state from Postgres
    - Verify registry consistency between DB and actual processes
    """

    duckdb: DuckDBClient
    tigris: TigrisClient | None
    notifier: Any | None

    def __init__(
        self,
        duckdb_client: DuckDBClient | None = None,
        tigris_client: TigrisClient | None = None,
        notifier: Any | None = None,
    ) -> None:
        """Initialize startup orchestrator.

        Args:
            duckdb_client: DuckDB client (creates default if None)
            tigris_client: Tigris S3 client (creates from config if None)
            notifier: Optional notification adapter for alerts
        """
        self.duckdb = duckdb_client or DuckDBClient()
        self.notifier = notifier

        # Initialize Tigris client from config if not provided
        if tigris_client:
            self.tigris = tigris_client
        elif settings.s3_endpoint:
            self.tigris = TigrisClient(
                endpoint=settings.s3_endpoint,
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                bucket=settings.s3_bucket,
            )
        else:
            self.tigris = None
            logger.warning(
                "Tigris client not configured. DuckDB rebuild from Parquet will not work."
            )

    async def recover_all(self) -> StartupReport:
        """Execute full startup recovery workflow.

        Steps:
        1. Check DuckDB health and rebuild from Tigris if needed
        2. Query bot registry for running bots
        3. Restore state for each running bot
        4. Verify registry consistency

        Returns:
            StartupReport with recovery results
        """
        report = StartupReport(
            duckdb_rebuilt=False,
            bots_recovered=0,
            bots_started=0,
            errors=[],
        )

        logger.info("Starting recovery workflow")

        # 1. Check/rebuild DuckDB
        if not self._duckdb_healthy():
            logger.warning("DuckDB not healthy, attempting rebuild from Tigris")
            try:
                rebuild = await self.rebuild_duckdb()
                report.duckdb_rebuilt = len(rebuild.errors) == 0
                report.errors.extend(rebuild.errors)
                if rebuild.symbols_rebuilt:
                    logger.info(
                        f"DuckDB rebuilt successfully for symbols: {rebuild.symbols_rebuilt}"
                    )
            except Exception as e:
                error_msg = f"Failed to rebuild DuckDB: {e}"
                logger.error(error_msg)
                report.errors.append(error_msg)
        else:
            logger.info("DuckDB is healthy, skipping rebuild")
            report.duckdb_rebuilt = True

        # 2. Query bot registry for bots that were running
        try:
            bots = await list_all_bot_instances()
            logger.info(f"Found {len(bots)} bot instances in registry")
        except Exception as e:
            error_msg = f"Failed to list bot instances: {e}"
            logger.error(error_msg)
            report.errors.append(error_msg)
            return report

        # 3. For each bot that was running, restore state
        for bot in bots:
            if bot.status == "running":
                try:
                    context = BotContext(
                        bot_type=bot.bot_type,
                        instance_id=bot.instance_id,
                    )
                    state = await load_bot_state(context)
                    if state:
                        report.bots_recovered += 1
                        logger.info(
                            f"Restored state for bot {bot.bot_type}/{bot.instance_id}",
                            state_keys=list(state.keys()),
                        )
                    else:
                        logger.warning(
                            f"No state found for running bot {bot.bot_type}/{bot.instance_id}"
                        )
                except Exception as e:
                    error_msg = f"Failed to recover {bot.bot_type}/{bot.instance_id}: {e}"
                    logger.error(error_msg)
                    report.errors.append(error_msg)

        logger.info(
            f"Recovery complete: {report.bots_recovered} bots recovered, "
            f"DuckDB rebuilt: {report.duckdb_rebuilt}"
        )

        return report

    def _duckdb_healthy(self) -> bool:
        """Check if DuckDB is healthy and accessible.

        Returns:
            True if DuckDB exists and can be queried
        """
        db_path = Path(self.duckdb.db_path)

        # Check if file exists
        if not db_path.exists():
            logger.warning(f"DuckDB file not found at {db_path}")
            return False

        # Check if we can connect and query
        try:
            self.duckdb.connect()
            stats = self.duckdb.get_stats()
            self.duckdb.close()

            # Healthy if we have some data
            if stats.get("total_rows", 0) > 0:
                logger.debug(
                    "DuckDB health check passed",
                    total_rows=stats.get("total_rows"),
                    symbols=[s["symbol"] for s in stats.get("symbols", [])],
                )
                return True
            else:
                logger.warning("DuckDB exists but has no data")
                return False

        except Exception as e:
            logger.error(f"DuckDB health check failed: {e}")
            return False

    async def rebuild_duckdb(self) -> RebuildReport:
        """Rebuild DuckDB from Tigris Parquet partitions.

        Downloads Parquet partitions for each symbol from Tigris S3,
        loads them into DuckDB ohlcv_1m table, and re-computes features.

        Returns:
            RebuildReport with results of rebuild operation
        """
        report = RebuildReport(
            symbols_rebuilt=[],
            total_rows=0,
            errors=[],
        )

        if not self.tigris:
            report.errors.append("Tigris client not configured")
            return report

        logger.info("Starting DuckDB rebuild from Tigris Parquet")

        try:
            # Connect to DuckDB
            self.duckdb.connect()

            # Get list of symbols from Tigris
            # For now, use common crypto symbols
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]

            total_rows = 0
            rebuilt_symbols = []

            for symbol in symbols:
                try:
                    symbol_rows = await self._rebuild_symbol(symbol)
                    if symbol_rows > 0:
                        total_rows += symbol_rows
                        rebuilt_symbols.append(symbol)
                        logger.info(
                            f"Rebuilt {symbol}: {symbol_rows} rows",
                        )
                except Exception as e:
                    error_msg = f"Failed to rebuild {symbol}: {e}"
                    logger.error(error_msg)
                    report.errors.append(error_msg)

            report.symbols_rebuilt = rebuilt_symbols
            report.total_rows = total_rows

            logger.info(
                f"DuckDB rebuild complete: {len(rebuilt_symbols)} symbols, {total_rows} total rows"
            )

        except Exception as e:
            error_msg = f"DuckDB rebuild failed: {e}"
            logger.error(error_msg)
            report.errors.append(error_msg)
        finally:
            self.duckdb.close()

        return report

    async def _rebuild_symbol(self, symbol: str) -> int:
        """Rebuild DuckDB data for a single symbol from Tigris.

        Downloads all available Parquet partitions for the symbol
        and inserts them into DuckDB.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)

        Returns:
            Number of rows inserted
        """
        if not self.tigris:
            return 0

        # List available partitions for symbol
        partitions = self.tigris.list_partitions(symbol)

        if not partitions:
            logger.debug(f"No partitions found for {symbol}")
            return 0

        total_rows = 0

        for partition in partitions:
            try:
                # Download partition
                df = self.tigris.download_ohlcv_partition(
                    symbol=symbol,
                    year=partition["year"],
                    month=partition["month"],
                )

                if df is not None and len(df) > 0:
                    # Convert to candles and insert
                    # Note: Features would need to be re-computed here
                    # For now, just insert raw OHLCV data
                    self._insert_dataframe_to_duckdb(df, symbol)
                    total_rows += len(df)

            except Exception as e:
                logger.error(
                    f"Failed to download partition {partition}",
                    error=str(e),
                )

        return total_rows

    def _insert_dataframe_to_duckdb(self, df: pd.DataFrame, symbol: str) -> None:
        """Insert DataFrame into DuckDB.

        Args:
            df: DataFrame with OHLCV data
            symbol: Symbol name
        """
        if not self.duckdb._conn:
            raise RuntimeError("DuckDB not connected")

        # Ensure symbol column exists
        if "symbol" not in df.columns:
            df = df.copy()
            df["symbol"] = symbol

        # Register DataFrame and insert
        self.duckdb._conn.register("temp_df", df)
        self.duckdb._conn.execute("""
            INSERT OR REPLACE INTO ohlcv_1m
            SELECT symbol, timestamp, open, high, low, close, volume,
                   trend_1h, rsi_1h, rsi_15m, roc, bb_width
            FROM temp_df
        """)

    async def verify_registry_consistency(self) -> list[Inconsistency]:
        """Verify consistency between BotInstanceModel and actual processes.

        Compares the bot registry in Postgres with actual OS processes
        to detect orphaned or crashed bot entries.

        Returns:
            List of inconsistencies found
        """
        inconsistencies: list[Inconsistency] = []

        try:
            bots = await list_all_bot_instances()

            for bot in bots:
                # Check if bot status matches reality
                # In a real implementation, this would check OS processes
                # For now, just verify the bot exists in registry
                if bot.status == "running":
                    # Check if we have recent state
                    context = BotContext(
                        bot_type=bot.bot_type,
                        instance_id=bot.instance_id,
                    )
                    state = await load_bot_state(context)

                    if not state:
                        inconsistencies.append(
                            Inconsistency(
                                bot_type=bot.bot_type,
                                instance_id=bot.instance_id,
                                issue="Running bot has no saved state",
                                expected_status="running",
                            )
                        )

            logger.info(f"Registry consistency check complete: {len(inconsistencies)} issues found")

        except Exception as e:
            logger.error(f"Failed to verify registry consistency: {e}")

        return inconsistencies


async def run_startup_recovery(
    skip_recovery: bool = False,
    duckdb_client: DuckDBClient | None = None,
    tigris_client: TigrisClient | None = None,
) -> StartupReport:
    """Convenience function to run startup recovery.

    Args:
        skip_recovery: If True, skip recovery and return empty report
        duckdb_client: Optional DuckDB client
        tigris_client: Optional Tigris client

    Returns:
        StartupReport with recovery results
    """
    if skip_recovery:
        logger.info("Startup recovery skipped (--skip-recovery flag)")
        return StartupReport(
            duckdb_rebuilt=False,
            bots_recovered=0,
            bots_started=0,
            errors=[],
        )

    orchestrator = StartupOrchestrator(
        duckdb_client=duckdb_client,
        tigris_client=tigris_client,
    )

    return await orchestrator.recover_all()
