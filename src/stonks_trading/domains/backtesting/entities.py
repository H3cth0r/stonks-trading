"""Backtesting domain entities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BacktestMode(str, Enum):
    """Backtest simulation mode."""

    BACKTEST = "backtest"  # Instant fill, no slippage
    DRY_RUN_SIMULATION = "dry_run_simulation"  # With slippage, latency


@dataclass
class BacktestResult:
    """Result of a backtest run.

    Contains all metrics and trade details from a backtest simulation.
    """

    backtest_id: str
    genome_id: int
    symbol: str
    mode: BacktestMode
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
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def is_profitable(self) -> bool:
        """Check if backtest was profitable."""
        return self.total_return_pct > 0

    def has_acceptable_drawdown(self, max_dd: float = 0.15) -> bool:
        """Check if max drawdown is within acceptable range."""
        return abs(self.max_drawdown_pct) <= max_dd


@dataclass
class BacktestConfig:
    """Configuration for backtest simulation."""

    mode: BacktestMode = BacktestMode.BACKTEST
    initial_capital: float = 10000.0
    fee_rate: float = 0.001
    slippage_bps: int = 0  # Basis points for dry_run_simulation
    latency_ms: int = 0  # Simulated latency for dry_run_simulation
    min_trade_interval: int = 15  # Minimum minutes between trades

    def is_dry_run_simulation(self) -> bool:
        """Check if this is a dry run simulation with slippage."""
        return self.mode == BacktestMode.DRY_RUN_SIMULATION


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
