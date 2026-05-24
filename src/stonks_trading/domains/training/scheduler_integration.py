"""Scheduler integration for daily retraining.

Manages APScheduler jobs for daily retraining at 00:00 UTC.
Integrates with BotContext for multi-bot isolation.
"""

import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.domains.training.entities import RetrainingJob
from stonks_trading.domains.training.services import (
    GenomeEvaluator,
    TrainingDataProvider,
    TrainingExecutor,
)
from stonks_trading.domains.training.use_cases import DailyRetrainingUseCase, TrainGenomeUseCase
from stonks_trading.shared.notifications import DiscordNotifier
from stonks_trading.shared.scheduler import Scheduler

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJobConfig:
    """Configuration for a scheduled retraining job."""

    bot_context: BotContext
    symbols: list[str]
    hour: int = 0  # UTC hour
    minute: int = 0  # UTC minute
    generations: int = 30
    population_size: int = 150
    improvement_threshold: float = 0.5


class TrainingScheduler:
    """Scheduler wrapper for training domain.

    Manages daily retraining jobs with BotContext isolation.
    Each bot context can have its own scheduled retraining.
    """

    def __init__(
        self,
        scheduler: Scheduler | None = None,
        notifier: DiscordNotifier | None = None,
    ):
        """Initialize training scheduler.

        Args:
            scheduler: APScheduler wrapper instance
            notifier: Discord notifier for alerts
        """
        self._scheduler = scheduler or Scheduler()
        self._notifier = notifier
        self._jobs: dict[str, ScheduledJobConfig] = {}
        self._running = False

    def start(self) -> None:
        """Start the scheduler."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Training scheduler started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._running:
            self._scheduler.stop()
            self._running = False
            logger.info("Training scheduler stopped")

    def schedule_daily_retrain(
        self,
        config: ScheduledJobConfig,
    ) -> str:
        """Schedule daily retraining for a bot context.

        Args:
            config: Job configuration including bot context and symbols

        Returns:
            Job ID string
        """
        job_id = self._generate_job_id(config.bot_context)

        # Store config for job execution
        self._jobs[job_id] = config

        # Create callback that captures config
        async def retraining_callback() -> None:
            await self._execute_retraining_job(job_id)

        # Schedule the job
        self._scheduler.schedule_daily_retrain(
            callback=retraining_callback,
            hour=config.hour,
            minute=config.minute,
            timezone="UTC",
        )

        logger.info(
            f"Scheduled daily retraining for {config.bot_context} "
            f"at {config.hour:02d}:{config.minute:02d} UTC"
        )

        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled retraining job.

        Args:
            job_id: Job ID to remove

        Returns:
            True if removed, False if not found
        """
        if job_id in self._jobs:
            del self._jobs[job_id]
            with contextlib.suppress(Exception):
                self._scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled job {job_id}")
            return True
        return False

    def get_scheduled_jobs(self) -> list[dict[str, Any]]:
        """Get list of scheduled retraining jobs.

        Returns:
            List of job info dicts with bot context and schedule
        """
        jobs = self._scheduler.list_jobs()
        result = []

        for job in jobs:
            job_id = job.get("id", "")
            if job_id in self._jobs:
                config = self._jobs[job_id]
                result.append(
                    {
                        "job_id": job_id,
                        "bot_type": config.bot_context.bot_type,
                        "instance_id": config.bot_context.instance_id,
                        "symbols": config.symbols,
                        "schedule": f"{config.hour:02d}:{config.minute:02d} UTC",
                        "next_run": job.get("next_run"),
                    }
                )

        return result

    async def trigger_retraining_now(
        self,
        bot_context: BotContext,
        symbols: list[str],
    ) -> list[dict[str, Any]]:
        """Trigger retraining immediately for a bot context.

        Args:
            bot_context: Bot context to retrain
            symbols: Symbols to retrain

        Returns:
            List of retraining results
        """
        config = ScheduledJobConfig(
            bot_context=bot_context,
            symbols=symbols,
        )
        job_id = self._generate_job_id(bot_context)
        self._jobs[job_id] = config

        return await self._execute_retraining_job(job_id)

    async def _execute_retraining_job(self, job_id: str) -> list[dict[str, Any]]:
        """Execute a retraining job.

        Args:
            job_id: Job ID to execute

        Returns:
            List of retraining results
        """
        if job_id not in self._jobs:
            logger.error(f"Job {job_id} not found")
            return []

        config = self._jobs[job_id]
        logger.info(f"Executing retraining job {job_id} for {config.bot_context}")

        try:
            # Build jobs for each symbol
            jobs: list[RetrainingJob] = []
            for symbol in config.symbols:
                job = RetrainingJob(
                    symbol=symbol,
                    bot_context=config.bot_context,
                    status="pending",
                    scheduled_at=datetime.utcnow(),
                )
                jobs.append(job)

            # Create services
            training_executor = TrainingExecutor(
                generations=config.generations,
                population_size=config.population_size,
            )
            genome_evaluator = GenomeEvaluator()
            data_provider = TrainingDataProvider()

            # Create use cases
            train_use_case = TrainGenomeUseCase(
                training_executor=training_executor,
                genome_evaluator=genome_evaluator,
                data_provider=data_provider,
                notifier=self._notifier.with_bot_context(
                    config.bot_context.bot_type,
                    config.bot_context.instance_id,
                )
                if self._notifier
                else None,
            )

            daily_use_case = DailyRetrainingUseCase(
                train_use_case=train_use_case,
                notifier=self._notifier.with_bot_context(
                    config.bot_context.bot_type,
                    config.bot_context.instance_id,
                )
                if self._notifier
                else None,
            )

            # Execute retraining
            results = await daily_use_case.execute_for_contexts(jobs)

            # Convert to dict for serialization
            results_dict = [
                {
                    "symbol": r.symbol,
                    "improved": r.improved,
                    "new_roi": r.new_roi,
                    "prev_roi": r.prev_roi,
                    "improvement_pct": r.improvement_pct,
                    "new_genome_id": r.new_genome_id,
                    "prev_genome_id": r.prev_genome_id,
                    "reason": r.reason,
                }
                for r in results
            ]

            logger.info(f"Retraining job {job_id} completed: {len(results)} results")
            return results_dict

        except Exception as e:
            logger.error(f"Retraining job {job_id} failed: {e}")
            if self._notifier:
                await self._notifier.send_message(
                    f"Retraining failed for {config.bot_context}: {e}"
                )
            raise

    def _generate_job_id(self, bot_context: BotContext) -> str:
        """Generate unique job ID for bot context."""
        return f"retrain_{bot_context.bot_type}_{bot_context.instance_id}"


