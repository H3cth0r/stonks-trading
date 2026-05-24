"""Reusable testing utilities for Hypothesis and Faker.

This module provides shared strategies, fixtures, and utilities
for property-based testing across the codebase.
"""

from typing import Any

import numpy as np
import pandas as pd
from faker import Faker
from hypothesis import strategies as st

from stonks_trading.domains.trading.entities import (
    Balance,
    Genome,
    OrderResult,
    Position,
    RiskCheckResult,
    RiskEvent,
    Trade,
)
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.value_objects import Money, Symbol

# Initialize Faker with seed for reproducibility
fake = Faker()
Faker.seed(12345)


# =============================================================================
# Hypothesis Strategies
# =============================================================================


def symbol_strategy() -> st.SearchStrategy[Symbol]:
    """Strategy for generating valid trading symbols."""
    symbols = ["BTC_USD", "ETH_USD", "XRP_USD", "SOL_USD", "ADA_USD", "DOT_USD"]
    return st.sampled_from([Symbol(value=s) for s in symbols])


def side_strategy() -> st.SearchStrategy[Side]:
    """Strategy for generating trade sides."""
    return st.sampled_from([Side.BUY, Side.SELL])


def money_strategy(
    min_value: float = 0.01,
    max_value: float = 1000000.0,
    currency: str = "USD",
) -> st.SearchStrategy[Money]:
    """Strategy for generating Money value objects."""
    return st.builds(
        Money,
        amount=st.floats(
            min_value=min_value, max_value=max_value, allow_nan=False, allow_infinity=False
        ),
        currency=st.just(currency),
    )


def risk_level_strategy() -> st.SearchStrategy[RiskLevel]:
    """Strategy for generating risk levels."""
    return st.sampled_from(
        [RiskLevel.OK, RiskLevel.WARNING, RiskLevel.CRITICAL, RiskLevel.EMERGENCY]
    )


def trade_strategy() -> st.SearchStrategy[Trade]:
    """Strategy for generating Trade entities with Faker data."""

    def make_trade() -> Trade:
        return Trade(
            symbol=Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"])),
            side=fake.random_element([Side.BUY, Side.SELL]),
            fill_price=Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            ),
            quantity=fake.pyfloat(min_value=0.001, max_value=10.0, right_digits=4),
            fee=Money(
                amount=fake.pyfloat(min_value=0.1, max_value=100.0, right_digits=2),
                currency="USD",
            ),
            id=fake.random_int(min=1, max=100000),
            created_at=fake.date_time_this_year(),
            order_id=fake.uuid4(),
            venue_trade_id=fake.uuid4(),
        )

    return st.builds(lambda: make_trade())


def position_strategy() -> st.SearchStrategy[Position]:
    """Strategy for generating Position entities with Faker data."""

    def make_position() -> Position:
        return Position(
            symbol=Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"])),
            quantity=fake.pyfloat(min_value=0.0, max_value=5.0, right_digits=4),
            entry_price=Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            ),
            id=fake.random_int(min=1, max=100000),
            created_at=fake.date_time_this_year(),
            updated_at=fake.date_time_this_year(),
        )

    return st.builds(lambda: make_position())


def order_result_strategy() -> st.SearchStrategy[OrderResult]:
    """Strategy for generating OrderResult entities."""

    def make_order_result() -> OrderResult:
        success = fake.boolean()
        return OrderResult(
            success=success,
            order_id=fake.uuid4(),
            fill_price=Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            )
            if success
            else None,
            filled_quantity=fake.pyfloat(min_value=0.001, max_value=10.0, right_digits=4)
            if success
            else 0.0,
            fee=Money(
                amount=fake.pyfloat(min_value=0.1, max_value=100.0, right_digits=2),
                currency="USD",
            )
            if success
            else None,
            timestamp=fake.date_time_this_year(),
        )

    return st.builds(lambda: make_order_result())


