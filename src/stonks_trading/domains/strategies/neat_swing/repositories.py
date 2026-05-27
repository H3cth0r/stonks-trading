"""Repository functions for NEAT swing strategy.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime
from typing import Any

from stonks_trading.domains.strategies.neat_swing.entities import NeatModel, NeatTrainingRun
from stonks_trading.shared.postgres_models import GenomeModel, TrainingRunModel


async def save_neat_model(model: NeatModel) -> NeatModel:
    """Persist a NEAT model to the database.

    Args:
        model: NeatModel entity to persist

    Returns:
        NeatModel with assigned ID
    """
    model_db = await GenomeModel.create(
        genome_data=model.model_data,
        symbol=model.symbol or "",
        model_family=model.strategy_type or "neat_swing",
        is_active=False,
        fitness_score=model.fitness_score,
        roi_validation=model.roi_validation,
        roi_test=model.roi_test,
        max_drawdown=model.max_drawdown,
        num_trades=model.num_trades,
        total_return=model.total_return,
        trained_at=model.created_at,
        active_for_bot_type=model.active_for_bot_type,
        active_for_instance_id=model.active_for_instance_id,
    )
    model.id = model_db.id
    return model


async def get_neat_model_by_id(model_id: int) -> NeatModel | None:
    """Get NEAT model by ID.

    Args:
        model_id: Model database ID

    Returns:
        NeatModel entity or None if not found
    """
    model_db = await GenomeModel.filter(id=model_id).first()
    if not model_db:
        return None
    return _genome_to_neat_model(model_db)


async def get_active_neat_model(
    symbol: str,
    bot_type: str | None = None,
    bot_instance_id: str | None = None,
) -> NeatModel | None:
    """Get active NEAT model for symbol.

    Args:
        symbol: Trading symbol
        bot_type: Optional bot type filter
        bot_instance_id: Optional bot instance filter

    Returns:
        Active NeatModel or None
    """
    query = GenomeModel.filter(
        model_family="neat_swing",
        symbol=symbol,
        is_active=True,
    )
    if bot_type:
        query = query.filter(active_for_bot_type=bot_type)
    if bot_instance_id:
        query = query.filter(active_for_instance_id=bot_instance_id)

    model_db = await query.first()
    if not model_db:
        return None
    return _genome_to_neat_model(model_db)


async def list_neat_models(
    symbol: str | None = None,
    is_active: bool | None = None,
    bot_type: str | None = None,
    bot_instance_id: str | None = None,
    limit: int = 100,
) -> list[NeatModel]:
    """List NEAT models with optional filters.

    Args:
        symbol: Optional symbol filter
        is_active: Optional active filter
        bot_type: Optional bot type filter
        bot_instance_id: Optional bot instance filter
        limit: Maximum results

    Returns:
        List of NeatModel entities
    """
    query = GenomeModel.filter(model_family="neat_swing")

    if symbol:
        query = query.filter(symbol=symbol)
    if is_active is not None:
        query = query.filter(is_active=is_active)
    if bot_type:
        query = query.filter(active_for_bot_type=bot_type)
    if bot_instance_id:
        query = query.filter(active_for_instance_id=bot_instance_id)

    models_db = await query.order_by("-trained_at").limit(limit)
    return [_genome_to_neat_model(m) for m in models_db]


async def activate_neat_model(model_id: int) -> bool:
    """Activate a NEAT model (deactivates others for same strategy/symbol).

    Args:
        model_id: Model ID to activate

    Returns:
        True if successful
    """
    model_db = await GenomeModel.filter(id=model_id).first()
    if not model_db:
        return False

    # Deactivate other models for same strategy/symbol/bot context
    await GenomeModel.filter(
        model_family=model_db.model_family,
        symbol=model_db.symbol,
        active_for_bot_type=model_db.active_for_bot_type,
        active_for_instance_id=model_db.active_for_instance_id,
        is_active=True,
    ).update(is_active=False)

    # Activate this model
    model_db.is_active = True
    model_db.activated_at = datetime.utcnow()
    await model_db.save()

    return True


async def save_training_run(run: NeatTrainingRun) -> NeatTrainingRun:
    """Persist a training run to the database.

    Args:
        run: NeatTrainingRun entity to persist

    Returns:
        NeatTrainingRun with assigned ID
    """
    run_db = await TrainingRunModel.create(
        symbol=run.symbol,
        model_family="neat_swing",
        generations=run.generations,
        best_fitness=run.best_fitness,
        best_roi_validation=run.best_roi_validation,
        best_roi_test=run.best_roi_test,
        episode_steps=run.episode_steps,
        fee_rate=run.fee_rate,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        config_snapshot=run.config_snapshot,
    )
    run.id = run_db.id
    return run


async def get_training_run(run_id: int) -> NeatTrainingRun | None:
    """Get training run by ID.

    Args:
        run_id: Training run database ID

    Returns:
        NeatTrainingRun entity or None if not found
    """
    run_db = await TrainingRunModel.filter(id=run_id).first()
    if not run_db:
        return None
    return _training_run_to_entity(run_db)


async def list_training_runs(
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[NeatTrainingRun]:
    """List training runs with optional filters.

    Args:
        symbol: Optional symbol filter
        status: Optional status filter
        limit: Maximum results

    Returns:
        List of NeatTrainingRun entities
    """
    query = TrainingRunModel.filter(model_family="neat_swing")

    if symbol:
        query = query.filter(symbol=symbol)
    if status:
        query = query.filter(status=status)

    runs_db = await query.order_by("-started_at").limit(limit)
    return [_training_run_to_entity(r) for r in runs_db]


async def update_training_run(
    run_id: int,
    best_fitness: float | None = None,
    best_roi_validation: float | None = None,
    best_roi_test: float | None = None,
    finished_at: datetime | None = None,
    status: str | None = None,
) -> bool:
    """Update training run with final metrics.

    Args:
        run_id: Training run ID
        best_fitness: Best fitness score achieved
        best_roi_validation: Best validation ROI
        best_roi_test: Best test ROI
        finished_at: Completion timestamp
        status: Final status

    Returns:
        True if successful
    """
    update_fields: dict[str, Any] = {}
    if best_fitness is not None:
        update_fields["best_fitness"] = best_fitness
    if best_roi_validation is not None:
        update_fields["best_roi_validation"] = best_roi_validation
    if best_roi_test is not None:
        update_fields["best_roi_test"] = best_roi_test
    if finished_at is not None:
        update_fields["finished_at"] = finished_at
    if status is not None:
        update_fields["status"] = status

    if not update_fields:
        return False

    updated = await TrainingRunModel.filter(id=run_id).update(**update_fields)
    return updated > 0


def _genome_to_neat_model(model_db: GenomeModel) -> NeatModel:
    """Convert database model to NeatModel entity.

    Args:
        model_db: Database model

    Returns:
        NeatModel entity
    """
    return NeatModel(
        model_data=model_db.genome_data or b"",
        id=model_db.id,
        strategy_type=model_db.model_family,
        symbol=model_db.symbol,
        fitness_score=model_db.fitness_score,
        roi_validation=model_db.roi_validation,
        roi_test=model_db.roi_test,
        max_drawdown=model_db.max_drawdown,
        num_trades=model_db.num_trades,
        total_return=model_db.total_return,
        created_at=model_db.trained_at,
        activated_at=model_db.activated_at,
        deactivated_at=model_db.deactivated_at,
        active_for_bot_type=model_db.active_for_bot_type,
        active_for_instance_id=model_db.active_for_instance_id,
    )


def _training_run_to_entity(run_db: TrainingRunModel) -> NeatTrainingRun:
    """Convert database model to NeatTrainingRun entity.

    Args:
        run_db: Database model

    Returns:
        NeatTrainingRun entity
    """
    return NeatTrainingRun(
        id=run_db.id,
        symbol=run_db.symbol,
        generations=run_db.generations,
        best_fitness=run_db.best_fitness,
        best_roi_validation=run_db.best_roi_validation,
        best_roi_test=run_db.best_roi_test,
        episode_steps=run_db.episode_steps,
        fee_rate=run_db.fee_rate,
        started_at=run_db.started_at,
        finished_at=run_db.finished_at,
        status=run_db.status,
        config_snapshot=run_db.config_snapshot,
    )
