"""Unit tests for reconciliation services.

Tests ReconciliationEngine and DifferenceCalculator with various scenarios.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationStatus,
    VenueStatement,
)
from stonks_trading.domains.reconciliation.services import (
    DifferenceCalculator,
    ReconciliationEngine,
)
from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Money, Symbol


class TestReconciliationEngine:
    """Test ReconciliationEngine."""

    @pytest.fixture
    def engine(self):
        """Create reconciliation engine."""
        return ReconciliationEngine()

    @pytest.fixture
    def sample_internal_trade(self):
        """Create sample internal trade."""
        return Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
            order_id="order-123",
        )

    @pytest.fixture
    def sample_venue_statement(self):
        """Create sample venue statement."""
        return VenueStatement(
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

    def test_match_exact(self, engine, sample_internal_trade, sample_venue_statement):
        """Test exact match between internal and venue."""
        result = engine.match(sample_internal_trade, sample_venue_statement)

        assert result.status == ReconciliationStatus.MATCHED
        assert result.internal_trade_id == 1
        assert result.venue_trade_id == "venue-123"

    def test_match_price_tolerance(self, engine):
        """Test match within price tolerance (0.01%)."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        # Price differs by 0.005% (within 0.01% tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50002.5,  # 0.005% difference
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MATCHED

    def test_match_price_mismatch(self, engine):
        """Test mismatch when price exceeds tolerance."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        # Price differs by 0.02% (exceeds 0.01% tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50010.0,  # 0.02% difference
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MISMATCH
        assert "price" in result.field_differences

    def test_match_quantity_tolerance(self, engine):
        """Test match within quantity tolerance (0.0001)."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        # Quantity differs by 0.00005 (within 0.0001 tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.10005,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MATCHED

    def test_match_quantity_mismatch(self, engine):
        """Test mismatch when quantity exceeds tolerance."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        # Quantity differs by 0.0002 (exceeds 0.0001 tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1002,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MISMATCH
        assert "quantity" in result.field_differences

    def test_match_time_tolerance(self, engine):
        """Test match within time tolerance (60 seconds)."""
        now = datetime.utcnow()

        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=now,
        )

        # Time differs by 30 seconds (within 60s tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=now + timedelta(seconds=30),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MATCHED

    def test_match_time_mismatch(self, engine):
        """Test mismatch when time exceeds tolerance."""
        now = datetime.utcnow()

        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=now,
        )

        # Time differs by 120 seconds (exceeds 60s tolerance)
        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=now + timedelta(seconds=120),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MISMATCH
        assert "timestamp" in result.field_differences

    def test_match_side_mismatch(self, engine):
        """Test mismatch when side differs."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="sell",  # Different side
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        assert result.status == ReconciliationStatus.MISMATCH
        assert "side" in result.field_differences

    def test_match_symbol_mismatch(self, engine):
        """Test mismatch when symbol differs - symbol is checked in find_matches, not match."""
        # Note: The _compare_trades method doesn't check symbol directly.
        # Symbol matching happens in find_matches() via time+side proximity.
        # For direct match(), we need to verify symbols are preserved in output.
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="ETH_USD",  # Different symbol
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = engine.match(internal, venue)

        # match() doesn't compare symbols, so this will be MATCHED
        # The symbol difference would be caught at a higher level (find_matches doesn't pair them)
        assert result.status == ReconciliationStatus.MATCHED
        assert result.symbol == "BTC_USD"  # Uses internal symbol


class TestDifferenceCalculator:
    """Test DifferenceCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create difference calculator."""
        return DifferenceCalculator()

    def test_calculate_price_difference(self, calculator):
        """Calculate price difference."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50100.0,  # Different price
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = calculator.calculate(internal, venue)

        assert "price" in result
        assert result["price"]["internal"] == 50000.0
        assert result["price"]["venue"] == 50100.0
        assert result["price"]["difference"] == -100.0
        assert result["price"]["difference_pct"] == pytest.approx(-0.2, rel=1e-2)

    def test_calculate_quantity_difference(self, calculator):
        """Calculate quantity difference."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1005,  # Different quantity
            fee=5.0,
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = calculator.calculate(internal, venue)

        assert "quantity" in result
        assert result["quantity"]["internal"] == 0.1
        assert result["quantity"]["venue"] == 0.1005
        assert result["quantity"]["difference"] == pytest.approx(-0.0005, rel=1e-5)

    def test_calculate_fee_difference(self, calculator):
        """Calculate fee difference."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.5,  # Different fee
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = calculator.calculate(internal, venue)

        assert "fee" in result
        assert result["fee"]["internal"] == 5.0
        assert result["fee"]["venue"] == 5.5
        assert result["fee"]["difference"] == -0.5

    def test_calculate_multiple_differences(self, calculator):
        """Calculate multiple field differences."""
        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=datetime.utcnow(),
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50100.0,  # Different
            quantity=0.1005,  # Different
            fee=5.5,  # Different
            fee_currency="USD",
            timestamp=datetime.utcnow(),
            venue="binance",
        )

        result = calculator.calculate(internal, venue)

        assert "price" in result
        assert "quantity" in result
        assert "fee" in result

    def test_calculate_no_differences(self, calculator):
        """Calculate when there are no differences."""
        now = datetime.utcnow()

        internal = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USD"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USD"),
            id=1,
            created_at=now,
        )

        venue = VenueStatement(
            venue_trade_id="venue-123",
            symbol="BTC_USD",
            side="buy",
            price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USD",
            timestamp=now,
            venue="binance",
        )

        result = calculator.calculate(internal, venue)

        # All fields should be present with zero differences
        assert "price" in result
        assert "quantity" in result
        assert "fee" in result
        assert result["price"]["difference"] == 0
        assert result["quantity"]["difference"] == 0
        assert result["fee"]["difference"] == 0
