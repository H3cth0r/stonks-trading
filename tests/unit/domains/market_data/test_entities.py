"""Unit tests for market data domain.

Tests entities and adapter patterns.
"""

from datetime import datetime

import pytest

from stonks_trading.domains.market_data.entities import Candle, OrderBook, Tick, TimeRange
from stonks_trading.domains.market_data.adapters import IExchangeAdapter
from stonks_trading.domains.trading.value_objects import Symbol


class TestCandle:
    """Test Candle entity."""

    def test_creation(self):
        """Candle can be created with OHLCV data."""
        candle = Candle(
            timestamp=datetime.utcnow(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
            symbol="BTC_USD",
        )
        assert candle.open == 100.0
        assert candle.high == 105.0
        assert candle.low == 99.0
        assert candle.close == 104.0
        assert candle.volume == 1000.0

    def test_is_bullish(self):
        """Candle correctly identifies bullish candle."""
        candle = Candle(
            timestamp=datetime.utcnow(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
        )
        assert candle.is_bullish() is True
        assert candle.is_bearish() is False

    def test_is_bearish(self):
        """Candle correctly identifies bearish candle."""
        candle = Candle(
            timestamp=datetime.utcnow(),
            open=104.0,
            high=105.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
        )
        assert candle.is_bullish() is False
        assert candle.is_bearish() is True

    def test_price_range(self):
        """price_range calculates high - low."""
        candle = Candle(
            timestamp=datetime.utcnow(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
        )
        assert candle.price_range() == 6.0

    def test_to_dict(self):
        """to_dict returns dictionary representation."""
        candle = Candle(
            timestamp=datetime.utcnow(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
            symbol="BTC_USD",
        )
        data = candle.to_dict()
        assert data["open"] == 100.0
        assert data["close"] == 104.0
        assert data["symbol"] == "BTC_USD"

    def test_from_dict(self):
        """from_dict creates Candle from dictionary."""
        data = {
            "timestamp": 1700000000000,
            "open": "100.0",
            "high": "105.0",
            "low": "99.0",
            "close": "104.0",
            "volume": "1000.0",
            "symbol": "BTC_USD",
        }
        candle = Candle.from_dict(data)
        assert candle.open == 100.0
        assert candle.close == 104.0
        assert candle.symbol == "BTC_USD"


class TestOrderBook:
    """Test OrderBook entity."""

    def test_creation(self):
        """OrderBook can be created with bids/asks."""
        book = OrderBook(
            symbol="BTC_USD",
            bids=[(100.0, 1.0), (99.0, 2.0)],
            asks=[(101.0, 1.5), (102.0, 2.0)],
            timestamp=datetime.utcnow(),
        )
        assert len(book.bids) == 2
        assert len(book.asks) == 2

    def test_best_bid(self):
        """best_bid returns highest bid (first after sort)."""
        book = OrderBook(
            symbol="BTC_USD",
            bids=[(101.0, 2.0), (100.0, 1.0)],  # Highest first
            asks=[(102.0, 1.0)],
        )
        best = book.best_bid()
        assert best == pytest.approx((101.0, 2.0))

    def test_best_ask(self):
        """best_ask returns lowest ask."""
        book = OrderBook(
            symbol="BTC_USD",
            bids=[(100.0, 1.0)],
            asks=[(101.0, 2.0), (102.0, 1.0)],  # Lowest first
        )
        best = book.best_ask()
        assert best == pytest.approx((101.0, 2.0))

    def test_spread(self):
        """spread calculates bid-ask spread."""
        book = OrderBook(
            symbol="BTC_USD",
            bids=[(100.0, 1.0)],
            asks=[(102.0, 1.0)],
        )
        assert book.spread() == 2.0

    def test_mid_price(self):
        """mid_price calculates midpoint."""
        book = OrderBook(
            symbol="BTC_USD",
            bids=[(100.0, 1.0)],
            asks=[(102.0, 1.0)],
        )
        assert book.mid_price() == 101.0


class TestTick:
    """Test Tick entity."""

    def test_creation(self):
        """Tick can be created."""
        tick = Tick(
            timestamp=datetime.utcnow(),
            price=100.0,
            quantity=1.0,
            side="buy",
            trade_id="123",
            symbol="BTC_USD",
        )
        assert tick.price == 100.0
        assert tick.side == "buy"

    def test_is_buy(self):
        """is_buy returns true for buy side."""
        tick = Tick(
            timestamp=datetime.utcnow(),
            price=100.0,
            quantity=1.0,
            side="buy",
        )
        assert tick.is_buy() is True
        assert tick.is_sell() is False


class TestTimeRange:
    """Test TimeRange entity."""

    def test_creation(self):
        """TimeRange can be created."""
        start = datetime.utcnow()
        end = datetime.utcnow()
        tr = TimeRange(start=start, end=end)
        assert tr.start == start
        assert tr.end == end

    def test_duration_seconds(self):
        """duration_seconds calculates seconds."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 1, 1, 0, 0)  # 1 hour later
        tr = TimeRange(start=start, end=end)
        assert tr.duration_seconds() == 3600.0

    def test_contains(self):
        """contains checks if timestamp is within range."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 1, 1, 0, 0)
        tr = TimeRange(start=start, end=end)
        inside = datetime(2024, 1, 1, 0, 30, 0)
        outside = datetime(2024, 1, 2, 0, 0, 0)
        assert tr.contains(inside) is True
        assert tr.contains(outside) is False

    def test_overlaps(self):
        """overlaps checks for range intersection."""
        tr1 = TimeRange(
            start=datetime(2024, 1, 1, 0, 0, 0),
            end=datetime(2024, 1, 1, 1, 0, 0),
        )
        tr2 = TimeRange(
            start=datetime(2024, 1, 1, 0, 30, 0),
            end=datetime(2024, 1, 1, 1, 30, 0),
        )
        tr3 = TimeRange(
            start=datetime(2024, 1, 2, 0, 0, 0),
            end=datetime(2024, 1, 2, 1, 0, 0),
        )
        assert tr1.overlaps(tr2) is True
        assert tr1.overlaps(tr3) is False
