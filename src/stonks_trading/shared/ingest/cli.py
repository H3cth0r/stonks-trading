"""CLI for data pipeline operations.

Provides command-line interface for:
- Starting/stopping data ingestion
- Backfilling historical data
- Verifying feature parity
- Checking storage status
"""

import asyncio
import signal
import sys
from datetime import UTC, datetime, timedelta

import click

from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.config import settings
from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.ingest.binance import BinanceAdapter
from stonks_trading.shared.ingest.orchestrator import IngestionOrchestrator
from stonks_trading.shared.logger import logger
from stonks_trading.shared.storage.duckdb_client import DuckDBClient
from stonks_trading.shared.storage.tigris_client import TigrisClient


@click.group()
def cli() -> None:
    """Data pipeline CLI for Stonks Trading.

    Commands for managing real-time and historical market data ingestion,
    backfilling, and storage operations.
    """
    pass


@cli.command()
@click.option(
    "--symbols",
    required=True,
    help="Comma-separated list of symbols (e.g., BTC_USD,ETH_USD)",
)
@click.option(
    "--duration",
    type=int,
    default=0,
    help="Duration in minutes to run (0 = indefinite)",
)
@click.option(
    "--testnet/--no-testnet",
    default=True,
    help="Use Binance testnet (default: True)",
)
@click.option(
    "--duckdb-path",
    default="data/neat.db",
    help="Path to DuckDB database",
)
@click.option(
    "--disable-tigris",
    is_flag=True,
    help="Disable Tigris archival",
)
def ingest(
    symbols: str,
    duration: int,
    testnet: bool,
    duckdb_path: str,
    disable_tigris: bool,
) -> None:
    """Start real-time data ingestion.

    Connects to Binance WebSocket for live 1m klines, computes features,
    and stores in DuckDB with optional Tigris archival.

    Examples:
        # Ingest BTC for 10 minutes using testnet
        python -m stonks_trading.shared.ingest.cli ingest --symbols BTC_USD --duration 10

        # Ingest multiple symbols indefinitely
        python -m stonks_trading.shared.ingest.cli ingest --symbols BTC_USD,ETH_USD --testnet
    """
    symbol_list = [Symbol(value=s.strip()) for s in symbols.split(",")]

    # Initialize components
    adapter = BinanceAdapter(use_testnet=testnet)
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    # Initialize Tigris if configured and not disabled
    tigris: TigrisClient | None = None
    if not disable_tigris and settings.s3_endpoint:
        tigris = TigrisClient(
            endpoint=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
        )

    features = LiveFeatureComputer(window_hours=200)

    orchestrator = IngestionOrchestrator(
        adapter=adapter,
        duckdb=duckdb,
        tigris=tigris,
        feature_computer=features,
    )

    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum: int, frame) -> None:  # type: ignore
        logger.info("Received shutdown signal", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def run() -> None:
        """Run ingestion until duration or shutdown signal."""
        await orchestrator.start(symbol_list)

        if duration > 0:
            logger.info(
                "Ingestion started",
                duration_minutes=duration,
                symbols=[s.value for s in symbol_list],
            )
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=duration * 60)
            except TimeoutError:
                logger.info("Ingestion duration reached")
        else:
            logger.info(
                "Ingestion started (indefinite)",
                symbols=[s.value for s in symbol_list],
            )
            await shutdown_event.wait()

        await orchestrator.stop()
        duckdb.close()

    asyncio.run(run())
    click.echo("Ingestion complete")


@cli.command()
@click.option(
    "--symbol",
    required=True,
    help="Symbol to backfill (e.g., BTC_USD)",
)
@click.option(
    "--days",
    type=int,
    default=1,
    help="Number of days to backfill",
)
@click.option(
    "--testnet/--no-testnet",
    default=True,
    help="Use Binance testnet",
)
@click.option(
    "--duckdb-path",
    default="data/neat.db",
    help="Path to DuckDB database",
)
def backfill(
    symbol: str,
    days: int,
    testnet: bool,
    duckdb_path: str,
) -> None:
    """Backfill historical data via REST API.

    Fetches historical 1m candles from Binance REST API and stores
    in DuckDB. Useful for initial data loading or gap repair.

    Examples:
        # Backfill 7 days of BTC data
        python -m stonks_trading.shared.ingest.cli backfill --symbol BTC_USD --days 7
    """
    target = Symbol(value=symbol)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)

    click.echo(f"Backfilling {symbol} from {start} to {end}...")

    async def run() -> None:
        adapter = BinanceAdapter(use_testnet=testnet)
        duckdb = DuckDBClient(db_path=duckdb_path)
        duckdb.connect()

        try:
            candles = await adapter.backfill(target, start, end)

            # Insert candles without features (will be computed on next live candle)
            count = duckdb.insert_candles_batch(candles)

            click.echo(f"Backfilled {count} candles")

        except Exception as e:
            click.echo(f"Backfill failed: {e}", err=True)
            raise click.ClickException(str(e)) from None
        finally:
            await adapter.disconnect()
            duckdb.close()

    asyncio.run(run())


