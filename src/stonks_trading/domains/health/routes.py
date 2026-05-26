"""FastAPI routes for health monitoring domain.

HTTP concerns only - no business logic.
"""

from fastapi import APIRouter, HTTPException, Query

from stonks_trading.domains.health.dtos import (
    BotHealthListResponse,
    BotHealthResponse,
    HealthCheckResponse,
    HealthHistoryResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    StaleBotsResponse,
    SystemHealthResponse,
)
from stonks_trading.domains.health.mappers import (
    BotHealthMapper,
    HealthCheckMapper,
    HeartbeatMapper,
    StaleBotsMapper,
    SystemHealthMapper,
)
from stonks_trading.domains.health.repositories import (
    get_latest_heartbeat as get_latest_heartbeat_repo,
)
from stonks_trading.domains.health.use_cases import (
    DetectStaleBotsUseCase,
    GetBotHealthUseCase,
    GetHealthHistoryUseCase,
    GetSystemHealthUseCase,
    RecordHeartbeatUseCase,
)
from stonks_trading.domains.trading.value_objects import BotContext

# =============================================================================
# Router Factory Pattern (follows existing domains/trading/routes.py)
# =============================================================================


def get_health_router() -> APIRouter:
    """Create and configure health monitoring router.

    Follows the router factory pattern from domains/trading/routes.py.
    """
    router = APIRouter(tags=["health"])

    # -------------------------------------------------------------------------
    # System Health Endpoints
    # -------------------------------------------------------------------------

    @router.get("/health", response_model=SystemHealthResponse)
    async def get_system_health() -> SystemHealthResponse:
        """Get full system health with per-bot status.

        Includes:
        - API health status
        - Database connectivity
        - DuckDB status
        - Per-bot health metrics
        """
        use_case = GetSystemHealthUseCase()
        health = await use_case.execute()
        return SystemHealthMapper.to_response(health)

    @router.get("/health/ready", response_model=HealthCheckResponse)
    async def health_ready() -> HealthCheckResponse:
        """Simple health check for load balancers.

        Returns 200 if API is running. Use /health for detailed status.
        """
        return HealthCheckMapper.to_response("healthy")

    # -------------------------------------------------------------------------
    # Bot Health Endpoints
    # -------------------------------------------------------------------------

    @router.get("/health/bots", response_model=BotHealthListResponse)
    async def list_bot_health() -> BotHealthListResponse:
        """Get health status for all registered bots."""
        use_case = GetSystemHealthUseCase()
        system_health = await use_case.execute()
        return BotHealthMapper.to_list_response(system_health.bots)

    @router.get("/health/bots/{bot_type}/{instance_id}", response_model=BotHealthResponse)
    async def get_bot_health(
        bot_type: str,
        instance_id: str,
    ) -> BotHealthResponse:
        """Get health status for a specific bot instance."""
        use_case = GetBotHealthUseCase()
        health = await use_case.execute(bot_type, instance_id)

        if not health:
            raise HTTPException(
                status_code=404,
                detail=f"Bot {bot_type}/{instance_id} not found",
            )

        return BotHealthMapper.to_response(health)

    @router.get("/health/stale", response_model=StaleBotsResponse)
    async def detect_stale_bots(
        threshold_minutes: int = Query(default=5, ge=1, le=60),
    ) -> StaleBotsResponse:
        """Detect bots with stale heartbeats.

        Args:
            threshold_minutes: How many minutes since last heartbeat before considered stale

        Returns:
            List of bots that haven't sent heartbeats within the threshold
        """
        use_case = DetectStaleBotsUseCase(threshold_minutes=threshold_minutes)
        stale_bots = await use_case.execute()
        return StaleBotsMapper.to_response(stale_bots, threshold_minutes)

    # -------------------------------------------------------------------------
    # Heartbeat Endpoints
    # -------------------------------------------------------------------------

    @router.post("/health/heartbeat", response_model=HeartbeatResponse)
    async def record_heartbeat(request: HeartbeatRequest) -> HeartbeatResponse:
        """Record a heartbeat from a bot.

        Bots should call this endpoint periodically (every 60 seconds)
        to indicate they are healthy and processing data.
        """
        use_case = RecordHeartbeatUseCase()
        context = BotContext(
            bot_type=request.bot_type,
            instance_id=request.bot_instance_id,
        )
        heartbeat = await use_case.execute(
            context=context,
            state_hash=request.state_hash,
            candle_timestamp=request.candle_timestamp,
        )
        return HeartbeatMapper.to_response(heartbeat)

    @router.get("/health/heartbeat/{bot_type}/{instance_id}", response_model=HeartbeatResponse)
    async def get_latest_heartbeat_endpoint(
        bot_type: str,
        instance_id: str,
    ) -> HeartbeatResponse:
        """Get the most recent heartbeat for a bot."""
        heartbeat = await get_latest_heartbeat_repo(bot_type, instance_id)

        if not heartbeat:
            raise HTTPException(
                status_code=404,
                detail=f"No heartbeat found for {bot_type}/{instance_id}",
            )

        return HeartbeatMapper.to_response(heartbeat)

    @router.get("/health/history", response_model=HealthHistoryResponse)
    async def get_health_history(
        bot_type: str | None = None,
        instance_id: str | None = None,
        hours: int = Query(default=24, ge=1, le=168),
    ) -> HealthHistoryResponse:
        """Get heartbeat history for bots.

        Args:
            bot_type: Optional filter by bot type
            instance_id: Optional filter by instance ID
            hours: How many hours of history to retrieve (1-168)

        Returns:
            List of heartbeats matching the filters
        """
        use_case = GetHealthHistoryUseCase()
        heartbeats = await use_case.execute(
            bot_type=bot_type,
            instance_id=instance_id,
            hours=hours,
        )

        return HealthHistoryResponse(
            heartbeats=[HeartbeatMapper.to_response(h) for h in heartbeats],
            count=len(heartbeats),
            bot_type=bot_type,
            bot_instance_id=instance_id,
        )

    return router


# =============================================================================
# Legacy router export for backward compatibility
# =============================================================================

router = get_health_router()
