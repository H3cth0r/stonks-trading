"""Service classes for bot control domain.

Pure business logic, no I/O operations.
All methods are deterministic and testable.
"""

from datetime import datetime
from typing import Any

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.botcontrol.worker_client import WorkerHTTPClient
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.logger import logger


class ProcessManager:
    """Manages bot processes via Bot Worker container.

    All bot operations are delegated to the Bot Worker container via HTTP API.
    The API container never spawns subprocesses directly.
    """

    def __init__(self):
        """Initialize ProcessManager with Worker HTTP client."""
        self._worker_client = WorkerHTTPClient()
        logger.info("ProcessManager initialized (Worker mode)")

    async def start_bot(
        self,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        config_path: str,
    ) -> BotProcess:
        """Start bot by delegating to Worker HTTP API.

        Args:
            bot_type: Type of bot (e.g., "neat_swing")
            instance_id: Bot instance identifier
            symbols: List of trading symbols
            mode: Trading mode (dry_run or live)
            config_path: Path to NEAT config file

        Returns:
            BotProcess with status=STARTING and captured PID

        Raises:
            RuntimeError: If bot is already running or spawn fails
        """
        context_key = f"{bot_type}/{instance_id}"
        logger.info(f"Delegating bot {context_key} start to Worker via HTTP")

        try:
            response = await self._worker_client.start_bot(
                bot_type=bot_type,
                instance_id=instance_id,
                symbols=symbols,
                mode=mode,
                config_path=config_path,
            )

            # Convert response to BotProcess
            bot_process = BotProcess(
                bot_type=bot_type,
                bot_instance_id=instance_id,
                mode=mode,
                symbols=symbols,
                pid=response.pid,
                status=ProcessStatus.STARTING,
                started_at=response.started_at,
                config_path=config_path,
            )

            logger.info(f"Worker started bot {context_key} with PID {response.pid}")
            return bot_process

        except Exception as e:
            logger.error(f"Worker failed to start bot {context_key}: {e}")
            raise RuntimeError(f"Worker failed to start bot: {e}") from e

    async def stop_bot(
        self,
        context: BotContext,
        graceful: bool = True,
        timeout_seconds: int = 30,
    ) -> tuple[ProcessStatus, int | None, str | None]:
        """Stop bot by delegating to Worker HTTP API.

        Args:
            context: BotContext identifying the bot
            graceful: If True, Worker sends SIGTERM first, then SIGKILL if needed
            timeout_seconds: Seconds to wait for graceful shutdown (handled by Worker)

        Returns:
            Tuple of (final_status, exit_code, error_message)
        """
        context_key = f"{context.bot_type}/{context.instance_id}"
        logger.info(f"Delegating bot {context_key} stop to Worker via HTTP")

        try:
            response = await self._worker_client.stop_bot(
                bot_type=context.bot_type,
                instance_id=context.instance_id,
                graceful=graceful,
            )

            # Map response status to ProcessStatus
            try:
                status = ProcessStatus(response.status)
            except ValueError:
                status = ProcessStatus.STOPPED

            return status, response.exit_code, response.message

        except Exception as e:
            logger.error(f"Worker failed to stop bot {context_key}: {e}")
            return ProcessStatus.ERROR, None, str(e)

    async def get_process_status(
        self,
        context: BotContext,
        pid: int | None,
    ) -> ProcessStatus:
        """Check if process is alive.

        In Worker architecture, status is tracked via database
        and Worker health checks. Direct PID checks are not available.

        Args:
            context: BotContext identifying the bot
            pid: OS process ID (not used in Worker mode, kept for interface)

        Returns:
            UNKNOWN (Worker manages actual process status)
        """
        # Worker manages subprocesses - status comes from database records
        # This method is kept for interface compatibility but returns UNKNOWN
        if pid is None:
            return ProcessStatus.UNKNOWN

        return ProcessStatus.UNKNOWN

    async def cleanup_stale_processes(
        self,
        stale_processes: list[BotProcess],
    ) -> list[BotProcess]:
        """Mark processes as ERROR if their PID is dead.

        Worker handles stale process cleanup internally.
        API layer should query Worker health for actual status.

        Args:
            stale_processes: List of processes to check

        Returns:
            Empty list (Worker handles this)
        """
        # Worker handles stale process cleanup
        return []

    @classmethod
    def is_process_running(cls, pid: int) -> bool:
        """Check if a process is running.

        Args:
            pid: Process ID to check

        Returns:
            False (Worker manages processes, not API)
        """
        # Worker manages processes - API doesn't have direct visibility
        return False

    async def kill_process_immediately(
        self,
        context: BotContext,
        pid: int | None,
    ) -> None:
        """Kill process immediately by delegating to Worker.

        Args:
            context: BotContext identifying the bot
            pid: Process ID (not used in Worker mode, kept for interface)
        """
        context_key = f"{context.bot_type}/{context.instance_id}"
        logger.warning(f"Delegating immediate kill for bot {context_key} to Worker")

        try:
            await self._worker_client.stop_bot(
                bot_type=context.bot_type,
                instance_id=context.instance_id,
                graceful=False,
            )
        except Exception as e:
            logger.error(f"Worker failed to kill bot {context_key}: {e}")

    async def clear_bot_state(self, context: BotContext) -> None:
        """Clear bot state from Redis.

        Args:
            context: BotContext identifying the bot
        """
        from stonks_trading.shared.redis_client import get_redis

        redis = await get_redis()
        context_key = f"{context.bot_type}/{context.instance_id}"

        # Clear state keys
        keys_to_delete = [
            f"bot:state:{context_key}",
            f"equity:history:{context_key}",
        ]

        for key in keys_to_delete:
            try:
                await redis.delete(key)
            except Exception:
                pass

        logger.info(f"Cleared state for bot {context_key}")