def balance_strategy() -> st.SearchStrategy[Balance]:
    """Strategy for generating Balance entities."""

    def make_balance() -> Balance:
        free = fake.pyfloat(min_value=0.0, max_value=1000.0, right_digits=4)
        locked = fake.pyfloat(min_value=0.0, max_value=100.0, right_digits=4)
        return Balance(
            asset=fake.random_element(["BTC", "ETH", "USDT", "USD", "SOL"]),
            free=free,
            locked=locked,
            total=free + locked,
        )

    return st.builds(lambda: make_balance())


def genome_strategy() -> st.SearchStrategy[Genome]:
    """Strategy for generating Genome entities."""

    def make_genome() -> Genome:
        return Genome(
            genome_data=b"test_genome_data",
            fitness=fake.pyfloat(min_value=-1000.0, max_value=1000.0, right_digits=4),
            generation=fake.random_int(min=0, max=1000),
            symbol=Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"])),
            fee_rate=fake.pyfloat(min_value=0.0001, max_value=0.01, right_digits=4),
            slippage_bps=fake.random_int(min=0, max=100),
            mode=fake.random_element(["backtest", "dry_run", "live"]),
            is_active=fake.boolean(),
            trades_count=fake.random_int(min=0, max=1000),
            max_drawdown=fake.pyfloat(min_value=0.0, max_value=0.5, right_digits=4),
            total_return=fake.pyfloat(min_value=-1.0, max_value=10.0, right_digits=4),
            notes=fake.text(max_nb_chars=200),
        )

    return st.builds(lambda: make_genome())


def risk_check_result_strategy() -> st.SearchStrategy[RiskCheckResult]:
    """Strategy for generating RiskCheckResult entities."""

    def make_risk_check_result() -> RiskCheckResult:
        allowed = fake.boolean()
        return RiskCheckResult(
            allowed=allowed,
            risk_level=RiskLevel.OK
            if allowed
            else fake.random_element([RiskLevel.WARNING, RiskLevel.CRITICAL]),
            reason=None
            if allowed
            else fake.random_element(
                [
                    "Max drawdown exceeded",
                    "Daily trade limit reached",
                    "Position size exceeds limit",
                ]
            ),
        )

    return st.builds(lambda: make_risk_check_result())


def risk_event_strategy() -> st.SearchStrategy[RiskEvent]:
    """Strategy for generating RiskEvent entities."""

    def make_risk_event() -> RiskEvent:
        return RiskEvent(
            event_type=fake.random_element(["drawdown_breach", "trade_limit", "kill_switch"]),
            severity=fake.random_element([RiskLevel.WARNING.value, RiskLevel.CRITICAL.value]),
            message=fake.sentence(nb_words=10),
            symbol=Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"])),
            metric_name="drawdown",
            metric_value=fake.pyfloat(min_value=0.1, max_value=0.5, right_digits=4),
            threshold_value=0.15,
            portfolio_value=Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            ),
            created_at=fake.date_time_this_year(),
        )

    return st.builds(lambda: make_risk_event())


def ohlcv_data_strategy(rows: int = 100) -> st.SearchStrategy[pd.DataFrame]:
    """Strategy for generating OHLCV DataFrame with features."""

    def make_ohlcv() -> pd.DataFrame:
        dates = pd.date_range(start="2024-01-01", periods=rows, freq="1min")
        np.random.seed(fake.random_int(min=0, max=10000))

        data = {
            "Open": 50000 + np.cumsum(np.random.randn(rows) * 10),
            "High": 50000
            + np.cumsum(np.random.randn(rows) * 10)
            + np.abs(np.random.randn(rows) * 5),
            "Low": 50000
            + np.cumsum(np.random.randn(rows) * 10)
            - np.abs(np.random.randn(rows) * 5),
            "Close": 50000 + np.cumsum(np.random.randn(rows) * 10),
            "Volume": np.random.uniform(1, 10, rows),
            "trend_1h": np.random.randn(rows) * 0.01,
            "rsi_1h": np.random.uniform(0.3, 0.7, rows),
            "rsi_15m": np.random.uniform(0.3, 0.7, rows),
            "roc": np.random.randn(rows) * 0.001,
            "bb_width": np.random.uniform(0.01, 0.05, rows),
        }

        df = pd.DataFrame(data, index=dates)
        df.index.name = "Datetime"
        return df

    return st.builds(lambda: make_ohlcv())


