"""Unit tests for NeatSwingState."""

from datetime import datetime

import pytest

from stonks_trading.bots.neat_swing.state import NeatSwingState


class TestNeatSwingState:
    """Tests for NeatSwingState."""

    def test_state_initialization(self) -> None:
        """State initializes with correct defaults."""
        state = NeatSwingState()
        assert state.trades_today == 0
        assert state.last_trade_time is None
        assert state.peak_equity == 10000.0
        assert state.current_equity == 10000.0
        assert state.daily_loss_pct == 0.0
        assert state.in_safe_mode is False

    def test_state_created_at_initialized(self) -> None:
        """State has created_at timestamp."""
        state = NeatSwingState()
        assert state.created_at is not None
        assert isinstance(state.created_at, datetime)

    def test_state_updated_at_initialized(self) -> None:
        """State has updated_at timestamp."""
        state = NeatSwingState()
        assert state.updated_at is not None
        assert isinstance(state.updated_at, datetime)

    def test_record_trade_increments_count(self) -> None:
        """record_trade increments trades_today."""
        state = NeatSwingState()
        assert state.trades_today == 0
        state.record_trade()
        assert state.trades_today == 1

    def test_record_trade_sets_last_trade_time(self) -> None:
        """record_trade sets last_trade_time."""
        state = NeatSwingState()
        assert state.last_trade_time is None
        state.record_trade()
        assert state.last_trade_time is not None

    def test_update_equity_increases_peak(self) -> None:
        """update_equity updates current_equity and peak_equity."""
        state = NeatSwingState()
        state.peak_equity = 10000.0

        state.update_equity(11000.0)

        assert state.current_equity == 11000.0
        assert state.peak_equity == 11000.0

    def test_update_equity_maintains_peak_on_drawdown(self) -> None:
        """update_equity keeps peak_equity on drawdown."""
        state = NeatSwingState()
        state.peak_equity = 10000.0

        state.update_equity(9000.0)

        assert state.current_equity == 9000.0
        assert state.peak_equity == 10000.0

    def test_reset_daily_metrics(self) -> None:
        """reset_daily_metrics resets daily counters."""
        state = NeatSwingState()
        state.trades_today = 10
        state.daily_loss_pct = 0.05
        state.in_safe_mode = True

        state.reset_daily_metrics()

        assert state.trades_today == 0
        assert state.daily_loss_pct == 0.0
        assert state.in_safe_mode is False


class TestNeatSwingStateSerialization:
    """Tests for state serialization."""

    def test_to_dict_returns_dict(self) -> None:
        """to_dict returns a dictionary."""
        state = NeatSwingState()
        data = state.to_dict()
        assert isinstance(data, dict)

    def test_to_dict_contains_positions(self) -> None:
        """to_dict includes positions."""
        state = NeatSwingState()
        data = state.to_dict()
        assert "positions" in data

    def test_to_dict_contains_trades_today(self) -> None:
        """to_dict includes trades_today."""
        state = NeatSwingState()
        data = state.to_dict()
        assert "trades_today" in data

    def test_to_dict_contains_equity(self) -> None:
        """to_dict includes equity fields."""
        state = NeatSwingState()
        data = state.to_dict()
        assert "peak_equity" in data
        assert "current_equity" in data

    def test_from_dict_returns_state(self) -> None:
        """from_dict creates a state instance."""
        data = {
            "positions": {},
            "trades_today": 5,
            "last_trade_time": None,
            "peak_equity": 11000.0,
            "current_equity": 10500.0,
            "daily_loss_pct": 0.02,
            "in_safe_mode": False,
            "last_realized_loss_time": None,
        }
        state = NeatSwingState.from_dict(data)
        assert state is not None
        assert state.trades_today == 5
        assert state.current_equity == 10500.0

    def test_roundtrip_serialization(self) -> None:
        """State survives to_dict -> from_dict roundtrip."""
        state = NeatSwingState()
        state.trades_today = 7
        state.current_equity = 12000.0
        state.peak_equity = 12500.0

        data = state.to_dict()
        recovered = NeatSwingState.from_dict(data)

        assert recovered.trades_today == state.trades_today
        assert recovered.current_equity == state.current_equity
        assert recovered.peak_equity == state.peak_equity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
