"""FastAPI routes for bot control domain.

HTTP concerns only - no business logic.
Provides API endpoints for bot lifecycle management.
"""

from fastapi import APIRouter, HTTPException, Path, Query, status

from stonks_trading.domains.botcontrol.dtos import (
    BotStatusResponse,
    ErrorResponse,
    RestartBotResponse,
    RunningBotsResponse,
    StartBotRequest,
    StartBotResponse,
    StopBotResponse,
)
from stonks_trading.domains.botcontrol.mappers import (
    BotProcessMapper,
    BotStatusMapper,
)
from stonks_trading.domains.botcontrol.use_cases import (
    GetBotStatusUseCase,
    ListRunningBotsUseCase,
    RestartBotUseCase,
    StartBotUseCase,
    StopBotUseCase,
)

# =============================================================================
# Router Factory Pattern
# =============================================================================


def get_botcontrol_router() -> APIRouter:
    """Create and configure bot control router.

    Follows the router factory pattern from other domains.
    """
    router = APIRouter(tags=["bot-control"])

    # -------------------------------------------------------------------------
    # Bot Control Endpoints
    # -------------------------------------------------------------------------

    @router.post(
        "/bots/{bot_type}/{instance_id}/start",
        response_model=StartBotResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            404: {"model": ErrorResponse, "description": "Bot not registered"},
            409: {"model": ErrorResponse, "description": "Bot already running"},
        },
    )
    async def start_bot_endpoint(
        bot_type: str = Path(..., description="Bot type (e.g., neat_swing)", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
        request: StartBotRequest | None = None,
    ) -> StartBotResponse:
        """Start a bot instance.

        Spawns a subprocess running the specified bot with given configuration.
        Bot must be registered via POST /api/v1/bots first.
        """
        # Use defaults if request body not provided
        if request is None:
            request = StartBotRequest()

        try:
            use_case = StartBotUseCase()
            bot_process = await use_case.execute(
                bot_type=bot_type,
                instance_id=instance_id,
                symbols=request.symbols,
                mode=request.mode,
                config_path=request.config_path,
            )
            return BotProcessMapper.to_start_response(bot_process)

        except ValueError as e:
            error_msg = str(e)
            if "not registered" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_msg,
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            ) from e
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e

    @router.post(
        "/bots/{bot_type}/{instance_id}/stop",
        response_model=StopBotResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Bot process not found"},
        },
    )
    async def stop_bot_endpoint(
        bot_type: str = Path(..., description="Bot type", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
        graceful: bool = Query(default=True, description="Use graceful shutdown (SIGTERM)"),
    ) -> StopBotResponse:
        """Stop a bot instance.

        Stops the bot subprocess gracefully by default (SIGTERM),
        or forcefully if graceful=False (SIGKILL).
        """
        try:
            use_case = StopBotUseCase()
            bot_process = await use_case.execute(
                bot_type=bot_type,
                instance_id=instance_id,
                graceful=graceful,
            )
            return BotProcessMapper.to_stop_response(bot_process)

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e

    @router.get(
        "/bots/{bot_type}/{instance_id}/status",
        response_model=BotStatusResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Bot not found"},
        },
    )
    async def get_bot_status_endpoint(
        bot_type: str = Path(..., description="Bot type", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
    ) -> BotStatusResponse:
        """Get bot process status.

        Returns comprehensive status including:
        - Process status (running, stopped, error, etc.)
        - Trading mode and uptime
        - Current equity and positions
        - Last seen timestamp
        """
        use_case = GetBotStatusUseCase()
        bot_status = await use_case.execute(
            bot_type=bot_type,
            instance_id=instance_id,
        )

        if not bot_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bot {bot_type}/{instance_id} not found",
            )

        return BotStatusMapper.to_response(bot_status)

    @router.get(
        "/bots/running",
        response_model=RunningBotsResponse,
    )
    async def list_running_bots_endpoint() -> RunningBotsResponse:
        """List all running bots.

        Returns a list of all bots with RUNNING status,
        including their current status and metrics.
        """
        use_case = ListRunningBotsUseCase()
        statuses = await use_case.execute()
        return BotStatusMapper.to_list_response(statuses)

    @router.post(
        "/bots/{bot_type}/{instance_id}/restart",
        response_model=RestartBotResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            404: {"model": ErrorResponse, "description": "Bot not found"},
        },
    )
    async def restart_bot_endpoint(
        bot_type: str = Path(..., description="Bot type", min_length=1),
        instance_id: str = Path(..., description="Bot instance ID", min_length=1),
        request: StartBotRequest | None = None,
    ) -> RestartBotResponse:
        """Restart a bot instance.

        Stops the bot if running, then starts it again.
        Uses existing configuration if request body not provided.
        """
        try:
            use_case = RestartBotUseCase()
            bot_process = await use_case.execute(
                bot_type=bot_type,
                instance_id=instance_id,
                symbols=request.symbols if request else None,
                mode=request.mode if request else None,
                config_path=request.config_path if request else None,
            )
            return BotProcessMapper.to_restart_response(bot_process)

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    return router


# =============================================================================
# Legacy router export for backward compatibility
# =============================================================================

router = get_botcontrol_router()
