"""API routes for strategy domain.

Uses router factory pattern for clean API structure.
"""

from fastapi import APIRouter, HTTPException

from stonks_trading.domains.strategies.dtos import (
    ConfigFieldResponse,
    ConfigSchemaResponse,
    StrategyInfoResponse,
    StrategyListResponse,
)


def get_strategies_router() -> APIRouter:
    """Create strategies router.

    Returns:
        APIRouter with strategy management endpoints
    """
    router = APIRouter(prefix="/strategies", tags=["strategies"])

    # Map strategy types to friendly names and trainability
    strategy_meta: dict[str, tuple[str, bool]] = {
        "neat_swing": ("NEAT Swing Trading", True),
    }

    @router.get(
        "/",
        response_model=StrategyListResponse,
        responses={404: {"description": "Strategies found"}},
    )
    async def list_strategies() -> StrategyListResponse:
        """List all available strategies.

        Returns:
            List of strategy information
        """
        strategies = []
        for strategy_type, (name, is_trainable) in strategy_meta.items():
            strategies.append(
                StrategyInfoResponse(
                    type=strategy_type,
                    name=name,
                    is_trainable=is_trainable,
                )
            )
        return StrategyListResponse(strategies=strategies)

    @router.get(
        "/{strategy_type}/config-schema",
        response_model=ConfigSchemaResponse,
        responses={404: {"description": "Strategy type not found"}},
    )
    async def get_config_schema(strategy_type: str) -> ConfigSchemaResponse:
        """Get configuration schema for a strategy.

        Args:
            strategy_type: Strategy type identifier

        Returns:
            Configuration schema with fields and defaults

        Raises:
            HTTPException: If strategy type not found
        """
        if strategy_type not in strategy_meta:
            raise HTTPException(status_code=404, detail="Strategy type not found")

        # Build schema based on strategy type
        if strategy_type == "neat_swing":
            config_fields = [
                ConfigFieldResponse(name="pop_size", type="integer", default=150),
                ConfigFieldResponse(name="generations", type="integer", default=30),
                ConfigFieldResponse(name="fee_rate", type="float", default=0.001),
                ConfigFieldResponse(name="decision_threshold", type="float", default=0.6),
                ConfigFieldResponse(name="min_trade_interval", type="integer", default=15),
            ]
        else:
            config_fields = []

        return ConfigSchemaResponse(
            strategy_type=strategy_type,
            config_fields=config_fields,
        )

    return router
