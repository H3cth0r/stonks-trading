"""Backtesting domain DTOs.

Pydantic models for API request/response validation.
All responses inherit from BaseResponse.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from stonks_trading.shared.serializers import BaseResponse


class RunBacktestRequest(BaseModel):
    """Request to run a backtest (Phase 10D - generic via strategy_type)."""

    strategy_type: str = Field(default="neat_swing", min_length=1, max_length=50)
    model_id: int = Field(..., gt=0)
    symbol: str = Field(..., min_length=1, max_length=20)
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(default=10000.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0, le=0.01)
    slippage_bps: int = Field(default=0, ge=0, le=100)
    mode: str = Field(default="backtest", pattern="^(backtest|dry_run_simulation)$")
    config: dict[str, Any] = Field(default_factory=dict)


class BacktestResultResponse(BaseResponse):
    """Backtest result response."""

    backtest_id: str
    model_id: int  # Phase 10H: Renamed from genome_id
    symbol: str
    mode: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_equity: float
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
    created_at: datetime


class BacktestResultListResponse(BaseResponse):
    """List of backtest results."""

    results: list[BacktestResultResponse] = Field(default_factory=list)
    total: int = 0


class BacktestComparisonResponse(BaseResponse):
    """Comparison of backtest vs dry-run simulation results."""

    backtest_roi: float
    dry_run_roi: float
    roi_difference_pct: float
    backtest_max_dd: float
    dry_run_max_dd: float
    dd_difference_pct: float
    dry_run_worse: bool
    verification_passed: bool


class BacktestMetricsResponse(BaseResponse):
    """Backtest metrics summary."""

    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate_pct: float
    profit_factor: float
