"""Use cases for health monitoring domain.

Orchestration layer - coordinates repositories, services, and entities.
No business logic here - pure coordination.
"""

from datetime import datetime, timedelta

from stonks_trading.domains.health.entities import (
    BotHealth,
    BotHeartbeat,
    HealthStatus,
    SystemHealth,
)
from stonks_trading.domains.health.repositories import (
    get_bot_health_snapshot,
    get_latest_heartbeat,
    get_system_health_status,
    list_all_bot_health_snapshots,
    list_recent_heartbeats,
    save_heartbeat,
)
from stonks_trading.domains.health.services import (
    BotHealthAssembler,
    SystemHealthCalculator,
)
from stonks_trading.domains.trading.value_objects import BotContext


class RecordHeartbeatUseCase:
    """Record a bot heartbeat for health monitoring.

    Called by bots periodically to indicate they are alive and healthy.
    """

    async def execute(
        self,
        context: BotContext,
        state_hash: str | None = None,
        candle_timestamp: datetime | None = None,
    ) -> BotHeartbeat:
        """Record a heartbeat for the given bot context.

        Args:
            context: Bot context (bot_type, instance_id)
            state_hash: Optional hash of bot state for integrity
            candle_timestamp: Optional timestamp of last processed candle

        Returns:
            The recorded BotHeartbeat entity
        """
        heartbeat = BotHeartbeat(
            bot_type=context.bot_type,
            bot_instance_id=context.instance_id,
            timestamp=datetime.utcnow(),
            state_hash=state_hash,
            candle_timestamp=candle_timestamp,
        )
        return await save_heartbeat(heartbeat)


class GetBotHealthUseCase:
    """Get comprehensive health status for a specific bot."""

    async def execute(self, bot_type: str, instance_id: str) -> BotHealth | None:
        """Get health snapshot for a specific bot.

        Args:
            bot_type: Type of bot (e.g., "neat_swing")
            instance_id: Bot instance ID

        Returns:
            BotHealth with calculated status and lag, or None if bot not found
        """
        # Get base health snapshot from repositories
        base_health = await get_bot_health_snapshot(bot_type, instance_id)

        if not base_health:
            return None

        # Get latest heartbeat for candle timestamp
        latest_heartbeat = await get_latest_heartbeat(bot_type, instance_id)
        last_candle_at = latest_heartbeat.candle_timestamp if latest_heartbeat else None

        # Assemble complete health with calculated fields
        return BotHealthAssembler.assemble(base_health, last_candle_at)


class GetSystemHealthUseCase:
    """Get system-wide health status."""

    async def execute(self) -> SystemHealth:
        """Get complete system health including all bots.

        Returns:
            SystemHealth with component status and per-bot health
        """
        # Get system component health
        system_status = await get_system_health_status()

        # Get all bot health snapshots
        bot_healths = await list_all_bot_health_snapshots()

        # Assemble complete health for each bot
        complete_bot_healths = []
        for health in bot_healths:
            latest_heartbeat = await get_latest_heartbeat(
                health.bot_type,
                health.bot_instance_id,
            )
            last_candle_at = latest_heartbeat.candle_timestamp if latest_heartbeat else None
            complete_health = BotHealthAssembler.assemble(health, last_candle_at)
            complete_bot_healths.append(complete_health)

        # Calculate overall system status
        overall_status = SystemHealthCalculator.calculate(
            api_healthy=system_status.get("api_healthy", True),
            database_healthy=system_status.get("database_healthy", False),
            duckdb_healthy=system_status.get("duckdb_healthy", False),
            bot_healths=complete_bot_healths,
        )

        return SystemHealth(
            status=overall_status,
            api_healthy=system_status.get("api_healthy", True),
            database_healthy=system_status.get("database_healthy", False),
            duckdb_healthy=system_status.get("duckdb_healthy", False),
            bots=complete_bot_healths,
            checked_at=datetime.utcnow(),
            message=self._get_system_message(overall_status, complete_bot_healths),
        )

    def _get_system_message(self, status: HealthStatus, bot_healths: list[BotHealth]) -> str | None:
        """Generate system message based on status."""
        if status == HealthStatus.HEALTHY:
            return f"All systems operational ({len(bot_healths)} bots)"

        unhealthy = [b for b in bot_healths if b.status == HealthStatus.UNHEALTHY]
        degraded = [b for b in bot_healths if b.status == HealthStatus.DEGRADED]

        messages = []
        if unhealthy:
            messages.append(f"{len(unhealthy)} bot(s) unhealthy")
        if degraded:
            messages.append(f"{len(degraded)} bot(s) degraded")

        return "; ".join(messages) if messages else None


class DetectStaleBotsUseCase:
    """Detect bots with stale heartbeats."""

    def __init__(self, threshold_minutes: int = 5):
        self.threshold_minutes = threshold_minutes
        self.threshold_seconds = threshold_minutes * 60

    async def execute(self) -> list[BotHealth]:
        """Find bots with stale heartbeats.

        Returns:
            List of BotHealth for bots that haven't sent heartbeats recently
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=self.threshold_minutes)

        # Get all bot health
        all_healths = await list_all_bot_health_snapshots()

        stale_bots = []
        for health in all_healths:
            # Get latest heartbeat
            latest_heartbeat = await get_latest_heartbeat(
                health.bot_type,
                health.bot_instance_id,
            )

            if latest_heartbeat is None:
                # Never sent a heartbeat - considered stale
                stale_bots.append(health)
                continue

            # Check if heartbeat is stale
            if latest_heartbeat.timestamp < cutoff_time:
                # Update status to unhealthy
                health.status = HealthStatus.UNHEALTHY
                health.last_heartbeat_at = latest_heartbeat.timestamp
                if health.message:
                    health.message += f"; Stale heartbeat (> {self.threshold_minutes}m)"
                else:
                    health.message = f"Stale heartbeat (> {self.threshold_minutes}m)"
                stale_bots.append(health)

        return stale_bots


class GetHealthHistoryUseCase:
    """Get heartbeat history for a bot."""

    async def execute(
        self,
        bot_type: str | None = None,
        instance_id: str | None = None,
        hours: int = 24,
    ) -> list[BotHeartbeat]:
        """Get recent heartbeat history.

        Args:
            bot_type: Optional bot type filter
            instance_id: Optional instance ID filter
            hours: How many hours of history to retrieve

        Returns:
            List of BotHeartbeat entities
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        return await list_recent_heartbeats(
            bot_type=bot_type,
            instance_id=instance_id,
            since=since,
        )
