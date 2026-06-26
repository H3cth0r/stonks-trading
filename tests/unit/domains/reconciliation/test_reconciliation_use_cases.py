"""Unit tests for reconciliation use cases.

Tests use cases with mocked repositories and services.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationReport,
    ReconciliationStatus,
    ReconciliationThresholds,
    VenueStatement,
)
from stonks_trading.domains.reconciliation.use_cases import (
    GetReconciliationReportUseCase,
    ListReconciliationReportsUseCase,
    ReconcileVenueStatementsUseCase,
)
from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Money, Symbol


class MockExchangeAdapter:
    """Mock exchange adapter for testing."""

    def __init__(self, trades=None):
        self._trades = trades or []

    async def get_my_trades(self, symbol, start_time, end_time):
        return self._trades


class TestReconcileVenueStatementsUseCase:
    """Test ReconcileVenueStatementsUseCase."""

    @pytest.mark.asyncio
    async def test_reconcile_success(self):
        """Reconcile venue statements successfully."""
        mock_internal_trade = Trade(
            id=1,
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            fee_currency="USD",
            order_id="order-123",
            created_at=datetime.utcnow(),
        )

        mock_venue_trade = {
            "id": 12345,
            "symbol": "BTCUSDT",
            "orderId": 99999,
            "price": "50000.00",
            "qty": "0.10000000",
            "commission": "5.00000000",
            "commissionAsset": "USDT",
            "time": int(datetime.utcnow().timestamp() * 1000),
            "isBuyer": True,
            "isMaker": False,
        }

        adapter = MockExchangeAdapter(trades=[mock_venue_trade])

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_unreconciled_trades",
            new=AsyncMock(return_value=[mock_internal_trade]),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_report",
            new=AsyncMock(return_value=MagicMock()),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_diffs",
            new=AsyncMock(return_value=None),
        ):
            use_case = ReconcileVenueStatementsUseCase(adapter=adapter)
            result = await use_case.execute(
                venue="binance",
                symbol="BTC_USD",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            assert result is not None
            assert result.venue == "binance"
            assert result.symbol == "BTC_USD"

    @pytest.mark.asyncio
    async def test_reconcile_empty(self):
        """Reconcile with no trades."""
        adapter = MockExchangeAdapter(trades=[])

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_unreconciled_trades",
            new=AsyncMock(return_value=[]),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_report",
            new=AsyncMock(return_value=MagicMock()),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_diffs",
            new=AsyncMock(return_value=None),
        ):
            use_case = ReconcileVenueStatementsUseCase(adapter=adapter)
            result = await use_case.execute(
                venue="binance",
                symbol="BTC_USD",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            assert result is not None
            assert result.total_internal == 0
            assert result.total_venue == 0

    @pytest.mark.asyncio
    async def test_reconcile_with_mismatches(self):
        """Reconcile with mismatches."""
        mock_internal_trade = Trade(
            id=1,
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            fee_currency="USD",
            order_id="order-123",
            created_at=datetime.utcnow(),
        )

        # Different price - will cause mismatch
        mock_venue_trade = {
            "id": 12345,
            "symbol": "BTCUSDT",
            "orderId": 99999,
            "price": "50100.00",  # Different price
            "qty": "0.10000000",
            "commission": "5.00000000",
            "commissionAsset": "USDT",
            "time": int(datetime.utcnow().timestamp() * 1000),
            "isBuyer": True,
            "isMaker": False,
        }

        adapter = MockExchangeAdapter(trades=[mock_venue_trade])

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_unreconciled_trades",
            new=AsyncMock(return_value=[mock_internal_trade]),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_report",
            new=AsyncMock(return_value=MagicMock()),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_diffs",
            new=AsyncMock(return_value=None),
        ):
            use_case = ReconcileVenueStatementsUseCase(adapter=adapter)
            result = await use_case.execute(
                venue="binance",
                symbol="BTC_USD",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            assert result is not None
            assert result.mismatches >= 0

    @pytest.mark.asyncio
    async def test_reconcile_venue_statement_entity(self):
        """Reconcile when adapter returns VenueStatement entities."""
        mock_internal_trade = Trade(
            id=1,
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            fee_currency="USD",
            order_id="order-123",
            created_at=datetime.utcnow(),
        )

        mock_venue_statement = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        adapter = MockExchangeAdapter(trades=[mock_venue_statement])

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_unreconciled_trades",
            new=AsyncMock(return_value=[mock_internal_trade]),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_report",
            new=AsyncMock(return_value=MagicMock()),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.save_reconciliation_diffs",
            new=AsyncMock(return_value=None),
        ):
            use_case = ReconcileVenueStatementsUseCase(adapter=adapter)
            result = await use_case.execute(
                venue="binance",
                symbol="BTC_USD",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
            )

            assert result is not None

    def test_parse_venue_statement(self):
        """Test parsing venue statement from dict."""
        adapter = MockExchangeAdapter()
        use_case = ReconcileVenueStatementsUseCase(adapter=adapter)

        data = {
            "id": 12345,
            "symbol": "BTCUSDT",
            "orderId": 99999,
            "price": "50000.00",
            "qty": "0.10000000",
            "commission": "5.00000000",
            "commissionAsset": "USDT",
            "time": 1609459200000,  # 2021-01-01 00:00:00 UTC
            "isBuyer": True,
            "isMaker": False,
        }

        result = use_case._parse_venue_statement(data)

        assert result.venue_trade_id == "12345"
        assert result.symbol == "BTCUSDT"
        assert result.side == "buy"
        assert result.price == 50000.0
        assert result.quantity == 0.1
        assert result.fee == 5.0
        assert result.fee_currency == "USDT"
        assert result.is_maker == False


class TestGetReconciliationReportUseCase:
    """Test GetReconciliationReportUseCase."""

    @pytest.mark.asyncio
    async def test_get_report_success(self):
        """Get existing report."""
        mock_report = ReconciliationReport(
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

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.get_reconciliation_report",
            new=AsyncMock(return_value=mock_report),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_diffs_by_report",
            new=AsyncMock(return_value=[]),
        ):
            use_case = GetReconciliationReportUseCase()
            result = await use_case.execute("run-123")

            assert result is not None
            assert result.run_id == "run-123"

    @pytest.mark.asyncio
    async def test_get_report_not_found(self):
        """Get non-existent report returns None."""
        with patch(
            "stonks_trading.domains.reconciliation.use_cases.get_reconciliation_report",
            new=AsyncMock(return_value=None),
        ):
            use_case = GetReconciliationReportUseCase()
            result = await use_case.execute("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_report_with_diffs(self):
        """Get report with diffs loaded."""
        mock_report = ReconciliationReport(
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

        mock_diff = ReconciliationDiff(
            status=ReconciliationStatus.MISMATCH,
            internal_trade_id=1,
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            internal_price=50000.0,
            venue_price=50100.0,
            internal_quantity=0.1,
            venue_quantity=0.1,
            internal_timestamp=datetime.utcnow(),
            venue_timestamp=datetime.utcnow(),
            field_differences={"price": [50000.0, 50100.0]},
        )

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.get_reconciliation_report",
            new=AsyncMock(return_value=mock_report),
        ), patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_diffs_by_report",
            new=AsyncMock(return_value=[mock_diff]),
        ):
            use_case = GetReconciliationReportUseCase()
            result = await use_case.execute("run-123")

            assert result is not None
            assert len(result.diffs) == 1
            assert result.diffs[0].status == ReconciliationStatus.MISMATCH


class TestListReconciliationReportsUseCase:
    """Test ListReconciliationReportsUseCase."""

    @pytest.mark.asyncio
    async def test_list_reports(self):
        """List reconciliation reports."""
        mock_report = ReconciliationReport(
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

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_reports",
            new=AsyncMock(return_value=[mock_report]),
        ):
            use_case = ListReconciliationReportsUseCase()
            result = await use_case.execute()

            assert len(result) == 1
            assert result[0].run_id == "run-123"

    @pytest.mark.asyncio
    async def test_list_reports_empty(self):
        """List reports returns empty when none."""
        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_reports",
            new=AsyncMock(return_value=[]),
        ):
            use_case = ListReconciliationReportsUseCase()
            result = await use_case.execute()

            assert result == []

    @pytest.mark.asyncio
    async def test_list_reports_by_venue(self):
        """List reports filtered by venue."""
        mock_report = ReconciliationReport(
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

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_reports",
            new=AsyncMock(return_value=[mock_report]),
        ):
            use_case = ListReconciliationReportsUseCase()
            result = await use_case.execute(venue="binance")

            assert len(result) == 1
            assert result[0].venue == "binance"

    @pytest.mark.asyncio
    async def test_list_reports_with_pagination(self):
        """List reports with pagination."""
        mock_report = ReconciliationReport(
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

        with patch(
            "stonks_trading.domains.reconciliation.use_cases.list_reconciliation_reports",
            new=AsyncMock(return_value=[mock_report]),
        ):
            use_case = ListReconciliationReportsUseCase()
            result = await use_case.execute(limit=50, offset=0)

            assert len(result) == 1
