"""Backtesting domain use cases - BUSINESS LOGIC.

ALL business logic lives here:
- Backtest execution
- Metrics calculation
- Mode handling (backtest vs dry_run_simulation)

Use case rules (per architecture.md):
- Classes with injected dependencies
- No direct SQL or HTTP calls - use repositories/services
- Business logic only - orchestration and decisions
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stonks_trading.domains.backtesting.entities import BacktestConfig, BacktestResult
from stonks_trading.domains.backtesting.services import EquityCurveAnalyzer, MetricsCalculator


@dataclass
class RunBacktestRequest:
    """Request to run a backtest."""

    genome_id: int
    symbol: str
    start_date: datetime
    end_date: datetime
    genome_data: bytes  # Pickled NEAT genome
    initial_capital: float = 10000.0
    config: BacktestConfig | None = None


@dataclass
class BacktestMetrics:
    """Calculated backtest metrics."""

    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    total_trades: int
    win_rate_pct: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_fees: float
    buy_hold_return_pct: float
    alpha: float
    beta: float


class RunBacktestUseCase:
    """Run a backtest simulation.

    BUSINESS LOGIC:
    1. Validate request parameters (business rules)
    2. Load and deserialize genome
    3. Fetch historical data for date range
    4. Execute simulation with appropriate mode
    5. Calculate all metrics (via service)
    6. Save results to DuckDB
    """

    def __init__(
        self,
        metrics_calculator: MetricsCalculator | None = None,
        equity_analyzer: EquityCurveAnalyzer | None = None,
    ):
        """Initialize use case with services.

        Args:
            metrics_calculator: Metrics calculation service
            equity_analyzer: Equity curve analysis service
        """
        self.metrics_calculator = metrics_calculator or MetricsCalculator()
        self.equity_analyzer = equity_analyzer or EquityCurveAnalyzer()

    async def execute(self, request: RunBacktestRequest) -> BacktestResult:
        """Execute backtest use case.

        Args:
            request: Backtest request with parameters

        Returns:
            BacktestResult with all metrics and trades

        Raises:
            ValueError: If validation fails
        """
        # 1. Validate request
        days = (request.end_date - request.start_date).days
        if days < 7:
            raise ValueError("Backtest requires at least 7 days of data")

        if request.initial_capital <= 0:
            raise ValueError("Initial capital must be positive")

        # 2. Load genome (deserialize from bytes)
        import pickle

        genome, neat_config = pickle.loads(request.genome_data)

        # 3. Fetch historical data
        # TODO: Fetch from DuckDB/Parquet based on symbol and date range
        # For now, raise NotImplementedError
        raise NotImplementedError("Data fetching not implemented - need DuckDB integration")

    async def _execute_simulation(
        self,
        genome: Any,
        config: BacktestConfig,
        data: Any,
    ) -> dict[str, Any]:
        """Execute simulation based on mode.

        Args:
            genome: NEAT genome
            config: Backtest configuration
            data: Historical price data

        Returns:
            Dict with simulation results
        """
        # This would use the TradingEnv from NEAT modules
        # Mode determines slippage and latency simulation
        raise NotImplementedError("Simulation execution not implemented")


class CompareBacktestResultsUseCase:
    """Compare two backtest results to verify mode differences."""

    def __init__(
        self,
        metrics_calculator: MetricsCalculator | None = None,
    ):
        """Initialize use case.

        Args:
            metrics_calculator: Metrics calculation service
        """
        self.metrics_calculator = metrics_calculator or MetricsCalculator()

    async def execute(
        self,
        backtest_result: BacktestResult,
        dry_run_result: BacktestResult,
    ) -> dict[str, Any]:
        """Compare backtest vs dry-run simulation results.

        Args:
            backtest_result: Pure backtest result (instant fill)
            dry_run_result: Dry-run simulation result (with slippage)

        Returns:
            Dict with comparison metrics
        """
        if backtest_result.genome_id != dry_run_result.genome_id:
            raise ValueError("Cannot compare results from different genomes")

        if backtest_result.symbol != dry_run_result.symbol:
            raise ValueError("Cannot compare results from different symbols")

        # Calculate differences
        roi_diff = dry_run_result.total_return_pct - backtest_result.total_return_pct
        dd_diff = dry_run_result.max_drawdown_pct - backtest_result.max_drawdown_pct

        # Dry-run should have worse performance
        dry_run_worse = dry_run_result.total_return_pct <= backtest_result.total_return_pct

        return {
            "backtest_roi": backtest_result.total_return_pct,
            "dry_run_roi": dry_run_result.total_return_pct,
            "roi_difference_pct": roi_diff,
            "backtest_max_dd": backtest_result.max_drawdown_pct,
            "dry_run_max_dd": dry_run_result.max_drawdown_pct,
            "dd_difference_pct": dd_diff,
            "dry_run_worse": dry_run_worse,
            "verification_passed": dry_run_worse and abs(roi_diff) >= 0.01,  # At least 1% worse
        }


class GetBacktestHistoryUseCase:
    """Get backtest history for a genome or symbol."""

    async def execute(
        self,
        genome_id: int | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[BacktestResult]:
        """Get backtest history with filters.

        Args:
            genome_id: Filter by genome ID
            symbol: Filter by symbol
            limit: Maximum results

        Returns:
            List of BacktestResult entities
        """
        from stonks_trading.domains.backtesting.repositories import list_backtest_results

        return await list_backtest_results(
            symbol=symbol,
            genome_id=genome_id,
            limit=limit,
        )
