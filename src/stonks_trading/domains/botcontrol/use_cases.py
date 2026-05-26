"""Use cases for bot control domain.

Orchestration layer - coordinates repositories, services, and entities.
No business logic here - pure coordination.
"""

import contextlib
from datetime import datetime

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.botcontrol.repositories import (
    check_bot_instance_exists,
    create_bot_process,
    delete_bot_process,
    get_bot_process,
    list_running_bots,
    update_bot_process_status,
)
from stonks_trading.domains.botcontrol.services import (
    BotStatusAssembler,
    ProcessManager,
    ProcessValidator,
)
from stonks_trading.domains.trading.repositories import (
    get_bot_instance,
    load_bot_state,
)
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.logger import logger


class StartBotUseCase:
    """Start a bot instance.

    Business Logic:
    1. Validate bot is registered
    2. Check not already running
    3. Start process via ProcessManager
    4. Persist BotProcess record
    5. Return initial status
    """

    def __init__(self) -> None:
        self.process_manager = ProcessManager()

    async def execute(
        self,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str = "dry_run",
        config_path: str = "config-neat.txt",
    ) -> BotProcess:
        """Execute the start bot use case.

        Args:
            bot_type: Bot type (e.g., "neat_swing")
            instance_id: Bot instance ID
            symbols: Trading symbols list
            mode: Trading mode (dry_run or live)
            config_path: Path to NEAT config

        Returns:
            BotProcess entity with status=STARTING

        Raises:
            ValueError: If bot not registered or validation fails
            RuntimeError: If process spawn fails
        """
        # Validate bot type
        if not ProcessValidator.validate_bot_type(bot_type):
            raise ValueError(f"Invalid bot type: {bot_type}")

        # Validate mode
        if not ProcessValidator.validate_mode(mode):
            raise ValueError(f"Invalid mode: {mode}")

        # Validate symbols
        is_valid, error = ProcessValidator.validate_symbols(symbols)
        if not is_valid:
            raise ValueError(error)

        # Check bot is registered
        is_registered = await check_bot_instance_exists(bot_type, instance_id)
        if not is_registered:
            raise ValueError(
                f"Bot {bot_type}/{instance_id} not registered. "
                "Register via POST /api/v1/bots first."
            )

        # Check if process already exists
        existing = await get_bot_process(bot_type, instance_id)
        if existing and existing.is_running:
            raise ValueError(
                f"Bot {bot_type}/{instance_id} is already running (PID: {existing.pid})"
            )

        # Clean up old stopped process record if exists
        if existing and not existing.is_running:
            context = BotContext(bot_type=bot_type, instance_id=instance_id)
            await delete_bot_process(context)
            logger.info(f"Cleaned up old process record for {bot_type}/{instance_id}")

        # Start the process
        bot_process = await self.process_manager.start_bot(
            bot_type=bot_type,
            instance_id=instance_id,
            symbols=symbols,
            mode=mode,
            config_path=config_path,
        )

        # Persist the process record
        bot_process = await create_bot_process(bot_process)

        logger.info(f"Started bot {bot_type}/{instance_id} with PID {bot_process.pid}")
        return bot_process


class StopBotUseCase:
    """Stop a bot instance gracefully."""

    def __init__(self) -> None:
        self.process_manager = ProcessManager()

    async def execute(
        self,
        bot_type: str,
        instance_id: str,
        graceful: bool = True,
    ) -> BotProcess:
        """Execute the stop bot use case.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance ID
            graceful: If True, send SIGTERM first

        Returns:
            Updated BotProcess with status=STOPPED

        Raises:
            ValueError: If bot process not found
        """
        # Get existing process
        bot_process = await get_bot_process(bot_type, instance_id)
        if not bot_process:
            raise ValueError(f"Bot {bot_type}/{instance_id} process not found")

        if bot_process.status == ProcessStatus.STOPPED:
            logger.info(f"Bot {bot_type}/{instance_id} is already stopped")
            return bot_process

        # Update status to STOPPING
        context = BotContext(bot_type=bot_type, instance_id=instance_id)
        bot_process = await update_bot_process_status(
            context=context,
            status=ProcessStatus.STOPPING,
        )

        # Stop the process
        final_status, exit_code, error_message = await self.process_manager.stop_bot(
            context=context,
            graceful=graceful,
        )

        # Update final status
        bot_process = await update_bot_process_status(
            context=context,
            status=final_status,
            stopped_at=datetime.utcnow(),
            exit_code=exit_code,
            error_message=error_message,
        )

        logger.info(
            f"Stopped bot {bot_type}/{instance_id} "
            f"with exit_code={exit_code}, status={final_status.value}"
        )
        return bot_process