class BotSchedulerLifecycle:
    """Manages scheduler lifecycle tied to bot lifecycle.

    Attaches scheduler to bot start/stop events for seamless integration.
    """

    def __init__(
        self,
        training_scheduler: TrainingScheduler,
    ):
        """Initialize lifecycle manager.

        Args:
            training_scheduler: Training scheduler instance
        """
        self.scheduler = training_scheduler
        self._registered_configs: dict[str, ScheduledJobConfig] = {}

    async def on_bot_start(self, bot_context: BotContext, symbols: list[str]) -> None:
        """Call when bot starts to enable scheduled retraining.

        Args:
            bot_context: Starting bot's context
            symbols: Symbols the bot trades
        """
        # Start scheduler if not running
        self.scheduler.start()

        # Register job for this bot
        config = ScheduledJobConfig(
            bot_context=bot_context,
            symbols=symbols,
        )

        self.scheduler.schedule_daily_retrain(config)
        self._registered_configs[self._bot_key(bot_context)] = config

        logger.info(f"Registered scheduled retraining for {bot_context}")

    async def on_bot_stop(self, bot_context: BotContext) -> None:
        """Call when bot stops to disable scheduled retraining.

        Args:
            bot_context: Stopping bot's context
        """
        bot_key = self._bot_key(bot_context)

        if bot_key in self._registered_configs:
            config = self._registered_configs[bot_key]
            job_id = self.scheduler._generate_job_id(config.bot_context)
            self.scheduler.remove_job(job_id)
            del self._registered_configs[bot_key]

            logger.info(f"Unregistered scheduled retraining for {bot_context}")

    def _bot_key(self, bot_context: BotContext) -> str:
        """Generate unique key for bot context."""
        return f"{bot_context.bot_type}_{bot_context.instance_id}"
