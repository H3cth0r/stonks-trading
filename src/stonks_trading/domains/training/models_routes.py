"""API routes for model management.

Exposes models as generic resources that can represent genomes,
neural networks, or any trainable artifact.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel

from stonks_trading.domains.trading.entities import Genome
from stonks_trading.domains.trading.repositories import (
    activate_genome,
    get_genome_by_id,
    list_genomes,
)
from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.domains.training.repositories import (
    activate_genome_for_context,
)


class ModelInfoResponse(BaseModel):
    """Generic model information response."""

    id: int
    strategy_type: str
    symbol: str | None
    generation: int | None
    fitness_score: float | None
    roi_validation: float | None
    roi_test: float | None
    max_drawdown: float | None
    num_trades: int | None
    total_return: float | None
    is_active: bool
    created_at: datetime | None
    metadata: dict[str, Any] | None = None


class ModelListResponse(BaseModel):
    """List of models response."""

    models: list[ModelInfoResponse]
    total: int


class ModelActivateRequest(BaseModel):
    """Request to activate a model."""

    bot_type: str | None = None
    bot_instance_id: str | None = None


class ModelActivateResponse(BaseModel):
    """Model activation response."""

    success: bool
    model_id: int
    activated_at: datetime


class ModelDownloadResponse(BaseModel):
    """Model download response."""

    model_id: int
    download_url: str | None
    artifact_data: bytes | None = None


def _genome_to_model_response(
    genome: Genome, strategy_type: str = "neat_swing"
) -> ModelInfoResponse:
    """Convert Genome entity to generic ModelInfoResponse.

    Args:
        genome: Genome entity
        strategy_type: Strategy type for the model

    Returns:
        ModelInfoResponse with genome data
    """
    return ModelInfoResponse(
        id=genome.id or 0,
        strategy_type=strategy_type,
        symbol=genome.symbol.value if genome.symbol else None,
        generation=genome.generation,
        fitness_score=genome.fitness,
        roi_validation=genome.roi_validation,
        roi_test=genome.roi_test,
        max_drawdown=genome.max_drawdown,
        num_trades=genome.trades_count,
        total_return=genome.total_return,
        is_active=genome.is_active,
        created_at=genome.trained_at,
        metadata={
            "model_family": genome.model_family,
            "feature_schema_id": genome.feature_schema_id,
            "trainer_git_sha": genome.trainer_git_sha,
        },
    )


def get_models_router() -> APIRouter:
    """Create models router.

    Returns:
        APIRouter with model management endpoints
    """
    router = APIRouter(prefix="/models", tags=["models"])

    @router.get(
        "/",
        response_model=ModelListResponse,
        responses={
            200: {"description": "List of models"},
        },
    )
    async def list_models_endpoint(
        strategy_type: str | None = Query(None, description="Filter by strategy type"),
        symbol: str | None = Query(None, description="Filter by symbol"),
        is_active: bool | None = Query(None, description="Filter by active status"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
        offset: int = Query(0, ge=0, description="Results to skip"),
    ) -> ModelListResponse:
        """List all models with optional filtering.

        Args:
            strategy_type: Filter by strategy type (e.g., neat_swing)
            symbol: Filter by trading symbol
            is_active: Filter by active status
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of models matching filters
        """
        symbol_obj = Symbol(value=symbol.upper()) if symbol else None

        # Currently only NEAT swing strategy is supported
        # Phase 10D+: Will support multiple strategy types
        genomes = await list_genomes(symbol=symbol_obj, limit=limit)

        # Filter by active status if specified
        if is_active is not None:
            genomes = [g for g in genomes if g.is_active == is_active]

        # Map genomes to model responses
        models = [_genome_to_model_response(g, strategy_type or "neat_swing") for g in genomes]

        return ModelListResponse(models=models, total=len(models))

    @router.get(
        "/{model_id}",
        response_model=ModelInfoResponse,
        responses={
            200: {"description": "Model found"},
            404: {"description": "Model not found"},
        },
    )
    async def get_model_endpoint(
        model_id: int = Path(..., ge=1, description="Model ID"),
    ) -> ModelInfoResponse:
        """Get a specific model by ID.

        Args:
            model_id: Model identifier

        Returns:
            Model information

        Raises:
            HTTPException: If model not found
        """
        genome = await get_genome_by_id(model_id)
        if not genome:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found",
            )

        return _genome_to_model_response(genome)

    @router.post(
        "/{model_id}/activate",
        response_model=ModelActivateResponse,
        responses={
            200: {"description": "Model activated"},
            404: {"description": "Model not found"},
        },
    )
    async def activate_model_endpoint(
        model_id: int = Path(..., ge=1, description="Model ID"),
        request: ModelActivateRequest | None = None,
    ) -> ModelActivateResponse:
        """Activate a model for trading.

        Args:
            model_id: Model identifier
            request: Optional activation context (bot_type, bot_instance_id)

        Returns:
            Activation confirmation

        Raises:
            HTTPException: If model not found
        """
        # Check if model exists
        genome = await get_genome_by_id(model_id)
        if not genome:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found",
            )

        # Activate with or without bot context
        if request and request.bot_type and request.bot_instance_id:
            bot_context = BotContext(
                bot_type=request.bot_type,
                instance_id=request.bot_instance_id,
            )
            success = await activate_genome_for_context(model_id, bot_context)
        else:
            # Global activation
            success = await activate_genome(model_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found",
            )

        return ModelActivateResponse(
            success=True,
            model_id=model_id,
            activated_at=datetime.utcnow(),
        )

    @router.get(
        "/{model_id}/download",
        responses={
            200: {"description": "Model data"},
            404: {"description": "Model not found"},
        },
    )
    async def download_model_endpoint(
        model_id: int = Path(..., ge=1, description="Model ID"),
    ) -> dict[str, Any]:
        """Download model artifact.

        Args:
            model_id: Model identifier

        Returns:
            Model download information

        Raises:
            HTTPException: If model not found
        """
        genome = await get_genome_by_id(model_id)
        if not genome:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found",
            )

        # Return download info - actual download would be from artifact_uri
        return {
            "model_id": model_id,
            "download_url": genome.artifact_uri,
            "format": "pickle"
            if genome.artifact_uri and genome.artifact_uri.endswith(".pkl")
            else "unknown",
        }

    return router
