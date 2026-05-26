"""E2E tests for disaster recovery and startup resilience.

Tests the full disaster recovery flow including:
- DuckDB rebuild from Tigris Parquet
- Bot state restoration from Postgres
- Registry consistency verification
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.startup import (
    Inconsistency,
    RebuildReport,
    StartupOrchestrator,
    StartupReport,
    run_startup_recovery,
)
from stonks_trading.domains.trading.entities import BotInstance
from stonks_trading.domains.trading.enums import BotStatus
from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


class MockTigrisClient:
    """Mock Tigris client for disaster recovery testing."""

    def __init__(self, partitions=None):
        self._partitions = partitions or []
        self.download_calls = []
        self.upload_calls = []

    def list_partitions(self, symbol: str):
        """Return mock partitions for symbol."""
        return [
            p for p in self._partitions if p.get("symbol") == symbol
        ]

    def download_ohlcv_partition(self, symbol: str, year: int, month: int):
        """Return mock DataFrame with engineered features for partition."""
        self.download_calls.append({"symbol": symbol, "year": year, "month": month})

        # Return sample OHLCV data with engineered features
        base_time = datetime(year, month, 1)
        data = []
        for i in range(100):  # 100 candles
            timestamp = base_time + timedelta(minutes=i)
            data.append({
                "timestamp": timestamp,
                "open": 50000.0 + i * 10,
                "high": 50100.0 + i * 10,
                "low": 49900.0 + i * 10,
                "close": 50050.0 + i * 10,
                "volume": 1.5,
                "trend_1h": 0.01,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.001,
                "bb_width": 0.02,
            })

        return pd.DataFrame(data)

    def upload_ohlcv_partition(self, symbol: str, year: int, month: int, df):
        """Track upload calls."""
        self.upload_calls.append({
            "symbol": symbol,
            "year": year,
            "month": month,
            "rows": len(df),
        })


@pytest.fixture
def temp_duckdb_path():
    """Create temporary DuckDB database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest.fixture
def mock_tigris_partitions():
    """Create mock Tigris partitions."""
    return [
        {"symbol": "BTCUSDT", "year": 2024, "month": 1, "size": 1000, "last_modified": datetime.utcnow()},
        {"symbol": "BTCUSDT", "year": 2024, "month": 2, "size": 1000, "last_modified": datetime.utcnow()},
        {"symbol": "ETHUSDT", "year": 2024, "month": 1, "size": 800, "last_modified": datetime.utcnow()},
    ]


@pytest.mark.asyncio
async def test_startup_recovery_skip_flag():
    """Test that --skip-recovery flag skips recovery operations."""
    report = await run_startup_recovery(skip_recovery=True)

    assert report.duckdb_rebuilt is False
    assert report.bots_recovered == 0
    assert report.bots_started == 0
    assert report.errors == []


@pytest.mark.asyncio
async def test_duckdb_health_check_existing_db(temp_duckdb_path):
    """Test DuckDB health check with existing database."""
    # Create a DuckDB with some data
    client = DuckDBClient(db_path=temp_duckdb_path)
    client.connect()

    # Insert some test data
    candle = Candle(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=1.5,
        venue="binance",
        closed=True,
    )

    client.insert_candle(candle, features={"trend_1h": 0.01})
    client.close()

    # Now test health check
    orchestrator = StartupOrchestrator(duckdb_client=DuckDBClient(db_path=temp_duckdb_path))
    is_healthy = orchestrator._duckdb_healthy()

    assert is_healthy is True