class BotStatusAssembler:
    """Assembles BotStatus from multiple sources."""

    @staticmethod
    def assemble(
        process: BotProcess,
        state: dict[str, Any] | None,
        last_trade_at: datetime | None,
    ) -> BotStatus:
        """Build status response from process + state + trade data.

        Args:
            process: BotProcess entity
            state: Optional state dict from BotStateModel
            last_trade_at: Optional timestamp of last trade

        Returns:
            Complete BotStatus entity
        """
        current_equity = None
        position_count = 0

        if state:
            current_equity = state.get("current_equity")
            positions = state.get("positions", {})
            position_count = len(positions)

        # Calculate last_seen
        last_seen = process.updated_at
        if process.status == ProcessStatus.RUNNING and process.started_at:
            last_seen = datetime.utcnow()

        # Build message based on status
        message = None
        if process.status == ProcessStatus.ERROR and process.error_message:
            message = process.error_message
        elif process.status == ProcessStatus.STARTING:
            message = "Bot is starting..."
        elif process.status == ProcessStatus.STOPPING:
            message = "Bot is stopping..."

        return BotStatus(
            bot_type=process.bot_type,
            bot_instance_id=process.bot_instance_id,
            status=process.status,
            mode=process.mode,
            uptime_seconds=process.uptime_seconds,
            last_trade_at=last_trade_at,
            current_equity=current_equity,
            position_count=position_count,
            pid=process.pid,
            message=message,
            last_seen=last_seen,
        )


class ProcessValidator:
    """Validates bot process operations."""

    VALID_BOT_TYPES = {"neat_swing"}
    VALID_MODES = {"dry_run", "live"}

    @classmethod
    def validate_bot_type(cls, bot_type: str) -> bool:
        """Check if bot type is valid."""
        return bot_type in cls.VALID_BOT_TYPES

    @classmethod
    def validate_mode(cls, mode: str) -> bool:
        """Check if trading mode is valid."""
        return mode in cls.VALID_MODES

    @classmethod
    def validate_symbols(cls, symbols: list[str]) -> tuple[bool, str | None]:
        """Validate symbol list.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not symbols:
            return False, "At least one symbol required"

        for symbol in symbols:
            if not symbol or len(symbol) < 3:
                return False, f"Invalid symbol: {symbol}"

        return True, None
