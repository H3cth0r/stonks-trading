"""Tests for backtesting domain entities."""

from datetime import datetime

import pytest

from stonks_trading.domains.backtesting.entities import (
    BacktestConfig,
    BacktestMode,
    BacktestResult,
    BacktestMetrics,
)


class TestBacktestMode:
    """Tests for BacktestMode enum."""

    def test_backtest_mode_values(self) -> None:
        """Test enum values."""
        assert BacktestMode.BACKTEST == "backtest"
        assert BacktestMode.DRY_RUN_SIMULATION == "dry_run_simulation"


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = BacktestConfig()

        assert config.mode == BacktestMode.BACKTEST
        assert config.initial_capital == 10000.0
        assert config.fee_rate == 0.001
        assert config.slippage_bps == 0
        assert config.min_trade_interval == 15

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = BacktestConfig(
            mode=BacktestMode.DRY_RUN_SIMULATION,
            initial_capital=5000.0,
            fee_rate=0.002,
            slippage_bps=5,
            min_trade_interval=10,
        )

        assert config.mode == BacktestMode.DRY_RUN_SIMULATION
        assert config.initial_capital == 5000.0
        assert config.fee_rate == 0.002
        assert config.slippage_bps == 5
        assert config.min_trade_interval == 10

    def test_is_dry_run_simulation(self) -> None:
        """Test dry run check."""
        backtest_config = BacktestConfig(mode=BacktestMode.BACKTEST)
        assert backtest_config.is_dry_run_simulation() is False

        dry_run_config = BacktestConfig(mode=BacktestMode.DRY_RUN_SIMULATION)
        assert dry_run_config.is_dry_run_simulation() is True


class TestBacktestResult:
    """Tests for BacktestResult."""

    def test_is_profitable(self) -> None:
        """Test profit check."""
        result = BacktestResult(
            backtest_id="test-1",
            genome_id=1,
            symbol="BTC_USD",
            mode=BacktestMode.BACKTEST,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow(),
            initial_capital=10000.0,
            final_equity=11000.0,
            total_return_pct=10.0,
            annualized_return_pct=10.0,
            max_drawdown_pct=-5.0,
            sharpe_ratio=1.5,
            sortino_ratio=1.5,
            total_trades=10,
            win_rate_pct=60.0,
            avg_win=100.0,
            avg_loss=50.0,
            profit_factor=2.0,
            total_fees=10.0,
            buy_hold_return_pct=8.0,
            alpha=2.0,
            beta=0.8,
        )

        assert result.is_profitable() is True

        # Unprofitable result
        result.total_return_pct = -5.0
        assert result.is_profitable() is False

    def test_has_acceptable_drawdown(self) -> None:
        """Test drawdown check."""
        result = BacktestResult(
            backtest_id="test-1",
            genome_id=1,
            symbol="BTC_USD",
            mode=BacktestMode.BACKTEST,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow(),
            initial_capital=10000.0,
            final_equity=11000.0,
            total_return_pct=10.0,
            annualized_return_pct=10.0,
            max_drawdown_pct=-10.0,
            sharpe_ratio=1.5,
            sortino_ratio=1.5,
            total_trades=10,
            win_rate_pct=60.0,
            avg_win=100.0,
            avg_loss=50.0,
            profit_factor=2.0,
            total_fees=10.0,
            buy_hold_return_pct=8.0,
            alpha=2.0,
            beta=0.8,
        )

        # Drawdown within acceptable range (15%)
        assert result.has_acceptable_drawdown(max_dd=15.0) is True

        # Drawdown exceeding threshold
        result.max_drawdown_pct = -20.0
        assert result.has_acceptable_drawdown(max_dd=15.0) is False

        # Custom threshold (25%)
        assert result.has_acceptable_drawdown(max_dd=25.0) is True


class TestBacktestMetrics:
    """Tests for BacktestMetrics."""

    def test_metrics_creation(self) -> None:
        """Test metrics dataclass creation."""
        metrics = BacktestMetrics(
            total_return_pct=10.0,
            annualized_return_pct=10.0,
            max_drawdown_pct=-5.0,
            sharpe_ratio=1.5,
            sortino_ratio=1.5,
            total_trades=10,
            win_rate_pct=60.0,
            avg_win=100.0,
            avg_loss=50.0,
            profit_factor=2.0,
            total_fees=10.0,
            buy_hold_return_pct=8.0,
            alpha=2.0,
            beta=0.8,
        )

        assert metrics.total_return_pct == 10.0
        assert metrics.sharpe_ratio == 1.5
        assert metrics.total_trades == 10