# =============================================================================
# Faker Data Generators
# =============================================================================


def generate_fake_trade(**overrides: Any) -> Trade:
    """Generate a fake Trade entity with optional overrides."""
    return Trade(
        symbol=overrides.get(
            "symbol", Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"]))
        ),
        side=overrides.get("side", fake.random_element([Side.BUY, Side.SELL])),
        fill_price=overrides.get(
            "fill_price",
            Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            ),
        ),
        quantity=overrides.get(
            "quantity", fake.pyfloat(min_value=0.001, max_value=10.0, right_digits=4)
        ),
        fee=overrides.get(
            "fee",
            Money(
                amount=fake.pyfloat(min_value=0.1, max_value=100.0, right_digits=2),
                currency="USD",
            ),
        ),
        id=overrides.get("id", fake.random_int(min=1, max=100000)),
        created_at=overrides.get("created_at", fake.date_time_this_year()),
        order_id=overrides.get("order_id", fake.uuid4()),
        venue_trade_id=overrides.get("venue_trade_id", fake.uuid4()),
    )


def generate_fake_position(**overrides: Any) -> Position:
    """Generate a fake Position entity with optional overrides."""
    return Position(
        symbol=overrides.get(
            "symbol", Symbol(value=fake.random_element(["BTC_USD", "ETH_USD", "XRP_USD"]))
        ),
        quantity=overrides.get(
            "quantity", fake.pyfloat(min_value=0.0, max_value=5.0, right_digits=4)
        ),
        entry_price=overrides.get(
            "entry_price",
            Money(
                amount=fake.pyfloat(min_value=1000.0, max_value=100000.0, right_digits=2),
                currency="USD",
            ),
        ),
        id=overrides.get("id", fake.random_int(min=1, max=100000)),
        created_at=overrides.get("created_at", fake.date_time_this_year()),
        updated_at=overrides.get("updated_at", fake.date_time_this_year()),
    )


def generate_fake_money(**overrides: Any) -> Money:
    """Generate fake Money with optional overrides."""
    return Money(
        amount=overrides.get(
            "amount", fake.pyfloat(min_value=0.01, max_value=1000000.0, right_digits=2)
        ),
        currency=overrides.get("currency", fake.random_element(["USD", "MXN", "BTC", "ETH"])),
    )


def generate_fake_symbol(**overrides: Any) -> Symbol:
    """Generate fake Symbol with optional overrides."""
    symbols = ["BTC_USD", "ETH_USD", "XRP_USD", "SOL_USD", "ADA_USD"]
    return Symbol(value=overrides.get("value", fake.random_element(symbols)))


# =============================================================================
# Common Test Patterns
# =============================================================================


def assert_trade_valid(trade: Trade) -> None:
    """Assert that a Trade entity is valid."""
    assert trade.symbol is not None
    assert trade.side in [Side.BUY, Side.SELL]
    assert trade.fill_price.amount > 0
    assert trade.quantity > 0
    assert trade.fee.amount >= 0


def assert_position_valid(position: Position) -> None:
    """Assert that a Position entity is valid."""
    assert position.symbol is not None
    assert position.quantity >= 0
    if position.quantity > 0:
        assert position.entry_price is not None
        assert position.entry_price.amount > 0


def assert_money_valid(money: Money) -> None:
    """Assert that a Money value object is valid."""
    assert money.currency in ["USD", "USDT", "BTC", "ETH", "EUR", "GBP"]
    assert len(money.currency) == 3
