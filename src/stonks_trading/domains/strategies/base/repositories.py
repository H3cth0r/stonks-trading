"""Repository functions for strategy base domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime

from stonks_trading.domains.strategies.base.entities import Model
from stonks_trading.shared.postgres_models import GenomeModel


async def save_model(model: Model) -> Model:
    """Persist a model to the database.

    Args:
        model: Model entity to persist

    Returns:
        Model with assigned ID
    """
    model_db = await GenomeModel.create(
        genome_data=model.model_data,
        symbol=model.symbol or "",
        model_family=model.strategy_type,
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


async def get_model_by_id(model_id: int) -> Model | None:
    """Get model by ID.

    Args:
        model_id: Model database ID

    Returns:
        Model entity or None if not found
    """
    model_db = await GenomeModel.filter(id=model_id).first()
    if not model_db:
        return None
    return _model_to_entity(model_db)


async def get_active_model(
    strategy_type: str,
    symbol: str,
    bot_type: str | None = None,
    bot_instance_id: str | None = None,
) -> Model | None:
    """Get active model for strategy/symbol combination.

    Args:
        strategy_type: Strategy type identifier
        symbol: Trading symbol
        bot_type: Optional bot type filter
        bot_instance_id: Optional bot instance filter

    Returns:
        Active Model or None
    """
    query = GenomeModel.filter(
        model_family=strategy_type,
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
    return _model_to_entity(model_db)


async def list_models(
    strategy_type: str | None = None,
    symbol: str | None = None,
    is_active: bool | None = None,
    bot_type: str | None = None,
    bot_instance_id: str | None = None,
    limit: int = 100,
) -> list[Model]:
    """List models with optional filters.

    Args:
        strategy_type: Optional strategy type filter
        symbol: Optional symbol filter
        is_active: Optional active filter
        bot_type: Optional bot type filter
        bot_instance_id: Optional bot instance filter
        limit: Maximum results

    Returns:
        List of Model entities
    """
    query = GenomeModel.all()

    if strategy_type:
        query = query.filter(model_family=strategy_type)
    if symbol:
        query = query.filter(symbol=symbol)
    if is_active is not None:
        query = query.filter(is_active=is_active)
    if bot_type:
        query = query.filter(active_for_bot_type=bot_type)
    if bot_instance_id:
        query = query.filter(active_for_instance_id=bot_instance_id)

    models_db = await query.order_by("-trained_at").limit(limit)
    return [_model_to_entity(m) for m in models_db]


async def activate_model(model_id: int) -> bool:
    """Activate a model (deactivates others for same strategy/symbol).

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


def _model_to_entity(model_db: GenomeModel) -> Model:
    """Convert database model to entity.

    Args:
        model_db: Database model

    Returns:
        Model entity
    """
    return Model(
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
