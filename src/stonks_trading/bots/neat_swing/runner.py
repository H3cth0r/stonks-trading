"""NEAT Swing Bot CLI runner - with IngestionOrchestrator integration.

Entry point for running the live trading bot:
    python -m stonks_trading.bots.neat_swing

Usage:
    python -m stonks_trading.bots.neat_swing \\
        --symbols BTC_USD ETH_USD \\
        --mode dry_run \\
        --instance-id my-bot-1
"""

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Any

from stonks_trading.bots import BotFactory, StrategyRegistry
from stonks_trading.bots.neat_swing import create_neat_swing_strategy
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.startup import run_startup_recovery
from stonks_trading.domains.trading.adapters import DryRunAdapter
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.binance import BinanceAdapter
from stonks_trading.shared.ingest.orchestrator import IngestionOrchestrator
from stonks_trading.shared.scheduler import Scheduler
from stonks_trading.shared.storage.duckdb_client import DuckDBClient

# Register NeatSwingStrategy factory (Phase 10C - strategy injection)
StrategyRegistry.register("neat_swing", create_neat_swing_strategy)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(args: list[str] | None = None) -> dict[str, Any]:
    """Parse command line arguments.

    Args:
        args: Command line args (uses sys.argv if None)

    Returns:
        Parsed arguments dict
    """
    parser = argparse.ArgumentParser(
        description="NEAT Swing Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=["BTC_USD"],
        help="Trading symbols (canonical format, e.g., BTC_USD)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="dry_run",
        choices=["dry_run", "live"],
        help="Trading mode",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default="default",
        help="Bot instance identifier",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default="config-neat.txt",
        help="Path to NEAT config file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--skip-recovery",
        action="store_true",
        default=False,
        help="Skip startup recovery (for testing)",
    )
    parser.add_argument(
        "--capital-allocation",
        type=float,
        default=None,
        help="Initial capital allocation for this bot",
    )

    parsed = parser.parse_args(args)

    return {
        "symbols": parsed.symbols,
        "mode": parsed.mode,
        "instance_id": parsed.instance_id,
        "config_path": parsed.config_path,
        "log_level": parsed.log_level,
        "skip_recovery": parsed.skip_recovery,
        "capital_allocation": parsed.capital_allocation,
    }


async def run_bot(
    symbols: list[str],
    mode: str,
    instance_id: str,
    config_path: str,
    capital_allocation: float | None,
    skip_recovery: bool = False,
) -> None:
    """Initialize and run the trading bot using BotFactory.

    Uses BotFactory.create() for proper strategy injection and dependency
    management per Phase 10C.

    Args:
        symbols: List of trading symbols
        mode: Trading mode (dry_run or live)
        instance_id: Bot instance identifier
        config_path: Path to NEAT config
        capital_allocation: Initial capital allocation for this bot
        skip_recovery: If True, skip startup recovery
    """
    # Run startup recovery before creating bot
    recovery_report = await run_startup_recovery(skip_recovery=skip_recovery)
    if recovery_report.errors:
        logger.warning(f"Startup recovery had errors: {recovery_report.errors}")
    else:
        logger.info(
            f"Startup recovery complete: "
            f"DuckDB rebuilt={recovery_report.duckdb_rebuilt}, "
            f"Bots recovered={recovery_report.bots_recovered}"
        )

    # Use BotFactory for proper strategy injection (Phase 10C)
    # Create initial state before passing to factory
    initial_state = NeatSwingState()
    if capital_allocation:
        initial_state.current_equity = capital_allocation
        initial_state.peak_equity = capital_allocation

    bot = BotFactory.create(
        bot_type="neat_swing",
        instance_id=instance_id,
        symbols=symbols,
        mode=mode,
        strategy_type="neat_swing",
        capital_allocation=capital_allocation,
        initial_state=initial_state,
        strategy_config={"config_path": config_path},
    )

    # Set up adapter based on mode
    if mode == "dry_run":
        # Use capital_allocation or default to 10000
        initial_balance = {
            "USDT": capital_allocation if capital_allocation else 10000.0,
            "BTC": 0.0,
        }
        adapter = DryRunAdapter(
            initial_balance=initial_balance,
            slippage_bps=5.0,
            fee_rate=0.001,
        )
    else:
        # For live mode, would need BinanceAdapter with API credentials
        raise NotImplementedError("Live mode requires BinanceAdapter setup")

    bot.adapter = adapter

    # NEW: Create IngestionOrchestrator for market data
    # This replaces the WebSocketClient
    duckdb = DuckDBClient()
    duckdb.connect()

    binance_adapter = BinanceAdapter(use_testnet=(mode == "dry_run"))
    feature_computer = LiveFeatureComputer(window_hours=200)

    orchestrator = IngestionOrchestrator(
        adapter=binance_adapter,
        duckdb=duckdb,
        tigris=None,  # Optional: add Tigris client for archival
        feature_computer=feature_computer,
    )

    # NEW: Connect bot to orchestrator's feature computer
    bot.set_orchestrator(orchestrator)  # type: ignore[attr-defined]

    # Set up scheduler
    scheduler = Scheduler()
    scheduler.start()

    # Handle shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(bot, scheduler, orchestrator))
        )

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(heartbeat_loop(bot))

    try:
        logger.info(f"Starting bot with IngestionOrchestrator for symbols {symbols}")

        # Start orchestrator first (backfills gaps, then connects WebSocket)
        await orchestrator.start([Symbol(value=s) for s in symbols])

        # Then start bot (now has access to primed feature computer)
        await bot.start()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        # Cancel heartbeat on exit
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def heartbeat_loop(bot: Any) -> None:
    """Background task that sends periodic heartbeats.

    Runs every 60 seconds while bot is running.
    """
    while bot._running:
        try:
            await bot.heartbeat()
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
        await asyncio.sleep(60)


async def shutdown(bot: Any, scheduler: Scheduler, orchestrator: IngestionOrchestrator) -> None:
    """Graceful shutdown handler.

    Args:
        bot: Bot instance to stop
        scheduler: Scheduler to stop
        orchestrator: IngestionOrchestrator to stop
    """
    logger.info("Shutdown signal received")
    scheduler.stop()
    await orchestrator.stop()
    await bot.stop()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Set log level
    logging.getLogger().setLevel(args["log_level"])

    try:
        asyncio.run(
            run_bot(
                symbols=args["symbols"],
                mode=args["mode"],
                instance_id=args["instance_id"],
                config_path=args["config_path"],
                capital_allocation=args["capital_allocation"],
                skip_recovery=args["skip_recovery"],
            )
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
