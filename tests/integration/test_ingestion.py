"""Integration tests for data ingestion pipeline.

These tests verify the data pipeline components work together correctly:
- Binance adapter (WebSocket + REST)
- DuckDB storage
- Live feature computation
- Feature parity with training
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from stonks_trading.domains.trading.neat.features import engineer_features
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.ingest.binance import BinanceAdapter
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


@pytest_asyncio.fixture
async def duckdb() -> DuckDBClient:
    """DuckDB test fixture with temporary database."""
    # Use a temp directory path without pre-creating the file
    # DuckDB will create the file when connect() is called
    db_path = tempfile.mktemp(suffix=".db")

    client = DuckDBClient(db_path=db_path)
    client.connect()
    yield client
    client.close()
    os.unlink(db_path)


@pytest.fixture
def sample_candles() -> list[Candle]:
    """Generate sample candles for testing."""
    base_time = datetime.utcnow() - timedelta(hours=210)  # 210 hours for 200h window + buffer
    candles = []

    for i in range(210 * 60):  # 210 hours of 1m candles
        timestamp = base_time + timedelta(minutes=i)
        price = 50000.0 + (i % 1000) * 0.1  # Slight price drift

        candles.append(
            Candle(
                symbol="BTC_USD",
                venue="test",
                timestamp=timestamp,
                open=price,
                high=price + 50,
                low=price - 50,
                close=price + 20,
                volume=10.0,
                closed=True,
            )
        )

    return candles


@pytest.mark.asyncio
async def test_duckdb_insert_and_retrieve(duckdb: DuckDBClient) -> None:
    """Test DuckDB can insert and retrieve candles."""
    candle = Candle(
        symbol="BTC_USD",
        venue="test",
        timestamp=datetime.utcnow(),
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=10.0,
        closed=True,
    )

    features = {"trend_1h": 0.01, "rsi_1h": 0.55, "rsi_15m": 0.52, "roc": 0.001, "bb_width": 0.02}

    duckdb.insert_candle(candle, features)

    # Retrieve recent data
    symbol = Symbol(value="BTC_USD")
    recent = duckdb.get_recent_data(symbol, lookback=timedelta(hours=1))

    assert len(recent) == 1
    assert recent[0]["symbol"] == "BTC_USD"
    assert recent[0]["close"] == 50050.0
    assert recent[0]["trend_1h"] == 0.01


@pytest.mark.asyncio
async def test_duckdb_batch_insert(duckdb: DuckDBClient) -> None:
    """Test DuckDB batch insert."""
    candles = [
        Candle(
            symbol="BTC_USD",
            venue="test",
            timestamp=datetime.utcnow() - timedelta(minutes=i),
            open=50000.0 + i,
            high=50100.0 + i,
            low=49900.0 + i,
            close=50050.0 + i,
            volume=10.0,
            closed=True,
        )
        for i in range(100)
    ]

    count = duckdb.insert_candles_batch(candles)
    assert count == 100

    symbol = Symbol(value="BTC_USD")
    recent = duckdb.get_recent_data(symbol, lookback=timedelta(hours=2))
    assert len(recent) == 100


@pytest.mark.asyncio
async def test_duckdb_prune(duckdb: DuckDBClient) -> None:
    """Test DuckDB data pruning."""
    old_candle = Candle(
        symbol="BTC_USD",
        venue="test",
        timestamp=datetime.utcnow() - timedelta(days=40),
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=10.0,
        closed=True,
    )

    new_candle = Candle(
        symbol="BTC_USD",
        venue="test",
        timestamp=datetime.utcnow(),
        open=51000.0,
        high=51100.0,
        low=50900.0,
        close=51050.0,
        volume=10.0,
        closed=True,
    )

    duckdb.insert_candle(old_candle)
    duckdb.insert_candle(new_candle)

    # Prune data older than 35 days
    deleted = duckdb.prune_old_data(retention=timedelta(days=35))
    # Note: DuckDB may return -1 for rowcount on DELETE, so we verify by checking data

    # Verify only new data remains
    symbol = Symbol(value="BTC_USD")
    recent = duckdb.get_recent_data(symbol, lookback=timedelta(days=40))
    assert len(recent) == 1
    assert recent[0]["close"] == 51050.0


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Feature computation too slow for CI - run locally",
)
async def test_feature_computer(sample_candles: list[Candle]) -> None:
    """Test live feature computer produces features."""
    computer = LiveFeatureComputer(window_hours=200)

    # Feed all but last candle
    for candle in sample_candles[:-1]:
        result = computer.on_candle(candle)
        # First 200 hours will return None (not enough data)

    # Last candle should produce features
    features = computer.on_candle(sample_candles[-1])
    assert features is not None
    assert "trend_1h" in features
    assert "rsi_1h" in features
    assert "rsi_15m" in features
    assert "roc" in features
    assert "bb_width" in features


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Feature parity too slow for CI - run locally",
)
async def test_feature_parity(sample_candles: list[Candle]) -> None:
    """Verify live features match training features."""
    import pandas as pd

    # Compute via live feature computer
    live = LiveFeatureComputer(window_hours=200)
    for c in sample_candles[:-1]:
        live.on_candle(c)
    live_features = live.on_candle(sample_candles[-1])

    assert live_features is not None

    # Compute via training function
    df = pd.DataFrame(
        [
            {"Open": c.open, "High": c.high, "Low": c.low, "Close": c.close, "Volume": c.volume}
            for c in sample_candles
        ]
    )
    df.index = pd.DatetimeIndex([c.timestamp for c in sample_candles])
    train_df = engineer_features(df)
    train_features = train_df.iloc[-1]

    # Compare (should be very close)
    tolerance = 0.001
    assert abs(live_features["trend_1h"] - train_features["trend_1h"]) < tolerance
    assert abs(live_features["rsi_1h"] - train_features["rsi_1h"]) < tolerance
    assert abs(live_features["rsi_15m"] - train_features["rsi_15m"]) < tolerance
    assert abs(live_features["roc"] - train_features["roc"]) < tolerance
    assert abs(live_features["bb_width"] - train_features["bb_width"]) < tolerance


@pytest.mark.asyncio
async def test_binance_backfill() -> None:
    """Test Binance backfill returns valid candles.

    This test makes real API calls to Binance testnet.
    Skip if no network access.
    """
    import pytest

    pytest.skip("Skipping test that requires network access to Binance")

    adapter = BinanceAdapter(use_testnet=True)
    symbol = Symbol(value="BTC_USD")

    end = datetime.utcnow()
    start = end - timedelta(hours=1)

    try:
        candles = await adapter.backfill(symbol, start, end)

        assert len(candles) > 0
        assert all(c.symbol == "BTC_USD" for c in candles)
        assert all(c.venue == "binance" for c in candles)
        assert all(c.closed for c in candles)

    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_binance_symbol_conversion() -> None:
    """Test Binance symbol conversion methods."""
    adapter = BinanceAdapter(use_testnet=True)

    # Test canonical to venue
    btc = Symbol(value="BTC_USD")
    assert adapter._to_venue_symbol(btc) == "BTCUSDT"

    eth = Symbol(value="ETH_USD")
    assert adapter._to_venue_symbol(eth) == "ETHUSDT"

    # Test venue to canonical
    assert adapter._from_venue_symbol("BTCUSDT").value == "BTC_USD"
    assert adapter._from_venue_symbol("ETHUSDT").value == "ETH_USD"


@pytest.mark.asyncio
async def test_duckdb_stats(duckdb: DuckDBClient) -> None:
    """Test DuckDB statistics."""
    # Insert test data
    for i in range(10):
        candle = Candle(
            symbol="BTC_USD",
            venue="test",
            timestamp=datetime.utcnow() - timedelta(minutes=i),
            open=50000.0 + i,
            high=50100.0 + i,
            low=49900.0 + i,
            close=50050.0 + i,
            volume=10.0,
            closed=True,
        )
        duckdb.insert_candle(candle)

    stats = duckdb.get_stats()
    assert stats["total_rows"] == 10
    assert len(stats["symbols"]) == 1
    assert stats["symbols"][0]["symbol"] == "BTC_USD"
    assert stats["symbols"][0]["row_count"] == 10


@pytest.mark.asyncio
async def test_duckdb_get_latest_timestamp(duckdb: DuckDBClient) -> None:
    """Test retrieving latest timestamp."""
    now = datetime.now(UTC)

    # Insert candles at different times
    for i in [10, 5, 15, 3]:
        candle = Candle(
            symbol="BTC_USD",
            venue="test",
            timestamp=now - timedelta(minutes=i),
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=10.0,
            closed=True,
        )
        duckdb.insert_candle(candle)

    symbol = Symbol(value="BTC_USD")
    latest = duckdb.get_latest_timestamp(symbol)

    assert latest is not None
    # Latest should be the one with smallest i (3 minutes ago)
    expected = now - timedelta(minutes=3)
    # Handle both offset-aware and offset-naive datetimes
    if latest.tzinfo is not None and expected.tzinfo is None:
        expected = expected.replace(tzinfo=UTC)
    elif latest.tzinfo is None and expected.tzinfo is not None:
        latest = latest.replace(tzinfo=UTC)
    assert abs((latest - expected).total_seconds()) < 1


@pytest.mark.asyncio
async def test_duckdb_get_data_range(duckdb: DuckDBClient) -> None:
    """Test retrieving data in specific time range."""
    base_time = datetime.now(UTC) - timedelta(hours=1)

    # Insert candles across 2 hours
    for i in range(120):  # 2 hours of 1m candles
        candle = Candle(
            symbol="BTC_USD",
            venue="test",
            timestamp=base_time + timedelta(minutes=i),
            open=50000.0 + i,
            high=50100.0 + i,
            low=49900.0 + i,
            close=50050.0 + i,
            volume=10.0,
            closed=True,
        )
        duckdb.insert_candle(candle)

    symbol = Symbol(value="BTC_USD")
    start = base_time + timedelta(minutes=30)
    end = base_time + timedelta(minutes=45)

    result = duckdb.get_data_range(symbol, start, end)
    assert len(result) == 16  # 30-45 inclusive = 16 candles

    # Verify ordering
    for i, row in enumerate(result):
        expected_time = start + timedelta(minutes=i)
        ts = row["timestamp"]
        # Handle both offset-aware and offset-naive datetimes
        if ts.tzinfo is not None and expected_time.tzinfo is None:
            expected_time = expected_time.replace(tzinfo=UTC)
        elif ts.tzinfo is None and expected_time.tzinfo is not None:
            ts = ts.replace(tzinfo=UTC)
        assert abs((ts - expected_time).total_seconds()) < 1
