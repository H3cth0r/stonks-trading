"""Unit tests for capital domain.

Tests capital management entities.
"""

from datetime import datetime

import pytest

from stonks_trading.domains.capital.entities import CapitalAllocation, CapitalPool
from stonks_trading.domains.trading.value_objects import Money


class TestCapitalPool:
    """Test CapitalPool entity."""

    def test_creation(self):
        """CapitalPool can be created."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Trading Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=100000.0, currency="USDT"),
        )
        assert pool.pool_id == "main"
        assert pool.total_capital.amount == 100000.0

    def test_allocate(self):
        """allocate moves capital from available to reserved."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=100000.0, currency="USDT"),
            reserved_capital=Money(amount=0.0, currency="USDT"),
        )
        pool.allocate("neat_swing", "bot_1", Money(amount=50000.0, currency="USDT"))

        assert pool.available_capital.amount == 50000.0
        assert pool.reserved_capital.amount == 50000.0

    def test_allocate_raises_on_insufficient(self):
        """allocate raises when amount exceeds available."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=10000.0, currency="USDT"),
            reserved_capital=Money(amount=0.0, currency="USDT"),
        )
        with pytest.raises(ValueError, match="Insufficient"):
            pool.allocate("neat_swing", "bot_1", Money(amount=50000.0, currency="USDT"))

    def test_deallocate(self):
        """deallocate returns capital to available pool."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=50000.0, currency="USDT"),
            reserved_capital=Money(amount=50000.0, currency="USDT"),
        )
        pool.deallocate(Money(amount=25000.0, currency="USDT"))

        assert pool.available_capital.amount == 75000.0
        assert pool.reserved_capital.amount == 25000.0

    def test_deallocate_raises_on_exceed(self):
        """deallocate raises when amount exceeds reserved."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=50000.0, currency="USDT"),
            reserved_capital=Money(amount=10000.0, currency="USDT"),
        )
        with pytest.raises(ValueError, match="Cannot deallocate"):
            pool.deallocate(Money(amount=50000.0, currency="USDT"))

    def test_utilization_pct(self):
        """utilization_pct calculates percentage."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=100000.0, currency="USDT"),
            available_capital=Money(amount=50000.0, currency="USDT"),
            reserved_capital=Money(amount=50000.0, currency="USDT"),
        )
        assert pool.utilization_pct() == 50.0

    def test_utilization_pct_zero_total(self):
        """utilization_pct handles zero total."""
        pool = CapitalPool(
            pool_id="main",
            name="Main Pool",
            total_capital=Money(amount=0.0, currency="USDT"),
            available_capital=Money(amount=0.0, currency="USDT"),
            reserved_capital=Money(amount=0.0, currency="USDT"),
        )
        assert pool.utilization_pct() == 0.0


class TestCapitalAllocation:
    """Test CapitalAllocation entity."""

    def test_creation(self):
        """CapitalAllocation can be created."""
        alloc = CapitalAllocation(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            allocated_amount=Money(amount=50000.0, currency="USDT"),
        )
        assert alloc.bot_type == "neat_swing"
        assert alloc.allocated_amount.amount == 50000.0

    def test_current_return(self):
        """current_return calculates profit/loss."""
        alloc = CapitalAllocation(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            allocated_amount=Money(amount=10000.0, currency="USDT"),
            current_value=Money(amount=12000.0, currency="USDT"),
        )
        ret = alloc.current_return()
        assert ret is not None
        assert ret.amount == 2000.0

    def test_current_return_no_current_value(self):
        """current_return returns None if no current_value."""
        alloc = CapitalAllocation(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            allocated_amount=Money(amount=10000.0, currency="USDT"),
        )
        assert alloc.current_return() is None
