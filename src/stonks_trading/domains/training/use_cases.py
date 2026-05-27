"""Training domain use cases - BUSINESS LOGIC.

ALL business logic lives here:
- When to retrain
- Which data to use
- How to validate results
- Whether to swap genomes
- Notification decisions

Use case rules (per architecture.md):
- Classes with injected dependencies
- No direct SQL or HTTP calls - use repositories/services
- Business logic only - orchestration and decisions
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.entities import GenerationMetric, Genome
from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.domains.training.entities import (
    GenomeComparisonResult,
    RetrainingJob,
    TrainingSession,
)
from stonks_trading.domains.training.repositories import (
    activate_genome_for_context,
    create_training_run,
    deactivate_genome_for_context,
    get_active_genome_for_symbol,
    get_training_run,
    save_generation_metric,
    save_genome,
    update_training_run_status,
)
from stonks_trading.domains.training.services import (
    CheckpointManager,
    GenomeEvaluator,
    GenomeSerializer,
    TrainingDataProvider,
    TrainingExecutor,
)
from stonks_trading.shared.notifications import DiscordNotifier


@dataclass
class TrainGenomeRequest:
    """Request to train a genome (Phase 10D - strategy-aware).

    Use case input - contains all parameters for training.
    """

    bot_context: BotContext
    symbol: Symbol
    generations: int = 30
    population_size: int = 150
    improvement_threshold: float = 0.5  # 0.5% improvement required
    strategy_type: str = "neat_swing"  # Phase 10D: Strategy type for routing


@dataclass
class RetrainingScheduleRequest:
    """Request to schedule daily retraining.

    Use case input for scheduling retraining across bot contexts.
    """

    bot_contexts: list[BotContext]
    symbols: list[str]
    schedule_utc: str = "00:00"  # HH:MM format in UTC


class TrainGenomeUseCase:
    """Train a NEAT genome for a symbol.

    BUSINESS LOGIC:
    1. Validate request (business rules)
    2. Fetch training data (via service)
    3. Execute training (via service)
    4. Validate on held-out data (via service)
    5. Save results to database (via repos)
    6. Compare with current genome (business logic here)
    7. Decide on genome swap (business logic here)
    8. Send notifications (via notifier)

    NO direct ORM queries - uses repositories.
    NO neat-python calls directly - uses TrainingExecutor service.
    """

    def __init__(
        self,
        training_executor: TrainingExecutor,
        genome_evaluator: GenomeEvaluator,
        data_provider: TrainingDataProvider,
        notifier: DiscordNotifier | None = None,
    ):
        """Initialize use case with services.

        Args:
            training_executor: NEAT training service
            genome_evaluator: Genome evaluation service
            data_provider: Training data fetching service
            notifier: Discord notification service (optional)
        """
        self.training_executor = training_executor
        self.genome_evaluator = genome_evaluator
        self.data_provider = data_provider
        self.notifier = notifier

    async def execute(self, request: TrainGenomeRequest) -> GenomeComparisonResult:
        """Execute training use case.

        Args:
            request: Training request with parameters

        Returns:
            GenomeComparisonResult with decision

        Raises:
            RuntimeError: If training run creation fails
            ValueError: If training data is insufficient
        """
        # 1. Create training run record
        run = await create_training_run(
            symbol=request.symbol,
            model_family="NEAT_RNN_V1",
            trainer_git_sha=self._get_git_sha(),
            generations=request.generations,
            pop_size=request.population_size,
            episode_steps=20160,
            fee_rate=0.001,
            config_snapshot={
                "symbol": request.symbol.value,
                "bot_type": request.bot_context.bot_type,
                "bot_instance_id": request.bot_context.instance_id,
            },
        )

        if run.id is None:
            raise RuntimeError("Failed to create training run")

        try:
            # 2. Fetch training data
            train_data = await self.data_provider.fetch_training_window(
                symbol=request.symbol.value,
                days=30,
            )

            if len(train_data) < 1000:
                raise ValueError(f"Insufficient training data: {len(train_data)} rows")

            # 3. Execute training
            await update_training_run_status(run.id, status="running")

            winner, gen_metrics = await self.training_executor.execute_training(
                train_data=train_data,
            )

            # Save generation metrics
            for metric in gen_metrics:
                gen_metric = GenerationMetric(
                    run_id=run.id or 0,
                    generation=metric.get("generation", 0),
                    best_fitness=metric.get("best_fitness", 0.0),
                    mean_fitness=metric.get("mean_fitness", 0.0),
                    worst_fitness=metric.get("worst_fitness", 0.0),
                    num_species=metric.get("num_species", 0),
                    num_genomes=metric.get("num_genomes", 0),
                )
                await save_generation_metric(gen_metric)

            # 4. Validate on held-out data
            validation_data = await self.data_provider.fetch_validation_data(
                symbol=request.symbol.value,
                days=14,
            )

            validation_results = await self.genome_evaluator.evaluate_on_data(
                genome=winner,
                data=validation_data,
            )

            # 5. Save new genome
            config = self.training_executor.get_config()
            genome_bytes = GenomeSerializer.serialize(winner, config)

            new_genome = Genome(
                genome_data=genome_bytes,
                fitness=validation_results["final_roi_pct"],
                symbol=request.symbol,
                roi_validation=validation_results["final_roi_pct"],
                trained_at=datetime.utcnow(),
                model_family="NEAT_RNN_V1",
                trainer_git_sha=self._get_git_sha(),
            )
            saved_genome = await save_genome(new_genome)

            # Update run status
            await update_training_run_status(
                run_id=run.id,
                status="completed",
                best_fitness=validation_results["final_roi_pct"],
                best_roi_validation=validation_results["final_roi_pct"],
                finished_at=datetime.utcnow(),
            )

            # 6. Compare with current genome
            current_genome = await get_active_genome_for_symbol(
                request.bot_context,
                request.symbol,
            )

            new_roi = validation_results["final_roi_pct"]
            prev_roi = (
                current_genome.roi_validation
                if current_genome and current_genome.roi_validation is not None
                else 0.0
            )

            # 7. Business logic: Decide if improved
            if current_genome is None:
                improved = True
                reason = "No current genome - new genome wins by default"
            elif new_roi > prev_roi + request.improvement_threshold:
                improved = True
                reason = f"New ROI {new_roi:.2f}% > Prev ROI {prev_roi:.2f}% + threshold"
            else:
                improved = False
                reason = f"New ROI {new_roi:.2f}% not better than Prev ROI {prev_roi:.2f}%"

            # 8. Swap if improved
            if improved and current_genome and current_genome.id is not None:
                await deactivate_genome_for_context(current_genome.id)

            if improved and saved_genome.id is not None:
                await activate_genome_for_context(saved_genome.id, request.bot_context)

            # 9. Send notification
            if self.notifier:
                await self._send_notification(
                    symbol=request.symbol.value,
                    new_roi=new_roi,
                    prev_roi=prev_roi,
                    improved=improved,
                    reason=reason,
                    bot_context=request.bot_context,
                )

            return GenomeComparisonResult(
                improved=improved,
                new_roi=new_roi,
                prev_roi=prev_roi,
                improvement_pct=new_roi - prev_roi,
                new_genome_id=saved_genome.id or 0,
                prev_genome_id=current_genome.id if current_genome else None,
                symbol=request.symbol.value,
                reason=reason,
            )

        except Exception:
            await update_training_run_status(run.id, status="failed")
            raise

    async def _send_notification(
        self,
        symbol: str,
        new_roi: float,
        prev_roi: float,
        improved: bool,
        reason: str,
        bot_context: BotContext,
    ) -> None:
        """Send Discord notification with training results.

        Args:
            symbol: Trading symbol
            new_roi: New genome ROI
            prev_roi: Previous genome ROI
            improved: Whether improvement was found
            reason: Decision reason
            bot_context: Bot context for tagging
        """
        if not self.notifier:
            return

        emoji = "✅" if improved else "❌"
        message = (
            f"{emoji} Training Complete: {symbol}\n"
            f"New ROI: {new_roi:.2f}%\n"
            f"Prev ROI: {prev_roi:.2f}%\n"
            f"Improved: {improved}\n"
            f"Reason: {reason}\n"
            f"Bot: {bot_context.bot_type}/{bot_context.instance_id}"
        )
        await self.notifier.send_message(message)

    def _get_git_sha(self) -> str:
        """Get git SHA for training record."""
        # TODO: Implement using gitpython or similar
        return "unknown"


class DailyRetrainingUseCase:
    """Orchestrate daily retraining for all bot contexts and symbols.

    BUSINESS LOGIC:
    - Iterate over all active bot contexts
    - For each symbol in context's config:
      - Execute TrainGenomeUseCase
      - Collect results
    - Send summary notification
    """

    def __init__(
        self,
        train_use_case: TrainGenomeUseCase,
        notifier: DiscordNotifier | None = None,
    ):
        """Initialize use case.

        Args:
            train_use_case: TrainGenomeUseCase instance
            notifier: Discord notification service (optional)
        """
        self.train_use_case = train_use_case
        self.notifier = notifier

    async def execute_for_contexts(
        self,
        jobs: list[RetrainingJob],
    ) -> list[GenomeComparisonResult]:
        """Execute daily retraining for all scheduled jobs.

        Args:
            jobs: List of RetrainingJob to process

        Returns:
            List of comparison results for each job
        """
        results: list[GenomeComparisonResult] = []

        for job in jobs:
            if not job.is_pending():
                continue

            try:
                job.status = "running"
                job.started_at = datetime.utcnow()

                request = TrainGenomeRequest(
                    bot_context=job.bot_context,
                    symbol=Symbol(value=job.symbol),
                    generations=30,
                    population_size=150,
                    improvement_threshold=0.5,
                )

                result = await self.train_use_case.execute(request)
                job.result = result
                job.status = "completed"
                job.finished_at = datetime.utcnow()

                results.append(result)

            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                job.finished_at = datetime.utcnow()

        # Send summary notification
        if self.notifier:
            await self._send_summary_notification(results)

        return results

    async def _send_summary_notification(
        self,
        results: list[GenomeComparisonResult],
    ) -> None:
        """Send summary notification of all retraining results.

        Args:
            results: List of comparison results
        """
        if not self.notifier or not results:
            return

        improved_count = sum(1 for r in results if r.improved)
        total_count = len(results)

        message = (
            f"Daily Retraining Summary\n"
            f"Total: {total_count}\n"
            f"Improved: {improved_count}\n"
            f"Rejected: {total_count - improved_count}"
        )
        await self.notifier.send_message(message)


class GetTrainingProgressUseCase:
    """Get current training progress for monitoring.

    BUSINESS LOGIC:
    - Fetch current training run status
    - Get generation metrics if available
    - Build TrainingSession for display
    """

    async def execute(self, run_id: int) -> TrainingSession | None:
        """Get training progress for a run.

        Args:
            run_id: Training run ID

        Returns:
            TrainingSession or None if not found
        """
        run = await get_training_run(run_id)
        if not run:
            return None

        return TrainingSession(
            run_id=run.id or 0,
            symbol=run.symbol.value if run.symbol else "",
            status=run.status,
            started_at=run.started_at,
            best_fitness_so_far=run.best_fitness,
        )


class CheckpointCleanupUseCase:
    """Clean up old checkpoints based on retention policy.

    BUSINESS LOGIC:
    - Determine which checkpoints to retain
    - Delete old checkpoints
    - Update checkpoint metadata
    """

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        max_checkpoint_age_days: int = 30,
    ):
        """Initialize use case.

        Args:
            checkpoint_manager: Checkpoint retention service
            max_checkpoint_age_days: Maximum age for checkpoints
        """
        self.checkpoint_manager = checkpoint_manager
        self.max_checkpoint_age_days = max_checkpoint_age_days

    async def execute(
        self,
        run_id: int,
        checkpoints: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean up checkpoints based on retention policy.

        Args:
            run_id: Training run ID
            checkpoints: List of checkpoint dicts

        Returns:
            Dict with deleted_count, retained_count
        """
        retained = self.checkpoint_manager.apply_retention_policy(checkpoints)

        # TODO: Implement actual deletion from storage
        deleted_count = len(checkpoints) - len(retained)

        return {
            "run_id": run_id,
            "deleted_count": deleted_count,
            "retained_count": len(retained),
            "retained_checkpoints": retained,
        }
