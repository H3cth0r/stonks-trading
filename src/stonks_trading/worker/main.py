"""Bot Worker HTTP API.

This service runs inside the Bot Worker container and exposes
HTTP endpoints for the API to start/stop/manage bot subprocesses.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

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
from stonks_trading.shared.redis_client import get_redis


class WorkerProcessManager:
    """Manages OS-level bot processes within the Worker container.

    This class spawns and manages bot subprocesses directly.
    It runs inside the Bot Worker container, not the API container.
    """

    def __init__(self):
        """Initialize WorkerProcessManager."""
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._training_processes: dict[str, asyncio.subprocess.Process] = {}
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

    # Training job routes
    @router.post("/training/jobs")
    async def worker_start_training(request: dict[str, Any]) -> dict[str, Any]:
        """Start training subprocess in Worker.

        Called by API container via HTTP.
        Spawns training subprocess and tracks it.
        """
        job_id = str(uuid.uuid4())
        checkpoint_dir = Path(f"/app/data/training/{job_id}")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "python",
            "-m",
            "stonks_trading.worker.training_subprocess",
            "--job-id",
            job_id,
            "--symbol",
            request["symbol"],
            "--generations",
            str(request["generations"]),
            "--population-size",
            str(request["population_size"]),
            "--training-capital",
            str(request["training_capital"]),
            "--checkpoint-interval",
            str(request["checkpoint_interval"]),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--strategy-type",
            request.get("strategy_type", "neat_swing"),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            worker_process_manager._training_processes[job_id] = process

            job_data = {
                "id": job_id,
                "symbol": request["symbol"],
                "status": "running",
                "generations_total": request["generations"],
                "generations_completed": 0,
                "best_fitness": None,
                "best_roi": None,
                "progress_pct": 0.0,
                "checkpoints": [],
                "checkpoint_dir": str(checkpoint_dir),
                "started_at": datetime.utcnow().isoformat(),
                "error": None,
            }

            redis = await get_redis()
            await redis.setex(
                f"training:job:{job_id}",
                86400 * 30,
                json.dumps(job_data),
            )

            logger.info(f"[WORKER] Started training subprocess {job_id} with PID {process.pid}")

            return {
                "job_id": job_id,
                "status": "running",
                "started_at": job_data["started_at"],
            }

        except Exception as e:
            logger.error(f"[WORKER] Failed to start training: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start training: {str(e)}",
            ) from e

    @router.get("/training/jobs/{job_id}")
    async def worker_get_training_status(job_id: str) -> dict[str, Any]:
        """Get training job status from Redis."""
        redis = await get_redis()
        data = await redis.get(f"training:job:{job_id}")

        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found",
            )

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        return json.loads(data)

    @router.post("/training/jobs/{job_id}/stop")
    async def worker_stop_training(
        job_id: str,
        graceful: bool = True,
    ) -> dict[str, Any]:
        """Stop training subprocess."""
        if job_id not in worker_process_manager._training_processes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found",
            )

        process = worker_process_manager._training_processes[job_id]

        if graceful:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=30.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        else:
            process.kill()
            await process.wait()

        del worker_process_manager._training_processes[job_id]

        redis = await get_redis()
        data = await redis.get(f"training:job:{job_id}")
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            job_data = json.loads(data)
            job_data["status"] = "stopped"
            await redis.setex(
                f"training:job:{job_id}",
                86400 * 30,
                json.dumps(job_data),
            )

        return {"job_id": job_id, "status": "stopped"}

    @router.get("/training/jobs/{job_id}/checkpoints/{generation}/plot")
    async def worker_get_checkpoint_plot(job_id: str, generation: int) -> dict[str, Any]:
        """Get checkpoint plot HTML."""
        plot_file = Path(f"/app/data/training/{job_id}/gen_{generation}_plot.html")

        if not plot_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plot for generation {generation} not found",
            )

        plot_html = plot_file.read_text()
        return {"plot_html": plot_html}

    @router.get("/training/jobs/{job_id}/checkpoints")
    async def worker_list_checkpoints(job_id: str) -> dict[str, Any]:
        """List all checkpoints for a training job."""
        redis = await get_redis()
        data = await redis.get(f"training:job:{job_id}")

        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found",
            )

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        job_data = json.loads(data)
        checkpoints = job_data.get("checkpoints", [])

        return {"checkpoints": checkpoints, "count": len(checkpoints)}

    @router.get("/training/jobs/{job_id}/checkpoints/{generation}")
    async def worker_get_checkpoint(job_id: str, generation: int) -> dict[str, Any]:
        """Get checkpoint genome data."""
        checkpoint_dir = Path(f"/app/data/training/{job_id}")
        genome_file = checkpoint_dir / f"gen_{generation}.pkl"

        if not genome_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Checkpoint generation {generation} not found",
            )

        # Load checkpoint metadata from Redis
        redis = await get_redis()
        data = await redis.get(f"training:job:{job_id}")

        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found",
            )

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        job_data = json.loads(data)
        checkpoints = job_data.get("checkpoints", [])
        checkpoint_meta = next(
            (c for c in checkpoints if c["generation"] == generation),
            None,
        )

        return {
            "job_id": job_id,
            "generation": generation,
            "fitness": checkpoint_meta.get("fitness") if checkpoint_meta else None,
            "roi": checkpoint_meta.get("roi") if checkpoint_meta else None,
            "created_at": checkpoint_meta.get("created_at") if checkpoint_meta else None,
            "genome_path": str(genome_file),
        }

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