@cli.command()
@click.option(
    "--duckdb-path",
    default="data/neat.db",
    help="Path to DuckDB database",
)
def status(duckdb_path: str) -> None:
    """Check data pipeline status.

    Displays statistics about DuckDB storage including row counts,
    symbol coverage, and date ranges.
    """
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    try:
        stats = duckdb.get_stats()

        click.echo("\n=== DuckDB Status ===")
        click.echo(f"Database: {stats['db_path']}")
        click.echo(f"Size: {stats['db_size_bytes'] / 1024 / 1024:.2f} MB")
        click.echo(f"Total rows: {stats['total_rows']}")

        if stats["symbols"]:
            click.echo("\nSymbol coverage:")
            for sym in stats["symbols"]:
                click.echo(f"  - {sym['symbol']}: {sym['row_count']} rows")
                click.echo(f"    Range: {sym['earliest']} to {sym['latest']}")
        else:
            click.echo("\nNo data in database")

    finally:
        duckdb.close()


@cli.command()
def verify_features() -> None:
    """Verify live features match training features.

    Creates synthetic candles and computes features using both
    the live feature computer and the training feature function.
    Compares outputs to ensure parity.
    """
    import numpy as np
    import pandas as pd

    from stonks_trading.domains.trading.neat.features import engineer_features

    click.echo("Verifying feature parity...")

    # Create synthetic candles (250 hours of data)
    np.random.seed(42)
    base_price = 50000.0
    candles = []

    for i in range(250 * 60):  # 250 hours
        noise = np.random.randn() * 100
        candles.append(
            Candle(
                symbol="BTC_USD",
                venue="test",
                timestamp=datetime.now(UTC) - timedelta(minutes=250 * 60 - i),
                open=base_price + noise,
                high=base_price + noise + 50,
                low=base_price + noise - 50,
                close=base_price + noise + 20,
                volume=10.0,
                closed=True,
            )
        )

    # Compute via live feature computer
    live = LiveFeatureComputer()
    for c in candles[:-1]:  # All but last
        live.on_candle(c)
    live_features = live.on_candle(candles[-1])

    # Compute via training function
    df = pd.DataFrame(
        [
            {"Open": c.open, "High": c.high, "Low": c.low, "Close": c.close, "Volume": c.volume}
            for c in candles
        ]
    )
    df.index = pd.DatetimeIndex([c.timestamp for c in candles])
    train_df = engineer_features(df)
    train_features = train_df.iloc[-1]

    # Compare
    if live_features is None:
        click.echo("ERROR: Live features returned None", err=True)
        sys.exit(1)

    click.echo("\n=== Feature Comparison ===")

    all_match = True
    for key in ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]:
        live_val = live_features[key]
        train_val = float(train_features[key])
        diff = abs(live_val - train_val)
        match = diff < 0.001

        status = "✓" if match else "✗"
        click.echo(f"{status} {key}: live={live_val:.6f}, train={train_val:.6f}, diff={diff:.6f}")

        if not match:
            all_match = False

    if all_match:
        click.echo("\n✓ All features match within tolerance (0.001)")
        sys.exit(0)
    else:
        click.echo("\n✗ Some features differ", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--duckdb-path",
    default="data/neat.db",
    help="Path to DuckDB database",
)
def prune(duckdb_path: str) -> None:
    """Prune old data from DuckDB.

    Removes data older than 35 days to maintain the rolling window.
    Should be run periodically (e.g., via cron or scheduled task).
    """
    duckdb = DuckDBClient(db_path=duckdb_path)
    duckdb.connect()

    try:
        deleted = duckdb.prune_old_data()
        click.echo(f"Pruned {deleted} old rows from DuckDB")
    finally:
        duckdb.close()


if __name__ == "__main__":
    cli()
