"""Unit tests for reconciliation repositories.

Tests repository functions with mocked database models.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationReport,
    ReconciliationStatus,
)
from stonks_trading.domains.reconciliation.repositories import (
    _model_to_diff,
    _model_to_report,
    _trade_model_to_entity,
    get_reconciliation_report,
    list_reconciliation_diffs_by_report,
    list_reconciliation_reports,
    list_unreconciled_trades,
    save_reconciliation_diff,
    save_reconciliation_diffs,
    save_reconciliation_report,
)
from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


class TestModelToEntityConversion:
    """Test conversion functions."""

    def test_model_to_diff(self):
        """Test conversion from model to ReconciliationDiff entity."""
        mock_model = MagicMock()
        mock_model.status = "matched"
        mock_model.internal_trade_id = 1
        mock_model.venue_trade_id = "venue-123"
        mock_model.symbol = "BTC_USD"
        mock_model.side = "buy"
        mock_model.internal_price = 50000.0
        mock_model.venue_price = 50000.0
        mock_model.internal_quantity = 0.1
        mock_model.venue_quantity = 0.1
        mock_model.internal_timestamp = datetime.utcnow()
        mock_model.venue_timestamp = datetime.utcnow()
        mock_model.field_differences = None

        entity = _model_to_diff(mock_model)

        assert entity.status == ReconciliationStatus.MATCHED
        assert entity.internal_trade_id == 1
        assert entity.venue_trade_id == "venue-123"
        assert entity.symbol == "BTC_USD"

    @pytest.mark.asyncio
    async def test_model_to_report(self):
        """Test conversion from model to ReconciliationReport entity."""
        mock_model = MagicMock()
        mock_model.run_id = "run-123"
        mock_model.venue = "binance"
        mock_model.symbol = "BTC_USD"
        mock_model.start_time = datetime.utcnow()
        mock_model.end_time = datetime.utcnow()
        mock_model.total_internal = 10
        mock_model.total_venue = 10
        mock_model.matched = 8
        mock_model.mismatches = 2
        mock_model.missing_internal = 0
        mock_model.missing_venue = 0
        mock_model.created_at = datetime.utcnow()
        mock_model.diffs = AsyncMock()
        mock_model.diffs.all = AsyncMock(return_value=[])

        entity = await _model_to_report(mock_model)

        assert entity.run_id == "run-123"
        assert entity.venue == "binance"
        assert entity.symbol == "BTC_USD"
        assert entity.total_internal == 10

    def test_trade_model_to_entity(self):
        """Test conversion from TradeModel to Trade entity."""
        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.symbol = "BTC_USD"
        mock_model.side = Side.BUY
        mock_model.fill_price = 50000.0
        mock_model.quantity = 0.1
        mock_model.fee = 5.0
        mock_model.fee_currency = "USD"
        mock_model.realized_pnl = None
        mock_model.order_id = "order-123"
        mock_model.created_at = datetime.utcnow()
        mock_model.mode = TradingMode.DRY_RUN
        mock_model.bot_type = "neat_swing"
        mock_model.bot_instance_id = "test-bot"
        mock_model.intended_price = None
        mock_model.slippage_bps = None
        mock_model.quote_quantity = 5000.0
        mock_model.fee_rate = 0.001
        mock_model.genome_id = 1
        mock_model.entry_price = None
        mock_model.latency_ms = 100
        mock_model.exchange = "binance"
        mock_model.strategy = "neat_swing"

        entity = _trade_model_to_entity(mock_model)

        assert entity.id == 1
        assert entity.symbol.value == "BTC_USD"
        assert entity.side == Side.BUY
        assert entity.fill_price.amount == 50000.0


class TestSaveReconciliationReport:
    """Test save_reconciliation_report function."""

    @pytest.mark.asyncio
    async def test_save_report(self):
        """Save reconciliation report successfully."""
        mock_model = MagicMock()
        mock_model.run_id = "run-123"
        mock_model.venue = "binance"
        mock_model.symbol = "BTC_USD"
        mock_model.start_time = datetime.utcnow()
        mock_model.end_time = datetime.utcnow()
        mock_model.total_internal = 10
        mock_model.total_venue = 10
        mock_model.matched = 8
        mock_model.mismatches = 2
        mock_model.missing_internal = 0
        mock_model.missing_venue = 0
        mock_model.created_at = datetime.utcnow()

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.create",
            new=AsyncMock(return_value=mock_model),
        ):
            report = ReconciliationReport(
                run_id="run-123",
                venue="binance",
                symbol="BTC_USD",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                total_internal=10,
                total_venue=10,
                matched=8,
                mismatches=2,
                missing_internal=0,
                missing_venue=0,
            )
            result = await save_reconciliation_report(report)
            assert result.run_id == "run-123"


class TestGetReconciliationReport:
    """Test get_reconciliation_report function."""

    @pytest.mark.asyncio
    async def test_get_existing_report(self):
        """Get existing report."""
        mock_model = MagicMock()
        mock_model.run_id = "run-123"
        mock_model.venue = "binance"
        mock_model.symbol = "BTC_USD"
        mock_model.start_time = datetime.utcnow()
        mock_model.end_time = datetime.utcnow()
        mock_model.total_internal = 10
        mock_model.total_venue = 10
        mock_model.matched = 8
        mock_model.mismatches = 2
        mock_model.missing_internal = 0
        mock_model.missing_venue = 0
        mock_model.created_at = datetime.utcnow()
        mock_model.diffs = AsyncMock()
        mock_model.diffs.all = AsyncMock(return_value=[])

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=mock_model),
        ):
            result = await get_reconciliation_report("run-123")
            assert result is not None
            assert result.run_id == "run-123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_report(self):
        """Get non-existent report returns None."""
        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=None),
        ):
            result = await get_reconciliation_report("nonexistent")
            assert result is None


class TestListReconciliationReports:
    """Test list_reconciliation_reports function."""

    @pytest.mark.asyncio
    async def test_list_reports(self):
        """List reports."""
        mock_model = MagicMock()
        mock_model.run_id = "run-123"
        mock_model.venue = "binance"
        mock_model.symbol = "BTC_USD"
        mock_model.start_time = datetime.utcnow()
        mock_model.end_time = datetime.utcnow()
        mock_model.total_internal = 10
        mock_model.total_venue = 10
        mock_model.matched = 8
        mock_model.mismatches = 2
        mock_model.missing_internal = 0
        mock_model.missing_venue = 0
        mock_model.created_at = datetime.utcnow()
        mock_model.diffs = AsyncMock()
        mock_model.diffs.all = AsyncMock(return_value=[])

        mock_queryset = MagicMock()
        mock_queryset.order_by = MagicMock(return_value=mock_queryset)
        mock_queryset.offset = MagicMock(return_value=mock_queryset)
        mock_queryset.limit = AsyncMock(return_value=[mock_model])

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.all",
            return_value=mock_queryset,
        ):
            result = await list_reconciliation_reports()
            assert len(result) == 1
            assert result[0].run_id == "run-123"

    @pytest.mark.asyncio
    async def test_list_reports_by_venue(self):
        """List reports filtered by venue."""
        mock_model = MagicMock()
        mock_model.run_id = "run-123"
        mock_model.venue = "binance"
        mock_model.symbol = "BTC_USD"
        mock_model.start_time = datetime.utcnow()
        mock_model.end_time = datetime.utcnow()
        mock_model.total_internal = 10
        mock_model.total_venue = 10
        mock_model.matched = 8
        mock_model.mismatches = 2
        mock_model.missing_internal = 0
        mock_model.missing_venue = 0
        mock_model.created_at = datetime.utcnow()
        mock_model.diffs = AsyncMock()
        mock_model.diffs.all = AsyncMock(return_value=[])

        mock_queryset = MagicMock()
        mock_queryset.filter = MagicMock(return_value=mock_queryset)
        mock_queryset.order_by = MagicMock(return_value=mock_queryset)
        mock_queryset.offset = MagicMock(return_value=mock_queryset)
        mock_queryset.limit = AsyncMock(return_value=[mock_model])

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.all",
            return_value=mock_queryset,
        ):
            result = await list_reconciliation_reports(venue="binance")
            assert len(result) == 1


class TestSaveReconciliationDiff:
    """Test save_reconciliation_diff function."""

    @pytest.mark.asyncio
    async def test_save_diff(self):
        """Save reconciliation diff successfully."""
        mock_report_model = MagicMock()
        mock_report_model.id = 1

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=mock_report_model),
        ), patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationDiffModel.create",
            new=AsyncMock(return_value=MagicMock()),
        ):
            diff = ReconciliationDiff(
                status=ReconciliationStatus.MATCHED,
                internal_trade_id=1,
                venue_trade_id="venue-123",
                symbol="BTC_USD",
                side="buy",
                internal_price=50000.0,
                venue_price=50000.0,
                internal_quantity=0.1,
                venue_quantity=0.1,
                internal_timestamp=datetime.utcnow(),
                venue_timestamp=datetime.utcnow(),
            )
            result = await save_reconciliation_diff("run-123", diff)
            assert result.status == ReconciliationStatus.MATCHED

    @pytest.mark.asyncio
    async def test_save_diff_report_not_found(self):
        """Save diff fails when report not found."""
        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=None),
        ):
            diff = ReconciliationDiff(
                status=ReconciliationStatus.MATCHED,
                internal_trade_id=1,
                venue_trade_id="venue-123",
                symbol="BTC_USD",
                side="buy",
                internal_price=50000.0,
                venue_price=50000.0,
                internal_quantity=0.1,
                venue_quantity=0.1,
                internal_timestamp=datetime.utcnow(),
                venue_timestamp=datetime.utcnow(),
            )
            with pytest.raises(ValueError, match="Report run-123 not found"):
                await save_reconciliation_diff("run-123", diff)


class TestSaveReconciliationDiffs:
    """Test save_reconciliation_diffs function."""

    @pytest.mark.asyncio
    async def test_save_multiple_diffs(self):
        """Save multiple reconciliation diffs."""
        mock_report_model = MagicMock()
        mock_report_model.id = 1

        diffs = [
            ReconciliationDiff(
                status=ReconciliationStatus.MATCHED,
                internal_trade_id=1,
                venue_trade_id="venue-123",
                symbol="BTC_USD",
                side="buy",
                internal_price=50000.0,
                venue_price=50000.0,
                internal_quantity=0.1,
                venue_quantity=0.1,
                internal_timestamp=datetime.utcnow(),
                venue_timestamp=datetime.utcnow(),
            ),
            ReconciliationDiff(
                status=ReconciliationStatus.MISMATCH,
                internal_trade_id=2,
                venue_trade_id="venue-124",
                symbol="BTC_USD",
                side="sell",
                internal_price=50100.0,
                venue_price=50000.0,
                internal_quantity=0.2,
                venue_quantity=0.2,
                internal_timestamp=datetime.utcnow(),
                venue_timestamp=datetime.utcnow(),
                field_differences={"price": [50100.0, 50000.0]},
            ),
        ]

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=mock_report_model),
        ), patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationDiffModel.create",
            new=AsyncMock(return_value=MagicMock()),
        ):
            await save_reconciliation_diffs("run-123", diffs)
            # Should not raise


class TestListReconciliationDiffsByReport:
    """Test list_reconciliation_diffs_by_report function."""

    @pytest.mark.asyncio
    async def test_list_diffs_by_report(self):
        """List diffs for a specific report."""
        mock_report_model = MagicMock()
        mock_report_model.id = 1

        mock_diff_model = MagicMock()
        mock_diff_model.status = "matched"
        mock_diff_model.internal_trade_id = 1
        mock_diff_model.venue_trade_id = "venue-123"
        mock_diff_model.symbol = "BTC_USD"
        mock_diff_model.side = "buy"
        mock_diff_model.internal_price = 50000.0
        mock_diff_model.venue_price = 50000.0
        mock_diff_model.internal_quantity = 0.1
        mock_diff_model.venue_quantity = 0.1
        mock_diff_model.internal_timestamp = datetime.utcnow()
        mock_diff_model.venue_timestamp = datetime.utcnow()
        mock_diff_model.field_differences = None

        mock_queryset = MagicMock()
        mock_queryset.order_by = AsyncMock(return_value=[mock_diff_model])

        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=mock_report_model),
        ), patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationDiffModel.filter",
            return_value=mock_queryset,
        ):
            result = await list_reconciliation_diffs_by_report("run-123")
            assert len(result) == 1
            assert result[0].status == ReconciliationStatus.MATCHED

    @pytest.mark.asyncio
    async def test_list_diffs_report_not_found(self):
        """List diffs returns empty when report not found."""
        with patch(
            "stonks_trading.domains.reconciliation.repositories.ReconciliationReportModel.get_or_none",
            new=AsyncMock(return_value=None),
        ):
            result = await list_reconciliation_diffs_by_report("nonexistent")
            assert result == []


class TestListUnreconciledTrades:
    """Test list_unreconciled_trades function."""

    @pytest.mark.asyncio
    async def test_list_trades(self):
        """List unreconciled trades."""
        mock_trade_model = MagicMock()
        mock_trade_model.id = 1
        mock_trade_model.symbol = "BTC_USD"
        mock_trade_model.side = Side.BUY
        mock_trade_model.fill_price = 50000.0
        mock_trade_model.quantity = 0.1
        mock_trade_model.fee = 5.0
        mock_trade_model.fee_currency = "USD"
        mock_trade_model.realized_pnl = None
        mock_trade_model.order_id = "order-123"
        mock_trade_model.created_at = datetime.utcnow()
        mock_trade_model.mode = TradingMode.DRY_RUN
        mock_trade_model.bot_type = "neat_swing"
        mock_trade_model.bot_instance_id = "test-bot"
        mock_trade_model.intended_price = None
        mock_trade_model.slippage_bps = None
        mock_trade_model.quote_quantity = 5000.0
        mock_trade_model.fee_rate = 0.001
        mock_trade_model.genome_id = 1
        mock_trade_model.entry_price = None
        mock_trade_model.latency_ms = 100
        mock_trade_model.exchange = "binance"
        mock_trade_model.strategy = "neat_swing"

        mock_queryset = MagicMock()
        mock_queryset.order_by = AsyncMock(return_value=[mock_trade_model])

        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 31)

        with patch(
            "stonks_trading.domains.reconciliation.repositories.TradeModel.filter",
            return_value=mock_queryset,
        ):
            result = await list_unreconciled_trades("BTC_USD", start_time, end_time)
            assert len(result) == 1
            assert result[0].symbol.value == "BTC_USD"

    @pytest.mark.asyncio
    async def test_list_trades_empty(self):
        """List trades returns empty when none found."""
        mock_queryset = MagicMock()
        mock_queryset.order_by = AsyncMock(return_value=[])

        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 31)

        with patch(
            "stonks_trading.domains.reconciliation.repositories.TradeModel.filter",
            return_value=mock_queryset,
        ):
            result = await list_unreconciled_trades("BTC_USD", start_time, end_time)
            assert result == []
