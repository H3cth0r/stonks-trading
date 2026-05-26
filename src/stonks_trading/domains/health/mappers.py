"""Mappers for health monitoring domain.

Converts between entities and DTOs.
Pure transformation - no business logic.
"""

from stonks_trading.domains.health.dtos import (
    BotHealthListResponse,
    BotHealthResponse,
    HealthCheckResponse,
    HeartbeatResponse,
    StaleBotsResponse,
    SystemHealthResponse,
)
from stonks_trading.domains.health.entities import (
    BotHealth,
    BotHeartbeat,
    HealthStatus,
    SystemHealth,
)


class BotHealthMapper:
    """Map between BotHealth entity and response DTOs."""

    @staticmethod
    def to_response(entity: BotHealth) -> BotHealthResponse:
        """Convert BotHealth entity to response DTO."""
        return BotHealthResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            mode=entity.mode,
            status=entity.status.value,
            last_heartbeat_at=entity.last_heartbeat_at,
            trade_lag_seconds=entity.trade_lag_seconds,
            last_trade_at=entity.last_trade_at,
            position_count=entity.position_count,
            current_drawdown=entity.current_drawdown,
            error_count_1h=entity.error_count_1h,
            message=entity.message,
            uptime_seconds=entity.uptime_seconds,
        )

    @staticmethod
    def to_list_response(entities: list[BotHealth]) -> BotHealthListResponse:
        """Convert list of BotHealth entities to list response."""
        bots = [BotHealthMapper.to_response(e) for e in entities]

        healthy_count = sum(1 for e in entities if e.status == HealthStatus.HEALTHY)
        degraded_count = sum(1 for e in entities if e.status == HealthStatus.DEGRADED)
        unhealthy_count = sum(1 for e in entities if e.status == HealthStatus.UNHEALTHY)

        return BotHealthListResponse(
            bots=bots,
            total=len(bots),
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            unhealthy_count=unhealthy_count,
        )


class SystemHealthMapper:
    """Map between SystemHealth entity and response DTOs."""

    @staticmethod
    def to_response(entity: SystemHealth) -> SystemHealthResponse:
        """Convert SystemHealth entity to response DTO."""
        return SystemHealthResponse(
            status=entity.status.value,
            api_healthy=entity.api_healthy,
            database_healthy=entity.database_healthy,
            duckdb_healthy=entity.duckdb_healthy,
            bots=[BotHealthMapper.to_response(b) for b in entity.bots],
            checked_at=entity.checked_at,
            message=entity.message,
            version=entity.version,
        )


class HeartbeatMapper:
    """Map between BotHeartbeat entity and response DTOs."""

    @staticmethod
    def to_response(entity: BotHeartbeat) -> HeartbeatResponse:
        """Convert BotHeartbeat entity to response DTO."""
        return HeartbeatResponse(
            id=entity.id if entity.id else 0,
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            timestamp=entity.timestamp,
            state_hash=entity.state_hash,
            candle_timestamp=entity.candle_timestamp,
        )


class StaleBotsMapper:
    """Map stale bot detection results to response DTOs."""

    @staticmethod
    def to_response(entities: list[BotHealth], threshold_minutes: int) -> StaleBotsResponse:
        """Convert stale bot list to response DTO."""
        return StaleBotsResponse(
            stale_bots=[BotHealthMapper.to_response(e) for e in entities],
            count=len(entities),
            threshold_minutes=threshold_minutes,
        )


class HealthCheckMapper:
    """Map simple health check to response DTO."""

    @staticmethod
    def to_response(status: str = "healthy") -> HealthCheckResponse:
        """Create simple health check response."""
        return HealthCheckResponse(status=status)
