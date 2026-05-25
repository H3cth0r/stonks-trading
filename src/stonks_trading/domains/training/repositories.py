"""Training domain repositories - PURE DATA ACCESS ONLY.

Standalone async functions following trading domain pattern.
NO business logic - only ORM queries.

Repository rules (per architecture.md lines 42-48):
- Single file with standalone async functions
- NO classes, NO ABC, NO inheritance
- Pure data access - no business logic
- Use Tortoise ORM for all database operations
"""

from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.entities import GenerationMetric, Genome, TrainingRun
from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.shared.postgres_models import (
    GenerationMetricModel,
    GenomeModel,
    TrainingRunModel,
)

# =============================================================================
# Training Run Repository Functions
# =============================================================================


async def create_training_run(
    symbol: Symbol,
    model_family: str,
    trainer_git_sha: str,
    generations: int,
    pop_size: int,
    episode_steps: int,
    fee_rate: float,
    config_snapshot: dict[str, Any],
) -> TrainingRun:
    """Create a new training run record.

    Args:
        symbol: Trading symbol
        model_family: Model family identifier
        trainer_git_sha: Git SHA of trainer version
        generations: Number of generations to train
        pop_size: Population size
        episode_steps: Steps per episode
        fee_rate: Fee rate for training
        config_snapshot: Training configuration

    Returns:
        Created TrainingRun entity with ID
    """
    model = await TrainingRunModel.create(
        symbol=symbol.value,
        model_family=model_family,
        trainer_git_sha=trainer_git_sha,
        generations=generations,
        pop_size=pop_size,
        episode_steps=episode_steps,
        fee_rate=fee_rate,
        config_snapshot=config_snapshot,
        status="pending",
        started_at=datetime.utcnow(),
    )
    return _model_to_training_run(model)


async def update_training_run_status(
    run_id: int,
    status: str,
    best_fitness: float | None = None,
    best_roi_validation: float | None = None,
    finished_at: datetime | None = None,
) -> TrainingRun | None:
    """Update training run status.

    Args:
        run_id: Training run ID
        status: New status (pending, running, completed, failed)
        best_fitness: Best fitness achieved
        best_roi_validation: Best ROI on validation set
        finished_at: Completion timestamp

    Returns:
        Updated TrainingRun or None if not found
    """
    model = await TrainingRunModel.get_or_none(id=run_id)
    if not model:
        return None

    model.status = status
    if best_fitness is not None:
        model.best_fitness = best_fitness
    if best_roi_validation is not None:
        model.best_roi_validation = best_roi_validation
    if finished_at:
        model.finished_at = finished_at

    await model.save()
    return _model_to_training_run(model)


async def get_training_run(run_id: int) -> TrainingRun | None:
    """Get training run by ID.

    Args:
        run_id: Training run ID

    Returns:
        TrainingRun or None if not found
    """
    model = await TrainingRunModel.get_or_none(id=run_id)
    if not model:
        return None
    return _model_to_training_run(model)


async def list_training_runs(
    status: str | None = None,
    symbol: Symbol | None = None,
    bot_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TrainingRun]:
    """List training runs with optional filters.

    Args:
        status: Filter by status
        symbol: Filter by symbol
        bot_type: Filter by bot type
        limit: Maximum results
        offset: Results to skip

    Returns:
        List of TrainingRun entities
    """
    query = TrainingRunModel.all()

    if status:
        query = query.filter(status=status)
    if symbol:
        query = query.filter(symbol=symbol.value)

    models = await query.order_by("-started_at").offset(offset).limit(limit)
    return [_model_to_training_run(m) for m in models]


# =============================================================================
# Generation Metric Repository Functions
# =============================================================================


async def save_generation_metric(metric: GenerationMetric) -> GenerationMetric:
    """Save generation metric.

    Args:
        metric: GenerationMetric entity to save

    Returns:
        Saved metric with ID assigned
    """
    model = await GenerationMetricModel.create(
        run_id=metric.run_id,
        generation=metric.generation,
        best_fitness=metric.best_fitness,
        mean_fitness=metric.mean_fitness,
        worst_fitness=metric.worst_fitness or 0.0,
        num_species=metric.num_species or 0,
        num_genomes=metric.num_genomes or 0,
        best_roi_validation=metric.best_roi_validation,
        stagnation_count=metric.stagnation_count,
        num_trades_best=metric.num_trades_best,
        max_drawdown_best=metric.max_drawdown_best,
    )
    metric.id = model.id
    return metric


async def list_generation_metrics(run_id: int) -> list[GenerationMetric]:
    """List generation metrics for a run.

    Args:
        run_id: Training run ID

    Returns:
        List of GenerationMetric entities ordered by generation
    """
    models = await GenerationMetricModel.filter(run_id=run_id).order_by("generation")
    return [_model_to_generation_metric(m) for m in models]


# =============================================================================
# Genome Repository Functions (for training context)
# =============================================================================


async def get_active_genome_for_symbol(
    bot_context: BotContext,
    symbol: Symbol,
) -> Genome | None:
    """Get active genome for symbol in bot context.

    Args:
        bot_context: Bot context for scoping
        symbol: Trading symbol

    Returns:
        Active Genome or None if not found
    """
    model = await GenomeModel.get_or_none(
        active_for_bot_type=bot_context.bot_type,
        active_for_instance_id=bot_context.instance_id,
        symbol=symbol.value,
        is_active=True,
    )
    if not model:
        return None
    return _model_to_genome(model)


