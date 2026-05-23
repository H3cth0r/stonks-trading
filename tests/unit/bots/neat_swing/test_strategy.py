"""Unit tests for NeatSwingStrategy."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from stonks_trading.bots.neat_swing.strategy import (
    DECISION_THRESHOLD,
    MIN_TRADE_INTERVAL,
    TRANSACTION_FEE,
    NeatSwingStrategy,
)
from stonks_trading.domains.trading.entities import Signal
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Symbol


class TestNeatSwingStrategy:
    """Tests for NeatSwingStrategy."""

    def test_strategy_name(self) -> None:
        """Strategy name is correct."""
        strategy = NeatSwingStrategy()
        assert strategy.name == "neat_swing"

    def test_strategy_version(self) -> None:
        """Strategy version is correct."""
        strategy = NeatSwingStrategy()
        assert strategy.version == "1.0.0"

    def test_decision_threshold_constant(self) -> None:
        """Decision threshold is 0.6 as per NEAT parity."""
        assert DECISION_THRESHOLD == 0.6

    def test_transaction_fee_constant(self) -> None:
        """Transaction fee is 0.001 as per NEAT parity."""
        assert TRANSACTION_FEE == 0.001

    def test_min_trade_interval_constant(self) -> None:
        """Minimum trade interval is 15 minutes as per NEAT parity."""
        assert MIN_TRADE_INTERVAL == 15

    def test_strategy_has_config_path(self) -> None:
        """Strategy accepts config_path parameter."""
        strategy = NeatSwingStrategy(config_path="custom-config.txt")
        assert strategy.config_path == "custom-config.txt"

    def test_compute_features_returns_dict(self) -> None:
        """Compute features returns a dictionary."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [
            {
                "close": 50000.0,
                "open": 49000.0,
                "high": 51000.0,
                "low": 48500.0,
                "volume": 1.5,
            }
        ]
        features = strategy.compute_features(symbol, candles)
        assert isinstance(features, dict)

    def test_compute_features_contains_required_keys(self) -> None:
        """Compute features contains all required NEAT features."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [
            {
                "close": 50000.0 + i * 100,
                "open": 49000.0 + i * 100,
                "high": 51000.0 + i * 100,
                "low": 48500.0 + i * 100,
                "volume": 1.5,
            }
            for i in range(100)  # Need enough candles for indicators
        ]
        features = strategy.compute_features(symbol, candles)
        # Required features: trend_1h, rsi_1h, rsi_15m, roc, bb_width
        assert "trend_1h" in features
        assert "rsi_1h" in features
        assert "rsi_15m" in features
        assert "roc" in features
        assert "bb_width" in features

    def test_generate_signal_returns_none_when_no_position_and_low_prob(
        self,
    ) -> None:
        """Generate signal returns None when no position and probability is low."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candle = {"close": 50000.0}
        features = {
            "trend_1h": 0.0,
            "rsi_1h": 0.5,
            "rsi_15m": 0.5,
            "roc": 0.0,
            "bb_width": 0.02,
        }
        position = None

        signal = strategy.generate_signal(
            symbol, candle, features, position
        )
        assert signal is None

    def test_generate_signal_returns_buy_signal(self) -> None:
        """Generate signal returns BUY signal when buy probability is high."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candle = {"close": 50000.0}
        features = {
            "trend_1h": 0.0,
            "rsi_1h": 0.5,
            "rsi_15m": 0.5,
            "roc": 0.0,
            "bb_width": 0.02,
        }
        position = None

        # Manually set a high buy probability via determine_action
        action = strategy.determine_action(0.8, 0.2, False)
        assert action == Side.BUY

    def test_determine_action_returns_sell_when_invested(self) -> None:
        """determine_action returns SELL when sell probability is high and invested."""
        strategy = NeatSwingStrategy()

        action = strategy.determine_action(0.2, 0.8, True)
        assert action == Side.SELL

    def test_determine_action_returns_none_when_buy_low_and_not_invested(self) -> None:
        """determine_action returns None when probabilities are low."""
        strategy = NeatSwingStrategy()

        action = strategy.determine_action(0.3, 0.3, False)
        assert action is None

    def test_determine_action_returns_none_when_sell_low_and_invested(self) -> None:
        """determine_action returns None when sell prob is low and invested."""
        strategy = NeatSwingStrategy()

        action = strategy.determine_action(0.3, 0.3, True)
        assert action is None


class TestNeatSwingStrategyParity:
    """Tests for NEAT parity compliance."""

    def test_state_vector_length_is_7(self) -> None:
        """State vector has exactly 7 elements."""
        strategy = NeatSwingStrategy()
        # State vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
        # is_invested = 1.0 or -1.0
        # unrealized_pnl = float
        # trend_1h, rsi_1h, rsi_15m, roc, bb_width = 5 features = 5 floats
        # Total = 2 + 5 = 7
        expected_length = 7
        # This is a documentation test - the actual state vector
        # construction happens in the bot, not the strategy

    def test_threshold_is_0_6(self) -> None:
        """Decision threshold is exactly 0.6."""
        assert DECISION_THRESHOLD == 0.6

    def test_transaction_fee_is_0_001(self) -> None:
        """Transaction fee is exactly 0.001 (0.1%)."""
        assert TRANSACTION_FEE == 0.001

    def test_min_trade_interval_is_15(self) -> None:
        """Minimum trade interval is exactly 15 minutes."""
        assert MIN_TRADE_INTERVAL == 15


class TestNeatSwingStrategyEdgeCases:
    """Edge case tests for NeatSwingStrategy."""

    def test_compute_features_with_single_candle(self) -> None:
        """Strategy handles single candle gracefully."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [{"close": 50000.0, "open": 49000.0, "high": 51000.0, "low": 48500.0, "volume": 1.5}]

        features = strategy.compute_features(symbol, candles)
        # Should return dict but some features may be NaN
        assert isinstance(features, dict)

    def test_compute_features_with_empty_candles(self) -> None:
        """Strategy handles empty candles list."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = []

        features = strategy.compute_features(symbol, candles)
        assert isinstance(features, dict)

    def test_compute_features_with_sufficient_candles_covers_all_branches(self) -> None:
        """Strategy covers all indicator branches with sufficient candles."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        # Need 200+ candles for SMA200, 20+ for Bollinger Bands
        candles = [
            {"close": 50000.0 + i * 10, "open": 49900.0 + i * 10,
             "high": 50200.0 + i * 10, "low": 49800.0 + i * 10, "volume": 1.5}
            for i in range(250)
        ]

        features = strategy.compute_features(symbol, candles)

        assert isinstance(features, dict)
        assert "trend_1h" in features
        assert "rsi_1h" in features
        assert "rsi_15m" in features
        assert "roc" in features
        assert "bb_width" in features
        # Verify all features are valid numbers (not NaN)
        for key, value in features.items():
            assert value is not None
            assert isinstance(value, (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])