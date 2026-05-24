"""FastAPI routes for training domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to training domain functionality.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.domains.training import use_cases as training_use_cases
from stonks_trading.domains.training.dtos import (
    CheckpointCleanupResponse,
    GenerationMetricListResponse,
    GenomeComparisonResponse,
    RetrainingJobRequest,
    RetrainingJobResponse,
    RetrainingSummaryResponse,
    SchedulerJobListResponse,
    SchedulerJobRequest,
    SchedulerJobResponse,
    TrainingProgressResponse,
    TrainingRunListResponse,
    TrainingRunRequest,
    TrainingRunResponse,
    TriggerRetrainingRequest,
    TriggerRetrainingResponse,
)
from stonks_trading.domains.training.mappers import (
    GenerationMetricMapper,
    GenomeComparisonMapper,
    RetrainingJobMapper,
    SchedulerJobMapper,
    TrainingProgressMapper,
    TrainingRunMapper,
    TriggerRetrainingMapper,
)
from stonks_trading.domains.training.scheduler_integration import (
    ScheduledJobConfig,
    TrainingScheduler,
)
from stonks_trading.domains.training.services import (
    CheckpointManager,
    GenomeEvaluator,
    TrainingDataProvider,
    TrainingExecutor,
)

# Create router
router = APIRouter(prefix="/training", tags=["training"])

# Training run router
runs_router = APIRouter(prefix="/runs", tags=["runs"])


# =============================================================================
# Training Run Routes
# =============================================================================


@runs_router.post(
    "",
    response_model=GenomeComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_run_endpoint(
    request: TrainingRunRequest,
) -> GenomeComparisonResponse:
    """Start a new training run and return comparison result.

    HTTP CONCERNS ONLY:
    - Validate request (Pydantic)
    - Call use case
    - Return response or raise HTTPException

    Business logic lives in TrainGenomeUseCase.
    """
    # Create services (in production, inject via dependency)
    training_executor = TrainingExecutor(
        generations=request.generations,
        population_size=request.population_size,
    )
    genome_evaluator = GenomeEvaluator()
    data_provider = TrainingDataProvider()

    # Create notifier if webhook is configured
    notifier = None
    # if settings.DISCORD_WEBHOOK_URL:
    #     notifier = DiscordNotifier(settings.DISCORD_WEBHOOK_URL)

    # Create use case
    use_case = training_use_cases.TrainGenomeUseCase(
        training_executor=training_executor,
        genome_evaluator=genome_evaluator,
        data_provider=data_provider,
        notifier=notifier,
    )

    # Create request
    train_request = training_use_cases.TrainGenomeRequest(
        bot_context=BotContext(
            bot_type=request.bot_type,
            instance_id=request.bot_instance_id,
        ),
        symbol=Symbol(value=request.symbol.upper()),
        generations=request.generations,
        population_size=request.population_size,
        improvement_threshold=0.5,
    )

    try:
        result = await use_case.execute(train_request)
        return GenomeComparisonMapper.to_response(result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training failed: {str(e)}",
        ) from None


@router.get(
    "",
    response_model=TrainingRunListResponse,
)
async def list_training_runs_endpoint(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    bot_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TrainingRunListResponse:
    """List training runs with optional filtering.

    Thin route - delegates to use case for any business logic.
    """
    from stonks_trading.domains.training.repositories import list_training_runs

    symbol_obj = Symbol(value=symbol.upper()) if symbol else None

    runs = await list_training_runs(
        status=status,
        symbol=symbol_obj,
        bot_type=bot_type,
        limit=limit,
        offset=offset,
    )

    run_responses = TrainingRunMapper.to_response_list(runs)
    return TrainingRunListResponse(runs=run_responses, total=len(run_responses))


@router.get(
    "/{run_id}",
    response_model=TrainingRunResponse,
)
async def get_training_run_endpoint(
    run_id: int = Path(..., ge=1),
) -> TrainingRunResponse:
    """Get a specific training run by ID."""
    from stonks_trading.domains.training.repositories import get_training_run

    run = await get_training_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training run {run_id} not found",
        )
    return TrainingRunMapper.to_response(run)


@router.get(
    "/{run_id}/progress",
    response_model=TrainingProgressResponse,
)
async def get_training_progress_endpoint(
    run_id: int = Path(..., ge=1),
) -> TrainingProgressResponse:
    """Get current training progress for a run."""
    use_case = training_use_cases.GetTrainingProgressUseCase()
    session = await use_case.execute(run_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training run {run_id} not found",
        )
    return TrainingProgressMapper.to_response(session)


@router.get(
    "/{run_id}/metrics",
    response_model=GenerationMetricListResponse,
)
async def get_generation_metrics_endpoint(
    run_id: int = Path(..., ge=1),
) -> GenerationMetricListResponse:
    """Get generation metrics for a training run."""
    from stonks_trading.domains.training.repositories import list_generation_metrics

    metrics = await list_generation_metrics(run_id)
    metric_responses = GenerationMetricMapper.to_response_list(metrics)
    return GenerationMetricListResponse(metrics=metric_responses, total=len(metric_responses))


# =============================================================================
# Retraining Routes
# =============================================================================


@router.post(
    "/retrain",
    response_model=RetrainingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_retraining_endpoint(
    request: RetrainingJobRequest,
) -> RetrainingJobResponse:
    """Schedule a retraining job for a symbol and bot context."""
    from stonks_trading.domains.training.entities import RetrainingJob

    job = RetrainingJob(
        symbol=request.symbol.upper(),
        bot_context=BotContext(
            bot_type=request.bot_type,
            instance_id=request.bot_instance_id,
        ),
        status="pending",
        scheduled_at=request.scheduled_at,
    )

    # For now, immediately execute - in production, queue this
    training_executor = TrainingExecutor()
    genome_evaluator = GenomeEvaluator()
    data_provider = TrainingDataProvider()

    use_case = training_use_cases.TrainGenomeUseCase(
        training_executor=training_executor,
        genome_evaluator=genome_evaluator,
        data_provider=data_provider,
    )

    train_request = training_use_cases.TrainGenomeRequest(
        bot_context=job.bot_context,
        symbol=Symbol(value=job.symbol),
    )

    try:
        result = await use_case.execute(train_request)
        job.result = result
        job.status = "completed"
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)

    return RetrainingJobMapper.to_response(job)


@router.post(
    "/retrain/daily",
    response_model=RetrainingSummaryResponse,
)
async def trigger_daily_retraining_endpoint() -> RetrainingSummaryResponse:
    """Trigger daily retraining for all scheduled bots.

    Calls DailyRetrainingUseCase.
    """
    # TODO: Implement with scheduler integration
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Daily retraining trigger not yet implemented - use scheduler",
    )


# =============================================================================
# Checkpoint Management Routes
# =============================================================================


@router.post(
    "/checkpoints/cleanup/{run_id}",
    response_model=CheckpointCleanupResponse,
)
async def cleanup_checkpoints_endpoint(
    run_id: int = Path(..., ge=1),
    keep_every_nth: int = Query(default=5, ge=1, le=50),
    max_checkpoints: int = Query(default=20, ge=1, le=100),
) -> CheckpointCleanupResponse:
    """Clean up old checkpoints based on retention policy."""
    checkpoint_manager = CheckpointManager(
        keep_every_nth=keep_every_nth,
        max_checkpoints=max_checkpoints,
    )

    use_case = training_use_cases.CheckpointCleanupUseCase(
        checkpoint_manager=checkpoint_manager,
    )

    # TODO: Fetch actual checkpoints for run
    checkpoints: list[dict[str, Any]] = []

    result = await use_case.execute(run_id, checkpoints)

    return CheckpointCleanupResponse(
        run_id=result["run_id"],
        deleted_count=result["deleted_count"],
        retained_count=result["retained_count"],
        retained_checkpoints=result.get("retained_checkpoints", []),
    )


# =============================================================================
# Scheduler Routes
# =============================================================================

# Global scheduler instance (managed by app lifecycle)
_training_scheduler: TrainingScheduler | None = None


def get_training_scheduler() -> TrainingScheduler:
    """Get or create the global training scheduler."""
    global _training_scheduler
    if _training_scheduler is None:
        _training_scheduler = TrainingScheduler()
    return _training_scheduler


@router.post(
    "/scheduler/jobs",
    response_model=SchedulerJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_retraining_job_endpoint(
    request: SchedulerJobRequest,
) -> SchedulerJobResponse:
    """Schedule daily retraining for a bot context.

    Creates a scheduled job that runs daily at 00:00 UTC
    to retrain genomes for the specified symbols.
    """
    scheduler = get_training_scheduler()
    scheduler.start()

    config = ScheduledJobConfig(
        bot_context=BotContext(
            bot_type=request.bot_type,
            instance_id=request.bot_instance_id,
        ),
        symbols=request.symbols,
        hour=request.hour,
        minute=request.minute,
    )

    job_id = scheduler.schedule_daily_retrain(config)

    return SchedulerJobResponse(
        job_id=job_id,
        bot_type=request.bot_type,
        instance_id=request.bot_instance_id,
        symbols=request.symbols,
        schedule=f"{request.hour:02d}:{request.minute:02d} UTC",
        status="scheduled",
    )


@router.get(
    "/scheduler/jobs",
    response_model=SchedulerJobListResponse,
)
async def list_scheduler_jobs_endpoint() -> SchedulerJobListResponse:
    """List all scheduled retraining jobs."""
    scheduler = get_training_scheduler()
    jobs = scheduler.get_scheduled_jobs()
    return SchedulerJobMapper.to_list_response(jobs)


@router.delete(
    "/scheduler/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scheduler_job_endpoint(
    job_id: str = Path(..., min_length=1),
) -> None:
    """Remove a scheduled retraining job."""
    scheduler = get_training_scheduler()
    removed = scheduler.remove_job(job_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )


@router.post(
    "/scheduler/trigger",
    response_model=TriggerRetrainingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_retraining_endpoint(
    request: TriggerRetrainingRequest,
) -> TriggerRetrainingResponse:
    """Trigger immediate retraining for a bot context.

    This runs the retraining job immediately, outside of the schedule.
    Useful for testing or manual retraining.
    """
    scheduler = get_training_scheduler()
    scheduler.start()

    bot_context = BotContext(
        bot_type=request.bot_type,
        instance_id=request.bot_instance_id,
    )

    try:
        results = await scheduler.trigger_retraining_now(
            bot_context=bot_context,
            symbols=request.symbols,
        )

        job_id = (
            f"manual_{request.bot_type}_{request.bot_instance_id}_{datetime.utcnow().timestamp()}"
        )

        return TriggerRetrainingMapper.to_response(
            job_id=job_id,
            results=results,
            completed_at=datetime.utcnow(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retraining failed: {str(e)}",
        ) from None


@router.post(
    "/scheduler/start",
    status_code=status.HTTP_200_OK,
)
async def start_scheduler_endpoint() -> dict[str, str]:
    """Start the training scheduler.

    Must be called before scheduled jobs will run.
    """
    scheduler = get_training_scheduler()
    scheduler.start()
    return {"status": "scheduler_started"}


@router.post(
    "/scheduler/stop",
    status_code=status.HTTP_200_OK,
)
async def stop_scheduler_endpoint() -> dict[str, str]:
    """Stop the training scheduler.

    Stops all scheduled jobs from running.
    """
    scheduler = get_training_scheduler()
    scheduler.stop()
    return {"status": "scheduler_stopped"}
