"""Service classes for bot control domain.

Pure business logic, no I/O operations.
All methods are deterministic and testable.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.trading.value_objects import BotContext

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages OS-level bot processes.

    Handles spawning subprocesses, stopping them gracefully,
    and checking process status via PID.
    """

    # Track spawned processes for cleanup
    _processes: dict[str, asyncio.subprocess.Process] = {}

    async def start_bot(
        self,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        config_path: str,
    ) -> BotProcess:
        """Spawn bot subprocess via asyncio.create_subprocess_exec.

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

        # Check if already running in our tracking
        if context_key in self._processes:
            existing_process = self._processes[context_key]
            if existing_process.returncode is None:
                raise RuntimeError(
                    f"Bot {context_key} is already running (PID: {existing_process.pid})"
                )
            else:
                # Process has finished, remove it
                del self._processes[context_key]

        # Build command
        cmd = [
            "python",
            "-m",
            f"stonks_trading.bots.{bot_type}",
            "--symbols",
            *symbols,
            "--mode",
            mode,
            "--instance-id",
            instance_id,
            "--config-path",
            config_path,
        ]

        logger.info(f"Starting bot {context_key} with command: {' '.join(cmd)}")

        try:
            # Spawn subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Store for tracking
            self._processes[context_key] = process

            # Create BotProcess entity
            bot_process = BotProcess(
                bot_type=bot_type,
                bot_instance_id=instance_id,
                mode=mode,
                symbols=symbols,
                pid=process.pid,
                status=ProcessStatus.STARTING,
                started_at=datetime.utcnow(),
                config_path=config_path,
            )

            logger.info(f"Started bot {context_key} with PID {process.pid}")
            return bot_process

        except Exception as e:
            logger.error(f"Failed to start bot {context_key}: {e}")
            raise RuntimeError(f"Failed to start bot: {e}") from e

    async def stop_bot(
        self,
        context: BotContext,
        graceful: bool = True,
        timeout_seconds: int = 30,
    ) -> tuple[ProcessStatus, int | None, str | None]:
        """Stop bot subprocess.

        Args:
            context: BotContext identifying the bot
            graceful: If True, send SIGTERM first, then SIGKILL if needed
            timeout_seconds: Seconds to wait for graceful shutdown

        Returns:
            Tuple of (final_status, exit_code, error_message)
        """
        context_key = f"{context.bot_type}/{context.instance_id}"

        # Check our process tracking first
        if context_key in self._processes:
            process = self._processes[context_key]

            if process.returncode is not None:
                # Already stopped
                del self._processes[context_key]
                return ProcessStatus.STOPPED, process.returncode, None

            # Try graceful shutdown
            if graceful:
                try:
                    process.terminate()  # SIGTERM
                    logger.info(f"Sent SIGTERM to bot {context_key} (PID: {process.pid})")

                    # Wait for graceful shutdown
                    try:
                        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
                        del self._processes[context_key]
                        return ProcessStatus.STOPPED, process.returncode, None
                    except TimeoutError:
                        logger.warning(
                            f"Bot {context_key} did not stop gracefully, sending SIGKILL"
                        )
                        process.kill()  # SIGKILL
                        await process.wait()
                        del self._processes[context_key]
                        return ProcessStatus.STOPPED, process.returncode, "Killed after timeout"

                except ProcessLookupError:
                    # Process already gone
                    del self._processes[context_key]
                    return ProcessStatus.STOPPED, None, None
            else:
                # Immediate kill
                process.kill()
                await process.wait()
                del self._processes[context_key]
                return ProcessStatus.STOPPED, process.returncode, "Killed immediately"

        # Check if process exists via PID (from database record)
        # This is handled by the caller with the process record
        return ProcessStatus.UNKNOWN, None, "Process not tracked locally"

    async def get_process_status(
        self,
        context: BotContext,
        pid: int | None,
    ) -> ProcessStatus:
        """Check if process is alive via pid check.

        Args:
            context: BotContext identifying the bot
            pid: OS process ID to check

        Returns:
            RUNNING if alive, STOPPED if dead, UNKNOWN if no PID
        """
        if pid is None:
            return ProcessStatus.UNKNOWN

        context_key = f"{context.bot_type}/{context.instance_id}"

        # Check our tracking first
        if context_key in self._processes:
            process = self._processes[context_key]
            if process.returncode is None:
                return ProcessStatus.RUNNING
            else:
                return ProcessStatus.STOPPED

        # Check via os.kill with signal 0 (doesn't actually send signal)
        try:
            os.kill(pid, 0)
            return ProcessStatus.RUNNING
        except (OSError, ProcessLookupError):
            return ProcessStatus.STOPPED

    async def cleanup_stale_processes(
        self,
        stale_processes: list[BotProcess],
    ) -> list[BotProcess]:
        """Mark processes as ERROR if their PID is dead.

        Args:
            stale_processes: List of processes to check

        Returns:
            List of processes that were marked stale
        """
        cleaned = []

        for process in stale_processes:
            if process.pid is not None:
                actual_status = await self.get_process_status(
                    BotContext(
                        bot_type=process.bot_type,
                        instance_id=process.bot_instance_id,
                    ),
                    process.pid,
                )

                if actual_status == ProcessStatus.STOPPED:
                    process.status = ProcessStatus.ERROR
                    process.error_message = "Process died unexpectedly"
                    cleaned.append(process)

        return cleaned

    @classmethod
    def is_process_running(cls, pid: int) -> bool:
        """Static method to check if a process is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process exists
        """
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


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
