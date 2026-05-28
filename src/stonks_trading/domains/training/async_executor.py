"""Async training executor for background training jobs.

Phase 10C: Provides async training with real-time progress tracking.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

from stonks_trading.shared.logger import logger
from stonks_trading.shared.redis_client import get_redis
from stonks_trading.shared.websocket_api import broadcast_training_progress


class AsyncTrainingExecutor:
    """Manages async training jobs with checkpoint tracking.

    Handles:
    - Job lifecycle (queued -> running -> completed/failed)
    - Checkpoint storage every N generations
    - Progress tracking in Redis
    - Plot generation at checkpoints
    """

    def __init__(self) -> None:
        """Initialize async executor."""
        self._running_jobs: dict[str, asyncio.Task] = {}

    async def start_job(
        self,
        symbol: str,
        generations: int,
        population_size: int,
        training_capital: float,
        checkpoint_interval: int,
        strategy_type: str = "neat_swing",
    ) -> str:
        """Start a new async training job.

        Args:
            symbol: Trading symbol to train on
            generations: Number of generations to run
            population_size: Population size for NEAT
            training_capital: Initial capital for training (simulation)
            checkpoint_interval: Save checkpoint every N generations
            strategy_type: Strategy type (currently only neat_swing)

        Returns:
            Job ID for tracking
        """
        job_id = str(uuid.uuid4())

        # Create initial job state
        job_data = {
            "id": job_id,
            "symbol": symbol,
            "status": "queued",
            "generations_total": generations,
            "generations_completed": 0,
            "best_fitness": None,
            "genomes_evaluated": 0,
            "progress_pct": 0.0,
            "checkpoints": [],
            "started_at": None,
            "updated_at": datetime.utcnow().isoformat(),
            "estimated_completion": None,
            "strategy_type": strategy_type,
            "population_size": population_size,
            "training_capital": training_capital,
            "checkpoint_interval": checkpoint_interval,
            "error": None,
        }

        # Store in Redis
        await self._save_job_state(job_id, job_data)

        # Start background task
        task = asyncio.create_task(
            self._run_training_job(
                job_id=job_id,
                symbol=symbol,
                generations=generations,
                population_size=population_size,
                training_capital=training_capital,
                checkpoint_interval=checkpoint_interval,
                strategy_type=strategy_type,
            )
        )
        self._running_jobs[job_id] = task

        logger.info(f"Started async training job {job_id} for {symbol}")
        return job_id

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get current job status from Redis.

        Args:
            job_id: Job ID to look up

        Returns:
            Job data dict or None if not found
        """
        return await self._load_job_state(job_id)

    async def get_checkpoints(self, job_id: str) -> list[dict[str, Any]]:
        """Get all checkpoints for a job.

        Args:
            job_id: Job ID

        Returns:
            List of checkpoint dicts
        """
        job_data = await self._load_job_state(job_id)
        if not job_data:
            return []
        return job_data.get("checkpoints", [])

    async def select_checkpoint(self, job_id: str, generation: int) -> dict[str, Any] | None:
        """Activate a checkpoint for deployment.

        Args:
            job_id: Job ID
            generation: Generation number to activate

        Returns:
            Activation result or None if checkpoint not found
        """
        job_data = await self._load_job_state(job_id)
        if not job_data:
            return None

        checkpoints = job_data.get("checkpoints", [])
        checkpoint = next((c for c in checkpoints if c["generation"] == generation), None)

        if not checkpoint:
            return None

        # Mark as selected
        checkpoint["selected"] = True
        job_data["selected_checkpoint"] = generation
        await self._save_job_state(job_id, job_data)

        return {
            "job_id": job_id,
            "generation": generation,
            "model_id": checkpoint.get("model_id", ""),
            "activated": True,
            "message": f"Checkpoint gen {generation} selected for deployment",
        }

    async def _run_training_job(
        self,
        job_id: str,
        symbol: str,
        generations: int,
        population_size: int,
        training_capital: float,
        checkpoint_interval: int,
        strategy_type: str,
    ) -> None:
        """Run the actual training job in background.

        This is the main training loop that:
        1. Updates status to "running"
        2. Runs NEAT training
        3. Saves checkpoints every N generations
        4. Updates progress in Redis
        5. Marks as completed or failed
        """
        try:
            # Update status to running
            job_data = await self._load_job_state(job_id)
            if not job_data:
                logger.error(f"Job {job_id} not found")
                return

            job_data["status"] = "running"
            job_data["started_at"] = datetime.utcnow().isoformat()

            # Estimate completion time (rough estimate: ~30s per generation)
            estimated_duration = timedelta(seconds=generations * 30)
            job_data["estimated_completion"] = (datetime.utcnow() + estimated_duration).isoformat()

            await self._save_job_state(job_id, job_data)

            # Run training (placeholder - actual NEAT training would go here)
            # For now, simulate progress
            await self._simulate_training(
                job_id=job_id,
                symbol=symbol,
                generations=generations,
                checkpoint_interval=checkpoint_interval,
            )

            # Mark as completed
            job_data = await self._load_job_state(job_id)
            checkpoints = job_data.get("checkpoints", [])
            job_data["status"] = "completed"
            job_data["progress_pct"] = 100.0
            job_data["updated_at"] = datetime.utcnow().isoformat()
            await self._save_job_state(job_id, job_data)

            # Broadcast completion via WebSocket (Phase 3)
            broadcast_training_progress(
                job_id=job_id,
                generation=generations,
                total_generations=generations,
                best_fitness=job_data.get("best_fitness", 0),
                progress_pct=100.0,
                status="completed",
                checkpoints=checkpoints,
            )

            logger.info(f"Training job {job_id} completed")

        except Exception as e:
            logger.error(f"Training job {job_id} failed: {e}")
            job_data = await self._load_job_state(job_id)
            if job_data:
                job_data["status"] = "failed"
                job_data["error"] = str(e)
                job_data["updated_at"] = datetime.utcnow().isoformat()
                await self._save_job_state(job_id, job_data)

        finally:
            # Clean up task reference
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]

    async def _simulate_training(
        self,
        job_id: str,
        symbol: str,
        generations: int,
        checkpoint_interval: int,
    ) -> None:
        """Simulate training progress for demo purposes.

        In production, this would run actual NEAT training.
        """
        for gen in range(1, generations + 1):
            # Simulate work
            await asyncio.sleep(0.5)  # Fast simulation

            # Calculate fitness (simulated improvement curve)
            import math

            base_fitness = 0.5
            improvement = math.log(gen + 1) * 0.3
            noise = (gen % 5) * 0.02
            fitness = base_fitness + improvement + noise

            # Update progress
            job_data = await self._load_job_state(job_id)
            if not job_data:
                return

            job_data["generations_completed"] = gen
            job_data["best_fitness"] = fitness
            job_data["progress_pct"] = (gen / generations) * 100
            job_data["genomes_evaluated"] = gen * job_data.get("population_size", 150)
            job_data["updated_at"] = datetime.utcnow().isoformat()

            # Save checkpoint
            checkpoints = job_data.get("checkpoints", [])
            if gen % checkpoint_interval == 0:
                checkpoint = {
                    "generation": gen,
                    "model_id": f"{job_id}_{gen}",
                    "fitness": fitness,
                    "roi": fitness * 15,  # Simulated ROI
                    "created_at": datetime.utcnow().isoformat(),
                }
                checkpoints.append(checkpoint)
                job_data["checkpoints"] = checkpoints
                logger.info(f"Job {job_id}: Saved checkpoint at gen {gen}")

            await self._save_job_state(job_id, job_data)

            # Broadcast WebSocket update (Phase 3)
            broadcast_training_progress(
                job_id=job_id,
                generation=gen,
                total_generations=generations,
                best_fitness=fitness,
                progress_pct=(gen / generations) * 100,
                status="running",
                checkpoints=checkpoints,
            )

    async def _save_job_state(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Save job state to Redis.

        Args:
            job_id: Job ID
            job_data: Job data dict
        """
        import json

        redis = await get_redis()
        key = f"training:job:{job_id}"
        await redis.setex(
            key,
            86400 * 7,  # 7 days TTL
            json.dumps(job_data, default=str),
        )

    async def _load_job_state(self, job_id: str) -> dict[str, Any] | None:
        """Load job state from Redis.

        Args:
            job_id: Job ID

        Returns:
            Job data dict or None if not found
        """
        import json

        redis = await get_redis()
        key = f"training:job:{job_id}"
        data = await redis.get(key)

        if not data:
            return None

        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None


# Global executor instance
_training_executor: AsyncTrainingExecutor | None = None


def get_training_executor() -> AsyncTrainingExecutor:
    """Get or create the global training executor."""
    global _training_executor
    if _training_executor is None:
        _training_executor = AsyncTrainingExecutor()
    return _training_executor
