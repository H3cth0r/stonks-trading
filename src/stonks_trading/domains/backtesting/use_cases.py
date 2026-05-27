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

import pickle
from datetime import datetime
from typing import Any

import neat
import pandas as pd

from stonks_trading.domains.backtesting.entities import (
    BacktestConfig,
    BacktestResult,
    RunBacktestRequest,
)
from stonks_trading.domains.backtesting.repositories import (
    list_backtest_results,
    save_backtest_result,
)
from stonks_trading.domains.backtesting.services import EquityCurveAnalyzer, MetricsCalculator
from stonks_trading.domains.strategies.neat_swing.config_builder import create_default_config
from stonks_trading.domains.strategies.neat_swing.features import engineer_features
from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


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

    COLUMN_MAPPING = {
        "timestamp": "Datetime",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

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
        days = (request.end_date - request.start_date).days
        if days < 7:
            raise ValueError("Backtest requires at least 7 days of data")

        if request.initial_capital <= 0:
            raise ValueError("Initial capital must be positive")

        genome, _ = pickle.loads(request.genome_data)
        neat_config = create_default_config()

        db_client = DuckDBClient()
        db_client.connect()

        try:
            symbol_vo = Symbol(value=request.symbol)
            raw_data = db_client.get_data_range(
                symbol=symbol_vo,
                start=request.start_date,
                end=request.end_date,
            )

            if not raw_data:
                raise ValueError(f"No data found for {request.symbol} in date range")

            df = self._raw_data_to_dataframe(raw_data)
            df = self._ensure_features(df)

        finally:
            db_client.close()

        config = request.config or BacktestConfig(mode="backtest")
        simulation_results = await self._execute_simulation(
            genome=genome,
            config=config,
            data=df,
            neat_config=neat_config,
            initial_capital=request.initial_capital,
        )

        equity_curve = simulation_results["equity_curve"]
        metrics = self.metrics_calculator.calculate_all_metrics(
            equity_curve=equity_curve,
            trades=simulation_results["trades"],
            initial_capital=request.initial_capital,
            market_prices=simulation_results["market_prices"],
        )

        backtest_result = BacktestResult(
            genome_id=request.genome_id,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            mode=config.mode,
            initial_capital=request.initial_capital,
            final_equity=equity_curve[-1] if equity_curve else request.initial_capital,
            total_return_pct=metrics["total_return_pct"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            sortino_ratio=metrics["sortino_ratio"],
            total_trades=len(simulation_results["trades"]),
            win_rate_pct=metrics["win_rate_pct"],
            avg_win=metrics["avg_win"],
            avg_loss=metrics["avg_loss"],
            profit_factor=metrics["profit_factor"],
            total_fees=metrics["total_fees"],
            buy_hold_return_pct=metrics["buy_hold_return_pct"],
            alpha=metrics["alpha"],
            beta=metrics["beta"],
            equity_curve=equity_curve,
            trades=simulation_results["trades"],
            created_at=datetime.utcnow(),
        )

        await save_backtest_result(backtest_result)

        return backtest_result

    def _raw_data_to_dataframe(self, raw_data: list[dict]) -> pd.DataFrame:
        """Convert raw data to DataFrame."""
        df = pd.DataFrame(raw_data)
        df = df.rename(columns=self.COLUMN_MAPPING)

        if "Datetime" in df.columns:
            df.set_index("Datetime", inplace=True)

        return df

    REQUIRED_FEATURES = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]

    def _ensure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure required features exist."""
        if all(feat in df.columns for feat in self.REQUIRED_FEATURES):
            return df

        return engineer_features(df)

    async def _execute_simulation(
        self,
        genome: Any,
        config: BacktestConfig,
        data: pd.DataFrame,
        neat_config: Any,
        initial_capital: float,
    ) -> dict[str, Any]:
        """Execute simulation based on mode.

        Args:
            genome: NEAT genome
            config: Backtest configuration
            data: Historical price data DataFrame
            neat_config: NEAT configuration
            initial_capital: Starting capital

        Returns:
            Dict with simulation results
        """
        slippage_bps = 5 if config.mode == "dry_run" else 0

        env = TradingEnv(
            data=data,
            fee_rate=config.fee_rate if hasattr(config, "fee_rate") else 0.001,
            slippage_bps=slippage_bps,
            mode=config.mode,
            initial_capital=initial_capital,
            min_trade_interval=config.min_trade_interval
            if hasattr(config, "min_trade_interval")
            else 15,
            decision_threshold=config.decision_threshold
            if hasattr(config, "decision_threshold")
            else 0.6,
        )

        net = neat.nn.RecurrentNetwork.create(genome, neat_config)

        equity_curve = []
        env.reset()

        for i in range(len(data)):
            state = env.get_state(i)
            action = net.activate(state)
            equity = env.step(i, tuple(action))
            equity_curve.append(equity)

        market_prices = data["Close"].values

        trades = [
            {
                "step": t.step,
                "type": t.trade_type,
                "price": t.price,
                "timestamp": t.timestamp.isoformat()
                if hasattr(t.timestamp, "isoformat")
                else str(t.timestamp),
                "fee_paid": t.fee_paid,
                "quantity": t.quantity,
            }
            for t in env.trades
        ]

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "market_prices": market_prices,
            "final_equity": equity_curve[-1] if equity_curve else initial_capital,
            "max_drawdown": env.max_drawdown,
            "total_trades": len(env.trades),
        }


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
        return await list_backtest_results(
            symbol=symbol,
            genome_id=genome_id,
            limit=limit,
        )
