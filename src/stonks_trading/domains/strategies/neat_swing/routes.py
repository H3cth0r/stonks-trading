"""API routes for NEAT swing strategy.

Uses router factory pattern for clean API structure.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from stonks_trading.domains.strategies.neat_swing.repositories import (
    activate_neat_model,
    get_active_neat_model,
    get_neat_model_by_id,
    list_neat_models,
)


def get_neat_router() -> APIRouter:
    """Create NEAT strategy router.

    Returns:
        APIRouter with NEAT strategy endpoints
    """
    router = APIRouter(prefix="/neat", tags=["neat"])

    class NeatModelResponse(BaseModel):
        id: int
        symbol: str | None
        generation: int
        fitness_score: float | None
        roi_validation: float | None
        roi_test: float | None
        max_drawdown: float | None
        num_trades: int | None
        total_return: float | None
        is_active: bool
        created_at: datetime

    class ActivationResponse(BaseModel):
        success: bool
        model_id: int

    @router.get("/models", response_model=list[NeatModelResponse])
    async def list_models(
        symbol: str | None = Query(None),
        is_active: bool | None = Query(None),
        limit: int = Query(100, le=500),
    ) -> list[NeatModelResponse]:
        """List NEAT models with optional filters."""
        models = await list_neat_models(symbol=symbol, is_active=is_active, limit=limit)
        return [
            NeatModelResponse(
                id=m.id or 0,
                symbol=m.symbol,
                generation=m.generation,
                fitness_score=m.fitness_score,
                roi_validation=m.roi_validation,
                roi_test=m.roi_test,
                max_drawdown=m.max_drawdown,
                num_trades=m.num_trades,
                total_return=m.total_return,
                is_active=m.is_active(),
                created_at=m.created_at,
            )
            for m in models
        ]

    @router.get("/models/active", response_model=NeatModelResponse | None)
    async def get_active(
        symbol: str = Query(...),
        bot_type: str | None = Query(None),
        bot_instance_id: str | None = Query(None),
    ) -> NeatModelResponse | None:
        """Get active NEAT model for symbol."""
        model = await get_active_neat_model(symbol, bot_type, bot_instance_id)
        if not model:
            return None
        return NeatModelResponse(
            id=model.id or 0,
            symbol=model.symbol,
            generation=model.generation,
            fitness_score=model.fitness_score,
            roi_validation=model.roi_validation,
            roi_test=model.roi_test,
            max_drawdown=model.max_drawdown,
            num_trades=model.num_trades,
            total_return=model.total_return,
            is_active=model.is_active(),
            created_at=model.created_at,
        )

    @router.get("/models/{model_id}", response_model=NeatModelResponse)
    async def get_model(model_id: int) -> NeatModelResponse:
        """Get NEAT model by ID."""
        model = await get_neat_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        return NeatModelResponse(
            id=model.id or 0,
            symbol=model.symbol,
            generation=model.generation,
            fitness_score=model.fitness_score,
            roi_validation=model.roi_validation,
            roi_test=model.roi_test,
            max_drawdown=model.max_drawdown,
            num_trades=model.num_trades,
            total_return=model.total_return,
            is_active=model.is_active(),
            created_at=model.created_at,
        )

    @router.post("/models/{model_id}/activate", response_model=ActivationResponse)
    async def activate_model(model_id: int) -> ActivationResponse:
        """Activate a NEAT model."""
        success = await activate_neat_model(model_id)
        if not success:
            raise HTTPException(status_code=404, detail="Model not found")
        return ActivationResponse(success=True, model_id=model_id)

    return router
