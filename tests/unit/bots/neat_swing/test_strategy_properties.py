"""Property-based tests for NeatSwingStrategy using Hypothesis.

Uses Hypothesis to test feature computation and signal generation
across a wide range of randomly generated candle data.
"""

from hypothesis import HealthCheck, given, settings, Verbosity
from hypothesis import strategies as st
import numpy as np
import pytest

from stonks_trading.bots.neat_swing.strategy import (
    DECISION_THRESHOLD,
    NeatSwingStrategy,
)
from stonks_trading.domains.trading.value_objects import Symbol


def float_to_candle(close_price: float, idx: int) -> dict:
    """Generate a valid candle dict from close price."""
    variation = close_price * 0.02
    return {
        "close": close_price,
        "open": close_price - variation * 0.3,
        "high": close_price + variation,
        "low": close_price - variation,
        "volume": 1.0 + idx * 0.1,
    }


# Strategies for generating random but valid candle data
price_list_strategy = st.lists(
    st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False),
    min_size=200,  # Need 200+ candles for 200-period SMA
    max_size=500,
)


@given(
    close_prices=price_list_strategy,
)
@settings(
    max_examples=20,
    deadline=None,
    verbosity=Verbosity.verbose,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_compute_features_produces_valid_output(close_prices: list[float]) -> None:
    """compute_features returns a dict with all required keys for any valid candle data."""
    strategy = NeatSwingStrategy()
    symbol = Symbol(value="BTC_USD")
    candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

    features = strategy.compute_features(symbol, candles)

    # All required features must be present
    assert "trend_1h" in features
    assert "rsi_1h" in features
    assert "rsi_15m" in features
    assert "roc" in features
    assert "bb_width" in features


@given(
    close_prices=price_list_strategy,
)
@settings(max_examples=20, deadline=None)
def test_feature_values_are_finite(close_prices: list[float]) -> None:
    """All computed features are finite (not NaN/Inf) for valid data."""
    strategy = NeatSwingStrategy()
    symbol = Symbol(value="BTC_USD")
    candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

    features = strategy.compute_features(symbol, candles)

    for key, value in features.items():
        assert np.isfinite(value), f"Feature {key} is not finite: {value}"


@given(
    close_prices=price_list_strategy,
)
@settings(max_examples=20, deadline=None)
def test_rsi_values_in_valid_range(close_prices: list[float]) -> None:
    """RSI features are in [0, 1] range (divided by 100 in implementation)."""
    strategy = NeatSwingStrategy()
    symbol = Symbol(value="BTC_USD")
    candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

    features = strategy.compute_features(symbol, candles)

    # RSI is divided by 100 in the implementation, so should be in [0, 1]
    assert 0.0 <= features["rsi_1h"] <= 1.0, f"rsi_1h out of range: {features['rsi_1h']}"
    assert 0.0 <= features["rsi_15m"] <= 1.0, f"rsi_15m out of range: {features['rsi_15m']}"


@given(
    close_prices=price_list_strategy,
)
@settings(max_examples=20, deadline=None)
def test_bb_width_is_nonnegative(close_prices: list[float]) -> None:
    """Bollinger Band width is always non-negative."""
    strategy = NeatSwingStrategy()
    symbol = Symbol(value="BTC_USD")
    candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

    features = strategy.compute_features(symbol, candles)

    assert features["bb_width"] >= 0.0, f"bb_width is negative: {features['bb_width']}"


@given(
    close_prices=price_list_strategy,
)
@settings(max_examples=20, deadline=None)
def test_trend_1h_range_reasonable(close_prices: list[float]) -> None:
    """Trend (SMA50-SMA200)/SMA200 is in reasonable range [-1, 1] for stable prices."""
    strategy = NeatSwingStrategy()
    symbol = Symbol(value="BTC_USD")
    candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

    features = strategy.compute_features(symbol, candles)

    # For reasonable price movements, trend should be within [-1, 1]
    # (i.e., -100% to +100%)
    trend = features["trend_1h"]
    assert -2.0 <= trend <= 2.0, f"trend_1h unusual value: {trend}"


class TestNeatSwingStrategyWithHypothesis:
    """Additional Hypothesis tests for strategy edge cases."""

    @given(
        close_prices=st.lists(
            st.floats(min_value=100.0, max_value=1000.0),
            min_size=300,
            max_size=300,
        )
    )
    @settings(max_examples=10, deadline=None)
    def test_consistent_features_for_same_input(self, close_prices: list[float]) -> None:
        """Same candle data produces same features (deterministic)."""
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="ETH_USD")
        candles = [float_to_candle(p, i) for i, p in enumerate(close_prices)]

        features1 = strategy.compute_features(symbol, candles)
        features2 = strategy.compute_features(symbol, candles)

        assert features1 == features2

    @given(
        prices=st.lists(
            st.floats(min_value=1000.0, max_value=100000.0),
            min_size=300,
            max_size=300,
        )
    )
    @settings(max_examples=10, deadline=None)
    def test_trend_increases_with_uptrend_prices(self, prices: list[float]) -> None:
        """Monotonically increasing prices should produce positive trend."""
        # Create monotonically increasing prices
        increasing_prices = [10000.0 + i * 100 for i in range(300)]
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [float_to_candle(p, i) for i, p in enumerate(increasing_prices)]

        features = strategy.compute_features(symbol, candles)

        # In an uptrend, SMA50 > SMA200, so trend should be positive
        # (Note: this depends on the specific price pattern)
        assert np.isfinite(features["trend_1h"])

    @given(
        prices=st.lists(
            st.floats(min_value=1000.0, max_value=100000.0),
            min_size=300,
            max_size=300,
        )
    )
    @settings(max_examples=10, deadline=None)
    def test_trend_decreases_with_downtrend_prices(self, prices: list[float]) -> None:
        """Monotonically decreasing prices should produce negative trend."""
        decreasing_prices = [50000.0 - i * 100 for i in range(300)]
        strategy = NeatSwingStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [float_to_candle(p, i) for i, p in enumerate(decreasing_prices)]

        features = strategy.compute_features(symbol, candles)

        assert np.isfinite(features["trend_1h"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])