async def deactivate_genome_for_context(genome_id: int) -> bool:
    """Deactivate a genome (clear bot context).

    Args:
        genome_id: Genome ID to deactivate

    Returns:
        True if deactivated, False if not found
    """
    model = await GenomeModel.get_or_none(id=genome_id)
    if not model:
        return False

    model.is_active = False
    model.active_for_bot_type = None
    model.active_for_instance_id = None
    model.deactivated_at = datetime.utcnow()
    await model.save()
    return True


async def activate_genome_for_context(
    genome_id: int,
    bot_context: BotContext,
) -> bool:
    """Activate genome for bot context.

    Args:
        genome_id: Genome ID to activate
        bot_context: Bot context to activate for

    Returns:
        True if activated, False if not found
    """
    model = await GenomeModel.get_or_none(id=genome_id)
    if not model:
        return False

    model.is_active = True
    model.active_for_bot_type = bot_context.bot_type
    model.active_for_instance_id = bot_context.instance_id
    model.activated_at = datetime.utcnow()
    await model.save()
    return True


async def save_genome(genome: Genome) -> Genome:
    """Persist genome with metadata.

    Args:
        genome: Genome entity to save

    Returns:
        Saved genome with ID assigned
    """
    model = await GenomeModel.create(
        symbol=genome.symbol.value if genome.symbol else None,
        genome_data=genome.genome_data,
        fitness=genome.fitness,
        generation=genome.generation,
        model_family=genome.model_family,
        artifact_uri=genome.artifact_uri,
        trainer_git_sha=genome.trainer_git_sha,
        feature_schema_id=genome.feature_schema_id,
        is_active=genome.is_active,
        roi_validation=genome.roi_validation,
        roi_test=genome.roi_test,
        max_drawdown=genome.max_drawdown,
        num_trades=genome.trades_count,
        total_return=genome.total_return,
        fitness_score=genome.fitness,
        fee_rate_used=genome.fee_rate_used,
        trained_at=genome.trained_at or datetime.utcnow(),
        activated_at=genome.activated_at,
        deactivated_at=genome.deactivated_at,
        active_for_bot_type=genome.active_for_bot_type,
        active_for_instance_id=genome.active_for_instance_id,
    )
    genome.id = model.id
    return genome


# =============================================================================
# Model to Entity Conversion Functions
# =============================================================================


def _model_to_training_run(model: TrainingRunModel) -> TrainingRun:
    """Convert TrainingRunModel to TrainingRun entity.

    Pure transformation - no logic.
    """
    return TrainingRun(
        id=model.id,
        symbol=Symbol(value=model.symbol) if model.symbol else None,
        model_family=model.model_family,
        artifact_prefix_uri=model.artifact_prefix_uri,
        trainer_git_sha=model.trainer_git_sha,
        generations=model.generations,
        best_fitness=model.best_fitness or 0.0,
        best_roi_validation=model.best_roi_validation,
        best_roi_test=model.best_roi_test,
        episode_steps=model.episode_steps,
        pop_size=model.pop_size,
        fee_rate=model.fee_rate,
        status=model.status,
        config_snapshot=model.config_snapshot,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


def _model_to_generation_metric(model: GenerationMetricModel) -> GenerationMetric:
    """Convert GenerationMetricModel to GenerationMetric entity.

    Pure transformation - no logic.
    """
    return GenerationMetric(
        id=model.id,
        run_id=model.run_id,
        generation=model.generation,
        best_fitness=model.best_fitness,
        mean_fitness=model.mean_fitness,
        worst_fitness=model.worst_fitness or 0.0,
        num_species=model.num_species or 0,
        num_genomes=model.num_genomes or 0,
        best_roi_validation=model.best_roi_validation,
        stagnation_count=model.stagnation_count,
        num_trades_best=model.num_trades_best,
        max_drawdown_best=model.max_drawdown_best,
        created_at=model.created_at,
    )


def _model_to_genome(model: GenomeModel) -> Genome:
    """Convert GenomeModel to Genome entity.

    Pure transformation - no logic.
    """
    return Genome(
        id=model.id,
        genome_data=model.genome_data or b"",
        fitness=model.fitness_score or 0.0,
        generation=0,
        symbol=Symbol(value=model.symbol) if model.symbol else None,
        model_family=model.model_family,
        artifact_uri=model.artifact_uri,
        trainer_git_sha=model.trainer_git_sha,
        feature_schema_id=model.feature_schema_id,
        is_active=model.is_active,
        roi_validation=model.roi_validation,
        roi_test=model.roi_test,
        max_drawdown=model.max_drawdown or 0.0,
        total_return=model.total_return or 0.0,
        trades_count=model.num_trades or 0,
        fee_rate_used=model.fee_rate_used,
        trained_at=model.trained_at,
        activated_at=model.activated_at,
        deactivated_at=model.deactivated_at,
        active_for_bot_type=model.active_for_bot_type,
        active_for_instance_id=model.active_for_instance_id,
    )
