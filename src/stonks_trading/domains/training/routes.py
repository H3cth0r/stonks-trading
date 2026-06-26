"""FastAPI routes for training domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to training domain functionality.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import redis as redis_client
from fastapi import APIRouter, HTTPException, Query, status
from fastapi import Path as FastAPIPath

from stonks_trading.domains.trading.entities import Genome
from stonks_trading.domains.trading.repositories import save_genome
from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.domains.training import use_cases as training_use_cases
from stonks_trading.domains.training.dtos import (
    CheckpointCleanupResponse,
    GenomeComparisonResponse,
    RetrainingJobRequest,
    RetrainingJobResponse,
    RetrainingSummaryResponse,
    SchedulerJobListResponse,
    SchedulerJobRequest,
    SchedulerJobResponse,
    SelectCheckpointRequest,
    SelectCheckpointResponse,
    TrainingCheckpointResponse,
    TrainingJobDetailResponse,
    TrainingJobListResponse,
    TrainingJobRequest,
    TrainingJobResponse,
    TrainingJobStopResponse,
    TrainingPlotResponse,
    TrainingProgressPlotResponse,
    TrainingRunListResponse,
    TrainingRunRequest,
    TriggerRetrainingRequest,
    TriggerRetrainingResponse,
)
from stonks_trading.domains.training.entities import RetrainingJob
from stonks_trading.domains.training.mappers import (
    GenomeComparisonMapper,
    RetrainingJobMapper,
    SchedulerJobMapper,
    TrainingRunMapper,
    TriggerRetrainingMapper,
)
from stonks_trading.domains.training.repositories import (
    list_training_runs,
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
    get_training_process_manager,
)
from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger

# Create router
router = APIRouter(prefix="/training", tags=["training"])

# Training run router
runs_router = APIRouter(prefix="/runs", tags=["runs"])


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


@router.post(
    "/runs",
    response_model=GenomeComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_run_endpoint(
    request: TrainingRunRequest,
) -> GenomeComparisonResponse:
    """Start a new training run and return comparison result.

    Phase 10D: Now accepts strategy_type for generic training interface.
    Routes to strategy-specific training implementation.
    Currently only NEAT is implemented, but FIBRAS and others will follow.
    """
    # Validate strategy_type is supported (Phase 10D: only NEAT)
    if request.strategy_type != "neat_swing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy {request.strategy_type} not yet supported for training",
        )

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
        strategy_type=request.strategy_type,
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


# DISABLED: /{run_id}, /{run_id}/progress, /{run_id}/metrics routes
# These conflicted with /async-training-jobs patterns
# @router.get(
#     "/{run_id}",
#     response_model=TrainingRunResponse,
# )
# async def get_training_run_endpoint(
#     run_id: int = FastAPIPath(..., ge=1),
# ) -> TrainingRunResponse:
#     """Get a specific training run by ID."""
#     run = await get_training_run(run_id)
#     if not run:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Training run {run_id} not found",
#         )
#     return TrainingRunMapper.to_response(run)
#
#
# # DISABLED: conflicts with /async-training-jobs/{job_id}
# # @router.get(
# #     "/{run_id}/progress",
# #     response_model=TrainingProgressResponse,
# # )
# # async def get_training_progress_endpoint(
# #     run_id: int = FastAPIPath(..., ge=1),
# # ) -> TrainingRunResponse:
# #     """Get current training progress for a run."""
# #     use_case = training_use_cases.GetTrainingProgressUseCase()
# #     session = await use_case.execute(run_id)
# #
# #     if not session:
# #         raise HTTPException(
# #             status_code=status.HTTP_404_NOT_FOUND,
# #             detail=f"Training run {run_id} not found",
# #         )
# #     return TrainingProgressMapper.to_response(session)
#
#
# # DISABLED: conflicts with /async-training-jobs/{job_id}
# # @router.get(
# #     "/{run_id}/metrics",
# #     response_model=GenerationMetricListResponse,
# # )
# # async def get_generation_metrics_endpoint(
# #     run_id: int = FastAPIPath(..., ge=1),
# # ) -> GenerationMetricListResponse:
# #     """Get generation metrics for a training run."""
# #     metrics = await list_generation_metrics(run_id)
# #     metric_responses = GenerationMetricMapper.to_response_list(metrics)
# #     return GenerationMetricListResponse(metrics=metric_responses, total=len(metric_responses))


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
    run_id: int = FastAPIPath(..., ge=1),
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
    job_id: str = FastAPIPath(..., min_length=1),
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


# =============================================================================
# Async Training Job Routes (Phase 10C)
# =============================================================================


@router.post(
    "/async-training-jobs",
    response_model=TrainingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_training_job_endpoint(
    request: TrainingJobRequest,
) -> TrainingJobResponse:
    """Start an async training job.

    Returns immediately with job_id. Training runs in background.
    Poll GET /training/async-training-jobs/{job_id} for progress.
    """
    manager = get_training_process_manager()

    job = await manager.start_training(
        symbol=request.symbol,
        generations=request.generations,
        population_size=request.population_size,
        training_capital=request.training_capital,
        checkpoint_interval=request.checkpoint_interval,
        strategy_type=request.strategy_type,
        csv_path=request.csv_path,
    )

    return TrainingJobResponse(
        job_id=job.job_id,
        symbol=job.symbol,
        status=job.status,
        generations_total=job.generations_total,
        generations_completed=0,
        progress_pct=0.0,
        started_at=job.started_at or datetime.utcnow(),
    )


@router.get(
    "/async-training-jobs",
    response_model=TrainingJobListResponse,
)
async def list_training_jobs_endpoint(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> TrainingJobListResponse:
    """List all training jobs from Redis.

    Returns jobs from Redis cache. Jobs expire after 7 days.
    """
    r = redis_client.Redis.from_url(settings.redis_url)
    job_keys = []
    for key in r.scan_iter("training:job:*", count=1000):
        job_keys.append(key)

    jobs = []
    for key in job_keys[:limit]:
        data = r.get(key)
        if data:
            job_data = json.loads(data)
            if status is None or job_data.get("status") == status:
                jobs.append(
                    {
                        "job_id": job_data.get("id"),
                        "symbol": job_data.get("symbol"),
                        "status": job_data.get("status"),
                        "generations_total": job_data.get("generations_total"),
                        "generations_completed": job_data.get("generations_completed"),
                        "best_fitness": job_data.get("best_fitness"),
                        "best_roi": job_data.get("best_roi"),
                        "progress_pct": job_data.get("progress_pct"),
                        "started_at": job_data.get("started_at"),
                        "checkpoints": job_data.get("checkpoints", []),
                    }
                )

    return TrainingJobListResponse(jobs=jobs, total=len(jobs))


@router.get(
    "/async-training-jobs/{job_id}",
    response_model=TrainingJobDetailResponse,
)
async def get_training_job_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
) -> TrainingJobDetailResponse:
    """Get training job status and progress.

    Returns current generation, fitness, checkpoints, and plot data.
    """
    manager = get_training_process_manager()
    job_data = await manager.get_job_status(job_id)

    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training job {job_id} not found",
        )

    # Map checkpoints
    checkpoints = [
        TrainingCheckpointResponse(
            generation=c["generation"],
            model_id=c.get("model_id", f"{job_id}_{c['generation']}"),
            fitness=c["fitness"],
            roi=c.get("roi"),
            created_at=datetime.fromisoformat(c["created_at"])
            if c.get("created_at")
            else datetime.utcnow(),
        )
        for c in job_data.checkpoints or []
    ]

    return TrainingJobDetailResponse(
        job_id=job_data.job_id,
        symbol=job_data.symbol,
        status=job_data.status,
        generations_total=job_data.generations_total,
        generations_completed=job_data.generations_completed,
        best_fitness=job_data.best_fitness,
        best_roi=job_data.best_roi,
        progress_pct=job_data.progress_pct,
        started_at=job_data.started_at,
        checkpoints=checkpoints,
        current_plot=None,
    )


@router.get(
    "/async-training-jobs/{job_id}/checkpoints",
    response_model=list[TrainingCheckpointResponse],
)
async def list_training_checkpoints_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
) -> list[TrainingCheckpointResponse]:
    """List all checkpoints for a training job.

    Checkpoints are saved every N generations.
    """
    manager = get_training_process_manager()
    checkpoints = await manager.list_checkpoints(job_id)

    return [
        TrainingCheckpointResponse(
            generation=c["generation"],
            model_id=f"{job_id}_{c['generation']}",
            fitness=c["fitness"],
            roi=c.get("roi"),
            created_at=datetime.fromisoformat(c["created_at"])
            if c.get("created_at")
            else datetime.utcnow(),
        )
        for c in checkpoints
    ]


@router.post(
    "/async-training-jobs/{job_id}/select-checkpoint",
    response_model=SelectCheckpointResponse,
)
async def select_checkpoint_endpoint(
    request: SelectCheckpointRequest,
    job_id: str = FastAPIPath(..., min_length=1),
) -> SelectCheckpointResponse:
    """Select a checkpoint and save it as a model in the database.

    This makes the checkpoint available in /api/v1/models/
    """
    manager = get_training_process_manager()

    # Get checkpoint data from Worker
    checkpoint_data = await manager.get_checkpoint(job_id, request.generation)

    if not checkpoint_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint gen {request.generation} not found for job {job_id}",
        )

    # Get job status for symbol and checkpoint metadata
    job_status = await manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training job {job_id} not found",
        )

    checkpoints = job_status.checkpoints or []
    checkpoint_meta = next(
        (c for c in checkpoints if c["generation"] == request.generation),
        None,
    )

    # Load genome from pickle file
    genome_path = checkpoint_data.get("genome_path")
    if not genome_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Genome path not available",
        )

    genome_file = Path(genome_path)
    if not genome_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome file not found: {genome_path}",
        )

    with open(genome_file, "rb") as f:
        genome, config = pickle.load(f)

    genome_bytes = pickle.dumps((genome, config))
    symbol = job_status.symbol or "BTC_USD"

    genome_entity = Genome(
        genome_data=genome_bytes,
        fitness=checkpoint_data.get("fitness", 0) or 0.0,
        generation=request.generation,
        symbol=Symbol(value=symbol),
        roi_validation=checkpoint_data.get("roi", 0)
        or (checkpoint_meta.get("roi", 0) if checkpoint_meta else 0),
        total_return=(checkpoint_data.get("roi", 0) or 0) / 100,
        is_active=False,
        model_family="NEAT_RNN_V1",
        trained_at=datetime.utcnow(),
        notes=f"Checkpoint from training job {job_id}, generation {request.generation}",
    )

    # Save to database
    saved = await save_genome(genome_entity)

    logger.info(
        "Checkpoint selected and saved as model",
        job_id=job_id,
        generation=request.generation,
        model_id=saved.id,
    )

    return SelectCheckpointResponse(
        job_id=job_id,
        generation=request.generation,
        model_id=str(saved.id),
        activated=True,
        message=f"Checkpoint gen {request.generation} saved as model {saved.id}",
    )


@router.post(
    "/async-training-jobs/{job_id}/stop",
    response_model=TrainingJobStopResponse,
)
async def stop_training_job_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
    graceful: bool = True,
) -> TrainingJobStopResponse:
    """Stop a running training job.

    Sends stop signal to the Worker subprocess and updates job status.
    """
    manager = get_training_process_manager()
    success = await manager.stop_training(job_id, graceful=graceful)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training job {job_id} not found or already stopped",
        )

    return TrainingJobStopResponse(
        job_id=job_id,
        status="stopped",
        message=f"Training job {job_id} has been stopped",
    )


# =============================================================================
# Training Plot Endpoints (Phase 3)
# =============================================================================


@router.get(
    "/async-training-jobs/{job_id}/plot",
    response_model=TrainingPlotResponse,
)
async def get_training_plot_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
) -> TrainingPlotResponse:
    """Get training plot with fitness curve and equity curve.

    Returns Plotly HTML for the current training progress.
    Uses the most recent checkpoint's equity curve if available.
    """
    manager = get_training_process_manager()
    job_data = await manager.get_job_status(job_id)

    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training job {job_id} not found",
        )

    # Get checkpoints
    checkpoints = job_data.checkpoints or []

    # Try to get plot from last checkpoint
    plot_html = ""
    if checkpoints:
        last_checkpoint = checkpoints[-1]
        plot_html = last_checkpoint.get("plot_html", "")
        if plot_html:
            pass  # Use stored plot
        else:
            # Try to get plot from Worker
            plot_html = (
                await manager.get_checkpoint_plot(job_id, last_checkpoint["generation"]) or ""
            )

    if not plot_html:
        # Fallback to simple fitness plot
        plot_html = _generate_fitness_plot_html(checkpoints, job_data.symbol or "")

    return TrainingPlotResponse(
        job_id=job_id,
        plot_html=plot_html,
        generation=job_data.generations_completed,
        fitness=job_data.best_fitness,
        created_at=datetime.utcnow(),
    )


@router.get(
    "/async-training-jobs/{job_id}/checkpoints/{generation}/plot",
    response_model=TrainingPlotResponse,
)
async def get_checkpoint_plot_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
    generation: int = FastAPIPath(..., ge=1),
) -> TrainingPlotResponse:
    """Get plot for a specific checkpoint.

    Shows the equity curve at that specific generation.
    """
    manager = get_training_process_manager()

    # Get plot from Worker
    plot_html = await manager.get_checkpoint_plot(job_id, generation)

    if not plot_html:
        # Fallback to generating plot from checkpoint data
        job_data = await manager.get_job_status(job_id)
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found",
            )

        checkpoints = job_data.checkpoints or []
        checkpoint = next((c for c in checkpoints if c["generation"] == generation), None)

        if not checkpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Checkpoint generation {generation} not found for job {job_id}",
            )

        plot_html = _generate_checkpoint_plot_html(checkpoint, job_data.symbol or "")

        return TrainingPlotResponse(
            job_id=job_id,
            plot_html=plot_html,
            generation=generation,
            fitness=checkpoint.get("fitness"),
            created_at=datetime.fromisoformat(checkpoint["created_at"]),
        )

    # Get job data for response
    job_data = await manager.get_job_status(job_id)
    checkpoints = job_data.checkpoints if job_data else []
    checkpoint = next((c for c in checkpoints if c["generation"] == generation), None)

    return TrainingPlotResponse(
        job_id=job_id,
        plot_html=plot_html,
        generation=generation,
        fitness=checkpoint.get("fitness") if checkpoint else None,
        created_at=datetime.fromisoformat(checkpoint["created_at"])
        if checkpoint and checkpoint.get("created_at")
        else datetime.utcnow(),
    )


@router.get(
    "/async-training-jobs/{job_id}/progress-plot",
    response_model=TrainingProgressPlotResponse,
)
async def get_training_progress_plot_endpoint(
    job_id: str = FastAPIPath(..., min_length=1),
) -> TrainingProgressPlotResponse:
    """Get training progress data for live plotting.

    Returns structured data for client-side Plotly rendering.
    """
    manager = get_training_process_manager()
    job_data = await manager.get_job_status(job_id)

    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Training job {job_id} not found",
        )

    checkpoints = job_data.checkpoints or []
    generations = [c["generation"] for c in checkpoints]
    fitness_values = [c["fitness"] for c in checkpoints]

    # Build Plotly-compatible data structure
    plot_data = {
        "data": [
            {
                "x": generations,
                "y": fitness_values,
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Fitness",
                "line": {"color": "#00CC96", "width": 2},
                "marker": {"size": 8},
            }
        ],
        "layout": {
            "title": f"Training Progress - {job_data.symbol or ''}",
            "xaxis": {"title": "Generation"},
            "yaxis": {"title": "Fitness"},
            "showlegend": True,
        },
    }

    return TrainingProgressPlotResponse(
        job_id=job_id,
        plot_data=plot_data,
        generations=generations,
        fitness_values=fitness_values,
        updated_at=datetime.utcnow(),
    )


def _generate_fitness_plot_html(checkpoints: list[dict], symbol: str) -> str:
    """Generate Plotly HTML for fitness curve.

    Args:
        checkpoints: List of checkpoint dicts with generation and fitness
        symbol: Trading symbol

    Returns:
        Plotly HTML string
    """
    if not checkpoints:
        return "<div>No checkpoint data available yet</div>"

    try:
        generations = [c["generation"] for c in checkpoints]
        fitness_values = [c["fitness"] for c in checkpoints]

        # Build Plotly figure config
        fig_config = {
            "data": [
                {
                    "x": generations,
                    "y": fitness_values,
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Best Fitness",
                    "line": {"color": "#00CC96", "width": 3},
                    "marker": {"size": 10, "color": "#00CC96"},
                }
            ],
            "layout": {
                "title": {
                    "text": f"Training Fitness - {symbol}",
                    "font": {"size": 16},
                },
                "xaxis": {
                    "title": "Generation",
                    "gridcolor": "#333",
                },
                "yaxis": {
                    "title": "Fitness",
                    "gridcolor": "#333",
                },
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "showlegend": False,
            },
        }

        # Return as JSON-embedded HTML for client-side rendering
        return f"""
        <div id="training-plot-{symbol}" style="width:100%;height:400px;"></div>
        <script>
            (function() {{
                var data = {json.dumps(fig_config["data"])};
                var layout = {json.dumps(fig_config["layout"])};
                Plotly.newPlot('training-plot-{symbol}', data, layout, {{responsive: true}});
            }})();
        </script>
        """
    except Exception as e:
        return f"<div>Error generating plot: {e}</div>"


def _generate_checkpoint_plot_html(checkpoint: dict, symbol: str) -> str:
    """Generate Plotly HTML for specific checkpoint.

    Args:
        checkpoint: Checkpoint dict with generation, fitness, roi
        symbol: Trading symbol

    Returns:
        Plotly HTML string
    """
    try:
        gen = checkpoint["generation"]
        fitness = checkpoint.get("fitness", 0)
        roi = checkpoint.get("roi", 0)

        # Simple metric display for now
        # In production, this would show the actual equity curve from that checkpoint
        fig_config = {
            "data": [
                {
                    "type": "indicator",
                    "mode": "number+delta",
                    "value": fitness,
                    "title": {"text": "Fitness"},
                    "domain": {"row": 0, "column": 0},
                },
                {
                    "type": "indicator",
                    "mode": "number+delta",
                    "value": roi,
                    "title": {"text": "ROI %"},
                    "domain": {"row": 0, "column": 1},
                },
            ],
            "layout": {
                "title": f"Checkpoint Gen {gen} - {symbol}",
                "grid": {"rows": 1, "columns": 2},
                "paper_bgcolor": "rgba(0,0,0,0)",
            },
        }

        return f"""
        <div id="checkpoint-plot-{gen}" style="width:100%;height:300px;"></div>
        <script>
            (function() {{
                var data = {json.dumps(fig_config["data"])};
                var layout = {json.dumps(fig_config["layout"])};
                Plotly.newPlot('checkpoint-plot-{gen}', data, layout, {{responsive: true}});
            }})();
        </script>
        """
    except Exception as e:
        return f"<div>Error generating checkpoint plot: {e}</div>"
