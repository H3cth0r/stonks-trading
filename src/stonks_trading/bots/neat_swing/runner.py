"""NEAT Swing Bot CLI runner.

Entry point for running the live trading bot:
    python -m stonks_trading.bots.neat_swing

Usage:
    python -m stonks_trading.bots.neat_swing \\
        --symbols BTC_USD ETH_USD \\
        --mode dry_run \\
        --instance-id my-bot-1
"""

import asyncio
import contextlib
import logging
import signal
import sys
from typing import Any

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
from stonks_trading.domains.trading.adapters import DryRunAdapter
from stonks_trading.domains.trading.enums import TradingMode
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.scheduler import Scheduler
from stonks_trading.shared.websocket_client import WebSocketClient

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
    import argparse

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

    parsed = parser.parse_args(args)

    return {
        "symbols": parsed.symbols,
        "mode": parsed.mode,
        "instance_id": parsed.instance_id,
        "config_path": parsed.config_path,
        "log_level": parsed.log_level,
    }


async def run_bot(
    symbols: list[str],
    mode: str,
    instance_id: str,
    config_path: str,
) -> None:
    """Initialize and run the trading bot.

    Args:
        symbols: List of trading symbols
        mode: Trading mode (dry_run or live)
        instance_id: Bot instance identifier
        config_path: Path to NEAT config
    """
    # Create bot context
    context = BotContext(bot_type="neat_swing", instance_id=instance_id)

    # Create symbols
    symbol_objects = [Symbol(value=s) for s in symbols]

    # Create strategy
    strategy = NeatSwingStrategy(config_path=config_path)

    # Create initial state
    initial_state = NeatSwingState()

    # Create bot
    bot = NeatSwingBot(
        context=context,
        symbols=symbol_objects,
        mode=TradingMode(mode),
        strategy=strategy,
        initial_state=initial_state,
        config_path=config_path,
    )

    # Set up adapter based on mode
    if mode == "dry_run":
        adapter = DryRunAdapter(
            initial_balance={"USDT": 10000.0, "BTC": 0.0},
            slippage_bps=5.0,
            fee_rate=0.001,
        )
        # Set price source for dry run (would need real adapter in production)
        # adapter.set_price_source(real_adapter)
    else:
        # For live mode, would need BinanceAdapter with API credentials
        raise NotImplementedError("Live mode requires BinanceAdapter setup")

    bot.adapter = adapter

    # Set up WebSocket client
    ws_symbols = [s.replace("_", "").lower() + "usdt" for s in symbols]
    websocket = WebSocketClient(
        symbols=ws_symbols,
        callback=bot.handle_candle,
    )
    bot.set_websocket(websocket)

    # Set up scheduler
    scheduler = Scheduler()
    scheduler.start()

    # Handle shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot, scheduler)))

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(heartbeat_loop(bot))

    try:
        logger.info(f"Starting bot {context} with symbols {symbols} in {mode} mode")
        await bot.start()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        # Cancel heartbeat on exit
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def heartbeat_loop(bot: NeatSwingBot) -> None:
    """Background task that sends periodic heartbeats.

    Runs every 60 seconds while bot is running.
    """
    while bot._running:
        try:
            await bot.heartbeat()
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
        await asyncio.sleep(60)


async def shutdown(bot: NeatSwingBot, scheduler: Scheduler) -> None:
    """Graceful shutdown handler.

    Args:
        bot: Bot instance to stop
        scheduler: Scheduler to stop
    """
    logger.info("Shutdown signal received")
    scheduler.stop()
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
            )
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
