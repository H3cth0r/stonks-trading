"""FastAPI routes for backtesting domain.

API layer - NOT imported by the bot container.
These routes provide HTTP access to backtesting domain functionality.
"""

from fastapi import APIRouter, HTTPException, Path, Query, status

from stonks_trading.domains.backtesting import use_cases as backtesting_use_cases
from stonks_trading.domains.backtesting.dtos import (
    BacktestComparisonResponse,
    BacktestResultListResponse,
    BacktestResultResponse,
    RunBacktestRequest,
)
from stonks_trading.domains.backtesting.mappers import BacktestResultMapper
from stonks_trading.domains.backtesting.repositories import (
    delete_backtest_result,
    get_backtest_result,
    list_backtest_results,
)
from stonks_trading.domains.backtesting.services import MetricsCalculator
from stonks_trading.domains.trading.repositories import get_genome_by_id

# Create router
router = APIRouter(prefix="/backtest", tags=["backtesting"])


# =============================================================================
# Backtest Routes
# =============================================================================


@router.post(
    "",
    response_model=BacktestResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_backtest_endpoint(
    request: RunBacktestRequest,
) -> BacktestResultResponse:
    """Run a backtest simulation and return results.

    HTTP CONCERNS ONLY:
    - Validate request (Pydantic)
    - Call use case
    - Return response or raise HTTPException

    Business logic lives in RunBacktestUseCase.
    """
    # Create services
    metrics_calculator = MetricsCalculator()

    # Create use case
    use_case = backtesting_use_cases.RunBacktestUseCase(
        metrics_calculator=metrics_calculator,
    )

    # Fetch genome data first
    genome = await get_genome_by_id(request.genome_id)
    if not genome:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome {request.genome_id} not found",
        )
    if not genome.genome_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Genome has no data",
        )

    # Create request for use case
    backtest_request = backtesting_use_cases.RunBacktestRequest(
        genome_id=request.genome_id,
        symbol=request.symbol.upper(),
        start_date=request.start_date,
        end_date=request.end_date,
        genome_data=genome.genome_data,
        initial_capital=request.initial_capital,
    )

    try:
        result = await use_case.execute(backtest_request)
        return BacktestResultMapper.to_response(result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}",
        ) from None


@router.get(
    "/{backtest_id}",
    response_model=BacktestResultResponse,
)
async def get_backtest_result_endpoint(
    backtest_id: str = Path(..., min_length=1),
) -> BacktestResultResponse:
    """Get a specific backtest result by ID."""
    result = await get_backtest_result(backtest_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest result {backtest_id} not found",
        )
    return BacktestResultMapper.to_response(result)


@router.get(
    "",
    response_model=BacktestResultListResponse,
)
async def list_backtest_results_endpoint(
    symbol: str | None = Query(default=None),
    genome_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> BacktestResultListResponse:
    """List backtest results with optional filtering."""
    results = await list_backtest_results(
        symbol=symbol.upper() if symbol else None,
        genome_id=genome_id,
        limit=limit,
        offset=offset,
    )

    result_responses = BacktestResultMapper.to_response_list(results)
    return BacktestResultListResponse(results=result_responses, total=len(result_responses))


@router.post(
    "/compare",
    response_model=BacktestComparisonResponse,
)
async def compare_backtest_results_endpoint(
    backtest_id: str = Query(..., min_length=1),
    dry_run_id: str = Query(..., min_length=1),
) -> BacktestComparisonResponse:
    """Compare backtest vs dry-run simulation results.

    Verifies that dry-run simulation produces worse results than
    pure backtest (due to slippage and latency).
    """
    backtest_result = await get_backtest_result(backtest_id)
    dry_run_result = await get_backtest_result(dry_run_id)

    if not backtest_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest result {backtest_id} not found",
        )
    if not dry_run_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dry-run result {dry_run_id} not found",
        )

    use_case = backtesting_use_cases.CompareBacktestResultsUseCase()
    comparison = await use_case.execute(backtest_result, dry_run_result)

    return BacktestComparisonResponse(**comparison)


@router.delete(
    "/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_backtest_result_endpoint(
    backtest_id: str = Path(..., min_length=1),
) -> None:
    """Delete a backtest result."""
    deleted = await delete_backtest_result(backtest_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest result {backtest_id} not found",
        )
