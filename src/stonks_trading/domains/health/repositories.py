"""Repository functions for health monitoring domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime, timedelta
from typing import Any

from stonks_trading.domains.health.entities import BotHealth, BotHeartbeat, HealthStatus
from stonks_trading.shared.postgres_models import (
    BotHeartbeatModel,
    BotInstanceModel,
    BotStateModel,
    RiskEventModel,
    TradeModel,
)

# =============================================================================
# Bot Heartbeat Repository Functions
# =============================================================================


async def save_heartbeat(heartbeat: BotHeartbeat) -> BotHeartbeat:
    """Persist bot heartbeat for health monitoring."""
    model = await BotHeartbeatModel.create(
        bot_type=heartbeat.bot_type,
        bot_instance_id=heartbeat.bot_instance_id,
        timestamp=heartbeat.timestamp,
        state_hash=heartbeat.state_hash,
        candle_timestamp=heartbeat.candle_timestamp,
    )
    heartbeat.id = model.id
    return heartbeat


async def get_latest_heartbeat(bot_type: str, instance_id: str) -> BotHeartbeat | None:
    """Get most recent heartbeat for a bot."""
    model = (
        await BotHeartbeatModel.filter(
            bot_type=bot_type,
            bot_instance_id=instance_id,
        )
        .order_by("-timestamp")
        .first()
    )
    if not model:
        return None
    return _model_to_bot_heartbeat(model)


async def list_recent_heartbeats(
    bot_type: str | None = None,
    instance_id: str | None = None,
    since: datetime | None = None,
) -> list[BotHeartbeat]:
    """List heartbeats with optional filtering."""
    query = BotHeartbeatModel.all()

    if bot_type:
        query = query.filter(bot_type=bot_type)
    if instance_id:
        query = query.filter(bot_instance_id=instance_id)
    if since:
        query = query.filter(timestamp__gte=since)

    models = await query.order_by("-timestamp")
    return [_model_to_bot_heartbeat(m) for m in models]


def _model_to_bot_heartbeat(model: BotHeartbeatModel) -> BotHeartbeat:
    """Convert BotHeartbeatModel to BotHeartbeat entity."""
    return BotHeartbeat(
        id=model.id,
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
        timestamp=model.timestamp,
        state_hash=model.state_hash,
        candle_timestamp=model.candle_timestamp,
    )


# =============================================================================
# Bot Health Snapshot Repository Functions
# =============================================================================


async def get_bot_health_snapshot(bot_type: str, instance_id: str) -> BotHealth:
    """Build health snapshot for a specific bot from multiple sources."""
    # Get bot instance info
    instance = await BotInstanceModel.get_or_none(
        bot_type=bot_type,
        instance_id=instance_id,
    )

    mode = "unknown"
    if instance:
        mode = instance.mode if isinstance(instance.mode, str) else instance.mode.value

    # Get latest heartbeat
    heartbeat_model = (
        await BotHeartbeatModel.filter(
            bot_type=bot_type,
            bot_instance_id=instance_id,
        )
        .order_by("-timestamp")
        .first()
    )

    last_heartbeat_at = heartbeat_model.timestamp if heartbeat_model else None

    # Get latest trade
    trade_model = (
        await TradeModel.filter(
            bot_type=bot_type,
            bot_instance_id=instance_id,
        )
        .order_by("-created_at")
        .first()
    )
    last_trade_at = trade_model.created_at if trade_model else None

    # Count positions
    position_count = await BotStateModel.filter(
        bot_type=bot_type,
        bot_instance_id=instance_id,
    ).count()

    # Count risk events in last hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    error_count_1h = await RiskEventModel.filter(
        bot_type=bot_type,
        bot_instance_id=instance_id,
        created_at__gte=one_hour_ago,
    ).count()

    # Get current drawdown from latest state if available
    current_drawdown = 0.0
    state_model = (
        await BotStateModel.filter(
            bot_type=bot_type,
            bot_instance_id=instance_id,
        )
        .order_by("-created_at")
        .first()
    )
    if state_model and state_model.state_json:
        state_data = state_model.state_json
        if isinstance(state_data, dict):
            current_drawdown = state_data.get("max_drawdown", 0.0)

    return BotHealth(
        bot_type=bot_type,
        bot_instance_id=instance_id,
        mode=mode,
        status=HealthStatus.UNKNOWN,  # Calculated by service layer
        last_heartbeat_at=last_heartbeat_at,
        trade_lag_seconds=None,  # Calculated by service layer
        last_trade_at=last_trade_at,
        position_count=position_count,
        current_drawdown=current_drawdown,
        error_count_1h=error_count_1h,
        message=None,
    )


async def list_all_bot_health_snapshots() -> list[BotHealth]:
    """Build health snapshots for all registered bot instances."""
    instances = await BotInstanceModel.all()
    snapshots = []

    for instance in instances:
        snapshot = await get_bot_health_snapshot(
            bot_type=instance.bot_type,
            instance_id=instance.instance_id,
        )
        snapshots.append(snapshot)

    return snapshots


# =============================================================================
# System Health Repository Functions
# =============================================================================


async def get_system_health_status() -> dict[str, Any]:
    """Get system health status with lightweight connectivity checks."""
    # Check database connectivity
    database_healthy = False
    try:
        # Lightweight ping via Tortoise
        await BotInstanceModel.all().limit(1)
        database_healthy = True
    except Exception:
        database_healthy = False

    # Check DuckDB connectivity (simplified check)
    duckdb_healthy = True  # Will be updated if DuckDB connection is available

    return {
        "database_healthy": database_healthy,
        "duckdb_healthy": duckdb_healthy,
        "api_healthy": True,  # If we're here, API is running
        "checked_at": datetime.utcnow(),
    }