@pytest.mark.asyncio
async def test_duckdb_health_check_missing_db():
    """Test DuckDB health check with non-existent database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent_path = os.path.join(tmpdir, "nonexistent", "test.db")
        orchestrator = StartupOrchestrator(
            duckdb_client=DuckDBClient(db_path=nonexistent_path)
        )
        is_healthy = orchestrator._duckdb_healthy()

        assert is_healthy is False


@pytest.mark.asyncio
async def test_rebuild_duckdb_from_parquet(temp_duckdb_path, mock_tigris_partitions):
    """Test DuckDB rebuild from Tigris Parquet partitions."""
    mock_tigris = MockTigrisClient(partitions=mock_tigris_partitions)
    duckdb_client = DuckDBClient(db_path=temp_duckdb_path)

    orchestrator = StartupOrchestrator(
        duckdb_client=duckdb_client,
        tigris_client=mock_tigris,
    )

    # Run rebuild
    report = await orchestrator.rebuild_duckdb()

    # Verify results
    assert len(report.errors) == 0
    assert report.total_rows > 0
    assert "BTCUSDT" in report.symbols_rebuilt
    assert len(mock_tigris.download_calls) > 0


@pytest.mark.asyncio
async def test_rebuild_duckdb_without_tigris_config(temp_duckdb_path):
    """Test DuckDB rebuild fails gracefully without Tigris config."""
    orchestrator = StartupOrchestrator(
        duckdb_client=DuckDBClient(db_path=temp_duckdb_path),
        tigris_client=None,
    )

    report = await orchestrator.rebuild_duckdb()

    # Should have errors (at least one) when Tigris is not available
    assert len(report.errors) >= 1
    assert report.total_rows == 0


@pytest.mark.asyncio
async def test_full_recovery_workflow(temp_duckdb_path, mock_tigris_partitions):
    """Test full startup recovery workflow."""
    mock_tigris = MockTigrisClient(partitions=mock_tigris_partitions)
    duckdb_client = DuckDBClient(db_path=temp_duckdb_path)

    orchestrator = StartupOrchestrator(
        duckdb_client=duckdb_client,
        tigris_client=mock_tigris,
    )

    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="test-bot-1",
                symbols=["BTC_USD"],
                mode="dry_run",
                id=1,
                status=BotStatus.RUNNING,
                config={"genome_id": 1},
            ),
            BotInstance(
                bot_type="neat_swing",
                instance_id="test-bot-2",
                symbols=["ETH_USD"],
                mode="dry_run",
                id=2,
                status=BotStatus.STOPPED,  # Should be skipped
                config={},
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            mock_load_state.return_value = {"equity": 10000.0, "position": None}

            report = await orchestrator.recover_all()

            # Verify DuckDB was rebuilt (file didn't exist, so it's unhealthy)
            assert report.duckdb_rebuilt is True
            # Only running bot should be recovered
            assert report.bots_recovered == 1
            mock_load_state.assert_called_once()


@pytest.mark.asyncio
async def test_recovery_preserves_bot_state():
    """Test that recovery preserves bot state from Postgres."""
    expected_state = {
        "equity": 15000.0,
        "position": {"symbol": "BTC_USD", "quantity": 0.5, "entry_price": 50000.0},
        "trade_count": 10,
        "max_drawdown": 0.05,
    }

    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="recovery-test",
                symbols=["BTC_USD"],
                mode="live",
                id=1,
                status=BotStatus.RUNNING,
                config={"genome_id": 42},
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            mock_load_state.return_value = expected_state

            orchestrator = StartupOrchestrator()
            report = await orchestrator.recover_all()

            assert report.bots_recovered == 1
            mock_load_state.assert_called_once_with(
                BotContext(bot_type="neat_swing", instance_id="recovery-test")
            )


@pytest.mark.asyncio
async def test_registry_consistency_check():
    """Test registry consistency verification."""
    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="orphaned-bot",
                symbols=["BTC_USD"],
                mode="dry_run",
                id=1,
                status=BotStatus.RUNNING,
                config={},
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            # Simulate missing state for running bot
            mock_load_state.return_value = None

            orchestrator = StartupOrchestrator()
            inconsistencies = await orchestrator.verify_registry_consistency()

            assert len(inconsistencies) == 1
            assert inconsistencies[0].bot_type == "neat_swing"
            assert inconsistencies[0].instance_id == "orphaned-bot"
            assert "no saved state" in inconsistencies[0].issue


@pytest.mark.asyncio
async def test_delete_duckdb_rebuild_from_parquet(temp_duckdb_path, mock_tigris_partitions):
    """E2E test: Delete DuckDB and verify rebuild from Parquet.

    This test simulates a full disaster recovery scenario:
    1. Create initial DuckDB with data
    2. Delete DuckDB file (simulate disaster)
    3. Run recovery
    4. Verify DuckDB is rebuilt with data
    """
    # Setup
    mock_tigris = MockTigrisClient(partitions=mock_tigris_partitions)
    duckdb_client = DuckDBClient(db_path=temp_duckdb_path)

    # Step 1: Create initial data
    duckdb_client.connect()
    candle = Candle(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=1.5,
        venue="binance",
        closed=True,
    )
    duckdb_client.insert_candle(candle)
    duckdb_client.close()

    # Verify file exists
    assert Path(temp_duckdb_path).exists()

    # Step 2: Delete DuckDB file (simulate disaster)
    Path(temp_duckdb_path).unlink()
    assert not Path(temp_duckdb_path).exists()

    # Step 3: Run recovery
    orchestrator = StartupOrchestrator(
        duckdb_client=DuckDBClient(db_path=temp_duckdb_path),
        tigris_client=mock_tigris,
    )

    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = []

        report = await orchestrator.recover_all()

        # Step 4: Verify recovery
        assert report.duckdb_rebuilt is True
        assert len(report.errors) == 0
        assert Path(temp_duckdb_path).exists()

        # Verify data was loaded
        new_client = DuckDBClient(db_path=temp_duckdb_path)
        new_client.connect()
        stats = new_client.get_stats()
        assert stats["total_rows"] > 0
        new_client.close()


@pytest.mark.asyncio
async def test_bot_state_restored_after_crash(temp_duckdb_path):
    """E2E test: Verify bot state is restored from Postgres after simulated crash.

    This test verifies that:
    1. Bot was running before crash
    2. State was persisted to Postgres
    3. After crash and restart, state is restored
    """
    expected_bot_state = {
        "equity": 12500.0,
        "position": {"symbol": "BTC_USD", "quantity": 0.25, "entry_price": 48000.0},
        "trade_count": 5,
        "genome_id": 123,
    }

    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        # Bot was running before crash
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="crash-test-bot",
                symbols=["BTC_USD"],
                mode="live",
                id=1,
                status=BotStatus.RUNNING,
                config={"genome_id": 123},
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            # State persisted in Postgres
            mock_load_state.return_value = expected_bot_state

            orchestrator = StartupOrchestrator()
            report = await orchestrator.recover_all()

            # Verify state was restored
            assert report.bots_recovered == 1
            mock_load_state.assert_called_once()
            call_args = mock_load_state.call_args
            assert call_args[0][0].bot_type == "neat_swing"
            assert call_args[0][0].instance_id == "crash-test-bot"


@pytest.mark.asyncio
async def test_recovery_handles_missing_bot_gracefully():
    """Test that recovery handles missing/corrupted bot data gracefully."""
    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="corrupted-bot",
                symbols=["BTC_USD"],
                mode="dry_run",
                id=1,
                status=BotStatus.RUNNING,
                config=None,  # Missing config
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            # Simulate error loading state
            mock_load_state.side_effect = Exception("Database connection failed")

            orchestrator = StartupOrchestrator()
            report = await orchestrator.recover_all()

            # Should not crash, but report error
            assert report.bots_recovered == 0
            # Filter for bot-specific errors (may include Tigris config warning)
            bot_errors = [e for e in report.errors if "corrupted-bot" in e]
            assert len(bot_errors) == 1
            assert "Database connection failed" in bot_errors[0]


@pytest.mark.asyncio
async def test_recovery_multiple_bots():
    """Test recovery with multiple bots of different types."""
    with patch("stonks_trading.bots.startup.list_all_bot_instances") as mock_list_bots:
        mock_list_bots.return_value = [
            BotInstance(
                bot_type="neat_swing",
                instance_id="bot-1",
                symbols=["BTC_USD"],
                mode="dry_run",
                id=1,
                status=BotStatus.RUNNING,
                config={},
            ),
            BotInstance(
                bot_type="neat_swing",
                instance_id="bot-2",
                symbols=["ETH_USD"],
                mode="live",
                id=2,
                status=BotStatus.RUNNING,
                config={},
            ),
            BotInstance(
                bot_type="neat_swing",
                instance_id="bot-3",
                symbols=["SOL_USD"],
                mode="dry_run",
                id=3,
                status=BotStatus.STOPPED,  # Not running
                config={},
            ),
        ]

        with patch("stonks_trading.bots.startup.load_bot_state") as mock_load_state:
            mock_load_state.return_value = {"equity": 10000.0}

            orchestrator = StartupOrchestrator()
            report = await orchestrator.recover_all()

            # Only 2 running bots should be recovered
            assert report.bots_recovered == 2
            assert mock_load_state.call_count == 2


@pytest.mark.asyncio
async def test_rebuild_report_dataclass():
    """Test RebuildReport dataclass."""
    report = RebuildReport(
        symbols_rebuilt=["BTCUSDT", "ETHUSDT"],
        total_rows=10000,
        errors=[],
    )

    assert report.symbols_rebuilt == ["BTCUSDT", "ETHUSDT"]
    assert report.total_rows == 10000
    assert report.errors == []


@pytest.mark.asyncio
async def test_startup_report_dataclass():
    """Test StartupReport dataclass."""
    report = StartupReport(
        duckdb_rebuilt=True,
        bots_recovered=3,
        bots_started=2,
        errors=["Minor warning"],
    )

    assert report.duckdb_rebuilt is True
    assert report.bots_recovered == 3
    assert report.bots_started == 2
    assert len(report.errors) == 1


@pytest.mark.asyncio
async def test_inconsistency_dataclass():
    """Test Inconsistency dataclass."""
    inconsistency = Inconsistency(
        bot_type="neat_swing",
        instance_id="test-bot",
        issue="State mismatch",
        expected_status="running",
        actual_status="stopped",
    )

    assert inconsistency.bot_type == "neat_swing"
    assert inconsistency.instance_id == "test-bot"
    assert inconsistency.issue == "State mismatch"
    assert inconsistency.expected_status == "running"
    assert inconsistency.actual_status == "stopped"