class GetBotStatusUseCase:
    """Get comprehensive bot status."""

    def __init__(self) -> None:
        self.process_manager = ProcessManager()

    async def execute(self, bot_type: str, instance_id: str) -> BotStatus | None:
        """Execute the get bot status use case.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance ID

        Returns:
            BotStatus or None if bot process not found
        """
        # Get process record
        bot_process = await get_bot_process(bot_type, instance_id)
        if not bot_process:
            # Check if bot instance exists at all
            instance = await get_bot_instance(bot_type, instance_id)
            if not instance:
                return None

            # Bot exists but never started - return registered status
            return BotStatus(
                bot_type=bot_type,
                bot_instance_id=instance_id,
                status=ProcessStatus.REGISTERED,
                mode=instance.mode.value if hasattr(instance.mode, "value") else str(instance.mode),
                message="Bot registered but never started",
            )

        # Verify process is actually alive if marked running
        if bot_process.status == ProcessStatus.RUNNING:
            actual_status = await self.process_manager.get_process_status(
                context=BotContext(bot_type=bot_type, instance_id=instance_id),
                pid=bot_process.pid,
            )

            if actual_status == ProcessStatus.STOPPED:
                # Process died - update record
                bot_process = await update_bot_process_status(
                    context=BotContext(bot_type=bot_type, instance_id=instance_id),
                    status=ProcessStatus.ERROR,
                    error_message="Process died unexpectedly",
                    stopped_at=datetime.utcnow(),
                )

        # Get latest state from BotStateRepository
        context = BotContext(bot_type=bot_type, instance_id=instance_id)
        state_data = await load_bot_state(context)

        # Get last trade time (simplified - would need TradeRepository)
        last_trade_at = None  # Could be enhanced with actual trade lookup

        # Assemble complete status
        return BotStatusAssembler.assemble(
            process=bot_process,
            state=state_data,
            last_trade_at=last_trade_at,
        )


class ListRunningBotsUseCase:
    """List all running bots with current status."""

    def __init__(self) -> None:
        self.process_manager = ProcessManager()
        self.get_status_use_case = GetBotStatusUseCase()

    async def execute(self) -> list[BotStatus]:
        """Execute the list running bots use case.

        Returns:
            List of BotStatus for all bots with RUNNING status
        """
        running_processes = await list_running_bots()
        statuses = []

        for process in running_processes:
            # Get full status for each
            status = await self.get_status_use_case.execute(
                bot_type=process.bot_type,
                instance_id=process.bot_instance_id,
            )
            if status:
                statuses.append(status)

        return statuses


class RestartBotUseCase:
    """Stop then start bot."""

    def __init__(self) -> None:
        self.stop_use_case = StopBotUseCase()
        self.start_use_case = StartBotUseCase()

    async def execute(
        self,
        bot_type: str,
        instance_id: str,
        symbols: list[str] | None = None,
        mode: str | None = None,
        config_path: str | None = None,
    ) -> BotProcess:
        """Execute the restart bot use case.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance ID
            symbols: Optional symbols list (uses existing if None)
            mode: Optional mode (uses existing if None)
            config_path: Optional config path (uses existing if None)

        Returns:
            BotProcess for the restarted bot
        """
        # Get existing process to preserve settings
        existing = await get_bot_process(bot_type, instance_id)

        # Stop if running
        with contextlib.suppress(ValueError):
            await self.stop_use_case.execute(bot_type, instance_id, graceful=True)

        # Determine settings (use provided or fallback to existing)
        use_symbols = symbols
        use_mode = mode
        use_config = config_path

        if existing:
            use_symbols = symbols or existing.symbols
            use_mode = mode or existing.mode
            use_config = config_path or existing.config_path

        # Validate we have required settings
        if not use_symbols:
            raise ValueError("Symbols required for restart (no existing process)")
        if not use_mode:
            use_mode = "dry_run"
        if not use_config:
            use_config = "config-neat.txt"

        # Start fresh
        return await self.start_use_case.execute(
            bot_type=bot_type,
            instance_id=instance_id,
            symbols=use_symbols,
            mode=use_mode,
            config_path=use_config,
        )


class CleanupStaleBotsUseCase:
    """Find and mark stale bot processes as ERROR."""

    def __init__(self) -> None:
        self.process_manager = ProcessManager()

    async def execute(self, threshold_minutes: int = 5) -> list[BotProcess]:
        """Execute the cleanup stale bots use case.

        Args:
            threshold_minutes: Minutes since last update to consider stale

        Returns:
            List of processes marked as stale
        """
        from stonks_trading.domains.botcontrol.repositories import (
            list_stale_processes,
        )

        # Get potentially stale processes
        stale_processes = await list_stale_processes(threshold_minutes)

        # Verify and update each
        cleaned = []
        for process in stale_processes:
            actual_status = await self.process_manager.get_process_status(
                context=BotContext(
                    bot_type=process.bot_type,
                    instance_id=process.bot_instance_id,
                ),
                pid=process.pid,
            )

            if actual_status == ProcessStatus.STOPPED:
                # Mark as error
                await update_bot_process_status(
                    context=BotContext(
                        bot_type=process.bot_type,
                        instance_id=process.bot_instance_id,
                    ),
                    status=ProcessStatus.ERROR,
                    error_message=f"No heartbeat for {threshold_minutes}+ minutes",
                    stopped_at=datetime.utcnow(),
                )
                process.status = ProcessStatus.ERROR
                cleaned.append(process)

        logger.info(f"Cleaned up {len(cleaned)} stale bot processes")
        return cleaned
