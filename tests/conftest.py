"""Shared pytest fixtures for all tests."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from faker import Faker
from hypothesis import settings

from stonks_trading.domains.trading.entities import Position, Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.services import (
    FeeCalculator,
    InstrumentMapper,
    RiskChecker,
)
from stonks_trading.domains.trading.value_objects import Money, Symbol

# Initialize Faker
fake = Faker()

# Hypothesis configuration
settings.register_profile("ci", max_examples=100, deadline=None)
settings.register_profile("dev", max_examples=50, deadline=None)
settings.register_profile("debug", max_examples=10, deadline=None, verbosity=2)

# Load profile from env or use default
import os
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def sample_symbol() -> Symbol:
    """Return a sample trading symbol."""
    return Symbol(value="BTC_USD")


@pytest.fixture
def sample_money() -> Money:
    """Return sample money amount."""
    return Money(amount=50000.0, currency="USD")


@pytest.fixture
def sample_trade() -> Trade:
    """Return a sample trade."""
    return Trade(
        symbol=Symbol(value="BTC_USD"),
        side=Side.BUY,
        fill_price=Money(amount=50000.0, currency="USD"),
        quantity=0.1,
        fee=Money(amount=5.0, currency="USD"),
        id=1,
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_position() -> Position:
    """Return a sample open position."""
    return Position(
        symbol=Symbol(value="BTC_USD"),
        quantity=0.1,
        entry_price=Money(amount=50000.0, currency="USD"),
        id=1,
    )


@pytest.fixture
def risk_checker() -> RiskChecker:
    """Return default risk checker."""
    return RiskChecker()


@pytest.fixture
def fee_calculator() -> FeeCalculator:
    """Return default fee calculator."""
    return FeeCalculator()


@pytest.fixture
def instrument_mapper() -> InstrumentMapper:
    """Return default instrument mapper."""
    return InstrumentMapper()


@pytest.fixture
def sample_ohlcv_data() -> pd.DataFrame:
    """Return sample OHLCV data with features."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1min")
    np.random.seed(42)

    data = {
        "Open": 50000 + np.cumsum(np.random.randn(100) * 10),
        "High": 50000 + np.cumsum(np.random.randn(100) * 10) + np.abs(np.random.randn(100) * 5),
        "Low": 50000 + np.cumsum(np.random.randn(100) * 10) - np.abs(np.random.randn(100) * 5),
        "Close": 50000 + np.cumsum(np.random.randn(100) * 10),
        "Volume": np.random.uniform(1, 10, 100),
        "trend_1h": np.random.randn(100) * 0.01,
        "rsi_1h": np.random.uniform(0.3, 0.7, 100),
        "rsi_15m": np.random.uniform(0.3, 0.7, 100),
        "roc": np.random.randn(100) * 0.001,
        "bb_width": np.random.uniform(0.01, 0.05, 100),
    }

    df = pd.DataFrame(data, index=dates)
    df.index.name = "Datetime"
    return df


@pytest.fixture
def sample_neat_config():
    """Return sample NEAT configuration."""
    from stonks_trading.domains.trading.neat.config_builder import NeatConfig

    return NeatConfig(
        pop_size=10,
        num_generations=5,
        num_inputs=7,
        num_outputs=2,
    )


# =============================================================================
# Faker Fixtures for Generating Test Data
# =============================================================================


@pytest.fixture
def fake_symbol() -> Symbol:
    """Generate a random trading symbol using Faker."""
    symbols = ["BTC_USD", "ETH_USD", "XRP_USD", "SOL_USD", "ADA_USD"]
    return Symbol(value=fake.random_element(symbols))


@pytest.fixture
def fake_money() -> Money:
    """Generate random money amount using Faker."""
    currencies = ["USD", "USDT", "BTC", "ETH"]
    return Money(
        amount=fake.pyfloat(min_value=0.01, max_value=100000.0, right_digits=2),
        currency=fake.random_element(currencies),
    )


@pytest.fixture
def fake_trade() -> Trade:
    """Generate a random trade using Faker."""
    symbols = ["BTC_USD", "ETH_USD", "XRP_USD"]
    sides = [Side.BUY, Side.SELL]

    return Trade(
        symbol=Symbol(value=fake.random_element(symbols)),
        side=fake.random_element(sides),
        fill_price=Money(
            amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
            currency="USD",
        ),
        quantity=fake.pyfloat(min_value=0.001, max_value=10.0, right_digits=4),
        fee=Money(
            amount=fake.pyfloat(min_value=0.1, max_value=100.0, right_digits=2),
            currency="USD",
        ),
        id=fake.random_int(min=1, max=10000),
        created_at=fake.date_time_this_year(),
    )


@pytest.fixture
def fake_position() -> Position:
    """Generate a random position using Faker."""
    symbols = ["BTC_USD", "ETH_USD", "XRP_USD"]

    return Position(
        symbol=Symbol(value=fake.random_element(symbols)),
        quantity=fake.pyfloat(min_value=0.0, max_value=5.0, right_digits=4),
        entry_price=Money(
            amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
            currency="USD",
        ),
        id=fake.random_int(min=1, max=10000),
    )
