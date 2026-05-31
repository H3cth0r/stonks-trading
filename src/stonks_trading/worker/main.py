"""Bot Worker HTTP API.

This service runs inside the Bot Worker container and exposes
HTTP endpoints for the API to start/stop/manage bot subprocesses.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.routing import APIRouter

from stonks_trading.domains.botcontrol.dtos import (
    StartBotRequest,
    StartBotResponse,
    StopBotResponse,
)
from stonks_trading.domains.botcontrol.entities import BotProcess, ProcessStatus
from stonks_trading.domains.botcontrol.mappers import BotProcessMapper
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger


class WorkerProcessManager:
    """Manages OS-level bot processes within the Worker container.

    This class spawns and manages bot subprocesses directly.
    It runs inside the Bot Worker container, not the API container.
    """

    def __init__(self):
        """Initialize WorkerProcessManager."""
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        logger.info("WorkerProcessManager initialized")

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

        logger.info(f"[WORKER] Starting bot {context_key} with command: {' '.join(cmd)}")

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

            logger.info(f"[WORKER] Started bot {context_key} with PID {process.pid}")
            return bot_process

        except Exception as e:
            logger.error(f"[WORKER] Failed to start bot {context_key}: {e}")
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
                    logger.info(f"[WORKER] Sent SIGTERM to bot {context_key} (PID: {process.pid})")

                    # Wait for graceful shutdown
                    try:
                        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
                        del self._processes[context_key]
                        return ProcessStatus.STOPPED, process.returncode, None
                    except TimeoutError:
                        logger.warning(
                            f"[WORKER] Bot {context_key} did not stop gracefully, sending SIGKILL"
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

        # Process not tracked
        return ProcessStatus.UNKNOWN, None, "Process not tracked locally"


# Initialize WorkerProcessManager
worker_process_manager = WorkerProcessManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Worker lifespan context."""
    logger.info("Bot Worker starting up...")
    yield
    logger.info("Bot Worker shutting down...")


def get_worker_router() -> APIRouter:
    """Factory pattern for worker routes."""
    router = APIRouter(tags=["bot-worker"])

    @router.post(
        "/bots/{bot_type}/{instance_id}/start",
        response_model=StartBotResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def worker_start_bot(
        bot_type: str,
        instance_id: str,
        request: StartBotRequest,
    ) -> StartBotResponse:
        """Start a bot subprocess inside this container.

        Called by API container via HTTP.
        """
        try:
            bot_process = await worker_process_manager.start_bot(
                bot_type=bot_type,
                instance_id=instance_id,
                symbols=request.symbols,
                mode=request.mode,
                config_path=request.config_path,
            )
            return BotProcessMapper.to_start_response(bot_process)
        except RuntimeError as e:
            logger.error(f"[WORKER] RuntimeError starting bot: {e}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e
        except Exception as e:
            logger.error(f"[WORKER] Unexpected error starting bot: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start bot: {str(e)}",
            ) from e

    @router.post(
        "/bots/{bot_type}/{instance_id}/stop",
        response_model=StopBotResponse,
    )
    async def worker_stop_bot(
        bot_type: str,
        instance_id: str,
        graceful: bool = True,
    ) -> StopBotResponse:
        """Stop a bot subprocess."""
        context = BotContext(bot_type=bot_type, instance_id=instance_id)
        final_status, exit_code, error = await worker_process_manager.stop_bot(
            context=context,
            graceful=graceful,
        )

        # Get the process to build response (may be None if not tracked)
        stopped_at = datetime.utcnow()

        return StopBotResponse(
            bot_type=bot_type,
            bot_instance_id=instance_id,
            status=final_status.value,
            stopped_at=stopped_at,
            uptime_seconds=None,  # Worker doesn't track uptime history
            exit_code=exit_code,
            message=error or f"Bot {bot_type}/{instance_id} stopped",
        )

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "bot-worker"}

    return router


app = FastAPI(
    title="Stonks Bot Worker",
    description="Bot process management service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(get_worker_router())


if __name__ == "__main__":
    uvicorn.run(
        "stonks_trading.worker.main:app",
        host="0.0.0.0",
        port=8001,
        log_level=settings.log_level.lower(),
    )
