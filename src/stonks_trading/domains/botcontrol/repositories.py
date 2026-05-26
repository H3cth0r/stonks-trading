"""Repository functions for bot control domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime, timedelta
from typing import Any

from stonks_trading.domains.botcontrol.entities import BotProcess, ProcessStatus
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.postgres_models import BotInstanceModel, BotProcessModel

# =============================================================================
# Bot Process Repository Functions
# =============================================================================


async def create_bot_process(process: BotProcess) -> BotProcess:
    """Persist a new bot process record.

    Args:
        process: BotProcess entity to persist

    Returns:
        BotProcess with assigned ID
    """
    model = await BotProcessModel.create(
        bot_type=process.bot_type,
        bot_instance_id=process.bot_instance_id,
        mode=process.mode,
        symbols=process.symbols,
        pid=process.pid,
        status=process.status.value,
        started_at=process.started_at,
        stopped_at=process.stopped_at,
        exit_code=process.exit_code,
        error_message=process.error_message,
        config_path=process.config_path,
    )
    process.created_at = model.created_at
    process.updated_at = model.updated_at
    return process


async def get_bot_process(bot_type: str, instance_id: str) -> BotProcess | None:
    """Get bot process by bot type and instance ID.

    Args:
        bot_type: Bot type identifier
        instance_id: Bot instance ID

    Returns:
        BotProcess entity or None if not found
    """
    model = await BotProcessModel.filter(
        bot_type=bot_type,
        bot_instance_id=instance_id,
    ).first()

    if not model:
        return None

    return _model_to_bot_process(model)


async def update_bot_process_status(
    context: BotContext,
    status: ProcessStatus,
    **kwargs: Any,
) -> BotProcess | None:
    """Update bot process status and optional fields.

    Args:
        context: BotContext identifying the bot
        status: New ProcessStatus
        **kwargs: Optional fields to update (pid, started_at, stopped_at, etc.)

    Returns:
        Updated BotProcess or None if not found
    """
    model = await BotProcessModel.filter(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    ).first()

    if not model:
        return None

    model.status = status.value
    model.updated_at = datetime.utcnow()

    # Update optional fields
    if "pid" in kwargs:
        model.pid = kwargs["pid"]
    if "started_at" in kwargs:
        model.started_at = kwargs["started_at"]
    if "stopped_at" in kwargs:
        model.stopped_at = kwargs["stopped_at"]
    if "exit_code" in kwargs:
        model.exit_code = kwargs["exit_code"]
    if "error_message" in kwargs:
        model.error_message = kwargs["error_message"]
    if "symbols" in kwargs:
        model.symbols = kwargs["symbols"]
    if "mode" in kwargs:
        model.mode = kwargs["mode"]
    if "config_path" in kwargs:
        model.config_path = kwargs["config_path"]

    await model.save()
    return _model_to_bot_process(model)


async def list_running_bots() -> list[BotProcess]:
    """List all bots with RUNNING status.

    Returns:
        List of BotProcess entities with status=RUNNING
    """
    models = await BotProcessModel.filter(
        status=ProcessStatus.RUNNING.value,
    ).order_by("-started_at")

    return [_model_to_bot_process(m) for m in models]


async def list_bot_processes(
    status: ProcessStatus | None = None,
    limit: int = 100,
) -> list[BotProcess]:
    """List bot processes with optional status filter.

    Args:
        status: Optional status filter
        limit: Maximum number of results

    Returns:
        List of BotProcess entities
    """
    query = BotProcessModel.all()

    if status:
        query = query.filter(status=status.value)

    models = await query.order_by("-updated_at").limit(limit)
    return [_model_to_bot_process(m) for m in models]


async def delete_bot_process(context: BotContext) -> bool:
    """Delete bot process record.

    Args:
        context: BotContext identifying the bot

    Returns:
        True if deleted, False if not found
    """
    deleted = await BotProcessModel.filter(
        bot_type=context.bot_type,
        bot_instance_id=context.instance_id,
    ).delete()

    return bool(deleted > 0)


async def list_stale_processes(threshold_minutes: int = 5) -> list[BotProcess]:
    """List processes marked RUNNING but not updated recently.

    Args:
        threshold_minutes: Minutes since last update to consider stale

    Returns:
        List of potentially stale BotProcess entities
    """
    cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)

    models = await BotProcessModel.filter(
        status=ProcessStatus.RUNNING.value,
        updated_at__lt=cutoff,
    )

    return [_model_to_bot_process(m) for m in models]


# =============================================================================
# Bot Instance Repository Functions (for validation)
# =============================================================================


async def check_bot_instance_exists(bot_type: str, instance_id: str) -> bool:
    """Check if a bot instance is registered.

    Args:
        bot_type: Bot type identifier
        instance_id: Bot instance ID

    Returns:
        True if bot instance exists in registry
    """
    count = await BotInstanceModel.filter(
        bot_type=bot_type,
        instance_id=instance_id,
    ).count()

    return bool(count > 0)


# =============================================================================
# Model Conversion Helpers
# =============================================================================


def _model_to_bot_process(model: BotProcessModel) -> BotProcess:
    """Convert BotProcessModel to BotProcess entity.

    Args:
        model: Database model instance

    Returns:
        BotProcess entity
    """
    return BotProcess(
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
        mode=model.mode,
        symbols=list(model.symbols) if model.symbols else [],
        pid=model.pid,
        status=ProcessStatus(model.status),
        started_at=model.started_at,
        stopped_at=model.stopped_at,
        exit_code=model.exit_code,
        error_message=model.error_message,
        config_path=model.config_path,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
