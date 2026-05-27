"""Unit tests for live_features module."""

from datetime import datetime, timedelta

import pytest

from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.adapter import Candle


def make_candle(symbol: str = "BTC_USD", offset_minutes: int = 0) -> Candle:
    """Create a test candle with given offset."""
    return Candle(
        symbol=symbol,
        open=50000.0 + offset_minutes,
        high=50100.0 + offset_minutes,
        low=49900.0 + offset_minutes,
        close=50050.0 + offset_minutes,
        volume=1.5,
        timestamp=datetime(2024, 1, 1) + timedelta(minutes=offset_minutes),
        venue="binance",
        closed=True,
    )


class TestLiveFeatureComputer:
    """Tests for LiveFeatureComputer."""

    def test_creation(self):
        """LiveFeatureComputer can be created."""
        computer = LiveFeatureComputer(window_hours=100)
        assert computer.window_hours == 100

    def test_on_candle_returns_none_insufficient_data(self):
        """on_candle returns None when not enough data."""
        computer = LiveFeatureComputer(window_hours=200)

        # Add only a few candles (less than 200 hours = 12000 minutes)
        for i in range(10):
            candle = make_candle(offset_minutes=i)
            result = computer.on_candle(candle)
            assert result is None

    def test_on_candle_returns_features_when_sufficient_data(self):
        """on_candle returns features when enough data accumulated."""
        computer = LiveFeatureComputer(window_hours=200)

        # Add 12000 candles (exactly 200 hours * 60 = 12000)
        # First 11999 candles should return None
        for i in range(11999):
            result = computer.on_candle(make_candle(offset_minutes=i))
            assert result is None

        # 12000th candle should return features (we now have 12000 candles >= min_candles)
        result = computer.on_candle(make_candle(offset_minutes=11999))
        assert result is not None
        assert "trend_1h" in result
        assert "rsi_1h" in result
        assert "rsi_15m" in result
        assert "roc" in result
        assert "bb_width" in result

    def test_get_stats_returns_correct_format(self):
        """get_stats returns correct dictionary structure."""
        computer = LiveFeatureComputer(window_hours=200)

        # Empty state
        stats = computer.get_stats()
        assert "symbols" in stats
        assert stats["symbols"] == []

        # Single symbol
        stats = computer.get_stats("BTC_USD")
        assert stats["symbol"] == "BTC_USD"
        assert stats["candles"] == 0
        assert stats["has_features"] is False

    def test_reset_clears_data(self):
        """reset clears accumulated data."""
        computer = LiveFeatureComputer(window_hours=200)

        # Add some candles
        for i in range(100):
            computer.on_candle(make_candle(offset_minutes=i))

        # Verify data exists
        assert computer._1m_data.get("BTC_USD") is not None

        # Reset single symbol
        computer.reset("BTC_USD")
        assert computer._1m_data.get("BTC_USD") is None

        # Add more data and reset all
        for i in range(100):
            computer.on_candle(make_candle(offset_minutes=i))
        computer.reset()
        assert len(computer._1m_data) == 0

    def test_multiple_symbols(self):
        """computer tracks multiple symbols independently."""
        computer = LiveFeatureComputer(window_hours=200)

        # Add candles for BTC
        for i in range(100):
            computer.on_candle(make_candle(symbol="BTC_USD", offset_minutes=i))

        # Add candles for ETH
        for i in range(100):
            computer.on_candle(make_candle(symbol="ETH_USD", offset_minutes=i))

        stats = computer.get_stats()
        assert "BTC_USD" in stats["symbols"]
        assert "ETH_USD" in stats["symbols"]
