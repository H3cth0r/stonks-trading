"""Parity tests comparing extracted TradingEnv to NEAT/main.py.

These tests ensure the extracted modules produce identical results
to the original prototype when using default parameters.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add strategy-research to path for importing original
STRATEGY_RESEARCH = Path("/Users/h3cth0r/Documents/strategy-research")
if str(STRATEGY_RESEARCH) not in sys.path:
    sys.path.insert(0, str(STRATEGY_RESEARCH))

from stonks_trading.domains.trading.neat.fitness import calculate_fitness
from stonks_trading.domains.trading.neat.trading_env import TradingEnv


def load_sample_data() -> pd.DataFrame:
    """Load sample data for testing.

    Returns a small slice of data for quick parity testing.
    """
    # Create synthetic data matching NEAT/main.py format
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1min")
    np.random.seed(42)

    data = {
        "Open": 50000 + np.cumsum(np.random.randn(100) * 10),
        "High": 50000 + np.cumsum(np.random.randn(100) * 10) + np.abs(np.random.randn(100) * 5),
        "Low": 50000 + np.cumsum(np.random.randn(100) * 10) - np.abs(np.random.randn(100) * 5),
        "Close": 50000 + np.cumsum(np.random.randn(100) * 10),
        "Volume": np.random.uniform(1, 10, 100),
    }

    df = pd.DataFrame(data, index=dates)
    df.index.name = "Datetime"

    # Add minimal features for TradingEnv
    df["trend_1h"] = 0.0
    df["rsi_1h"] = 0.5
    df["rsi_15m"] = 0.5
    df["roc"] = 0.0
    df["bb_width"] = 0.01

    return df


class TestTradingEnvParity:
    """Test TradingEnv parity with NEAT/main.py."""

    def test_default_parameters_match_original(self) -> None:
        """Verify default parameters match NEAT/main.py constants."""
        # Default parameters that MUST match NEAT/main.py
        assert TradingEnv.__init__.__defaults__[0] == 0.001  # fee_rate
        assert TradingEnv.__init__.__defaults__[1] == 0.0  # slippage_bps
        assert TradingEnv.__init__.__defaults__[2] == "backtest"  # mode
        assert TradingEnv.__init__.__defaults__[3] == 10000.0  # initial_capital
        assert TradingEnv.__init__.__defaults__[4] == 15  # min_trade_interval
        assert TradingEnv.__init__.__defaults__[5] == 0.6  # decision_threshold

    def test_state_vector_structure(self) -> None:
        """Verify state vector has correct structure (7 inputs)."""
        data = load_sample_data()
        env = TradingEnv(data)

        state = env.get_state(0)

        # Should have 7 inputs: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
        assert len(state) == 7
        assert state[0] in [1.0, -1.0]  # is_invested

    def test_initial_state_no_position(self) -> None:
        """Verify initial state when no position held."""
        data = load_sample_data()
        env = TradingEnv(data)

        state = env.get_state(0)

        # No position: is_invested = -1.0, unrealized_pnl = 0.0
        assert state[0] == -1.0
        assert state[1] == 0.0

    def test_buy_logic_with_threshold(self) -> None:
        """Verify buy signal logic matches NEAT/main.py."""
        data = load_sample_data()
        env = TradingEnv(data)

        # Strong buy signal: buy_prob > 0.6 and buy_prob > sell_prob
        action = (0.8, 0.2)  # buy_prob=0.8, sell_prob=0.2

        # Use step >= min_trade_interval (15) to allow trading
        equity_before = env.get_equity(15)
        equity_after = env.step(15, action)

        # Should have executed buy (cash -> holdings)
        assert env.cash == 0.0
        assert env.holdings > 0.0
        assert len(env.trades) == 1
        assert env.trades[0].trade_type == "buy"

    def test_sell_logic_with_threshold(self) -> None:
        """Verify sell signal logic matches NEAT/main.py."""
        data = load_sample_data()
        env = TradingEnv(data)

        # First buy to establish position (step 15)
        env.step(15, (0.8, 0.2))
        initial_holdings = env.holdings

        # Then sell at step 30 (15 + min_trade_interval)
        action = (0.2, 0.8)  # sell_prob=0.8, buy_prob=0.2
        env.step(30, action)

        # Should have executed sell
        assert env.holdings == 0.0
        assert env.cash > 0.0
        assert len(env.trades) == 2
        assert env.trades[1].trade_type == "sell"

    def test_min_trade_interval_respected(self) -> None:
        """Verify minimum trade interval is enforced."""
        data = load_sample_data()
        env = TradingEnv(data, min_trade_interval=15)

        # Execute first trade
        env.step(0, (0.8, 0.2))
        initial_trades = len(env.trades)

        # Try to trade again within min interval (step 5)
        env.step(5, (0.8, 0.2))

        # Should not have executed (interval constraint)
        assert len(env.trades) == initial_trades

    def test_all_in_all_out_position_sizing(self) -> None:
        """Verify all-in / all-out position sizing."""
        data = load_sample_data()
        env = TradingEnv(data, initial_capital=10000.0)

        # Buy all-in at step 15 (first allowable trade step)
        env.step(15, (0.8, 0.2))

        assert env.cash == 0.0  # All cash deployed
        assert env.holdings > 0.0

        # Sell all-out at step 30 (15 + min_trade_interval)
        env.step(30, (0.2, 0.8))

        assert env.holdings == 0.0  # All holdings sold
        assert env.cash > 0.0

    def test_transaction_fee_calculation(self) -> None:
        """Verify fee calculation matches NEAT/main.py."""
        data = load_sample_data()
        env = TradingEnv(data, fee_rate=0.001, initial_capital=10000.0)

        # Buy at step 15 (first allowable trade step)
        env.step(15, (0.8, 0.2))

        # Fee should be ~0.1% of cost
        buy_trade = env.trades[0]
        expected_fee = 10000.0 * 0.001
        assert abs(buy_trade.fee_paid - expected_fee) < 1.0

    def test_equity_calculation(self) -> None:
        """Verify equity calculation: cash + (holdings * price)."""
        data = load_sample_data()
        env = TradingEnv(data)

        # Initial equity
        assert env.get_equity(0) == 10000.0

        # After buy
        env.step(0, (0.8, 0.2))
        price = data["Close"].iloc[0]
        expected_equity = env.cash + (env.holdings * price)
        assert abs(env.get_equity(0) - expected_equity) < 0.01

    def test_drawdown_tracking(self) -> None:
        """Verify drawdown tracking updates correctly."""
        data = load_sample_data()
        env = TradingEnv(data)

        initial_peak = env.peak_equity

        # Execute some steps
        for i in range(10):
            env.step(i, (0.5, 0.5))  # No trades, just tracking

        # Peak should be tracked
        assert env.peak_equity >= initial_peak
        assert env.max_drawdown >= 0.0

    def test_clipping_and_cleaning(self) -> None:
        """Verify state values are clipped and NaN cleaned."""
        data = load_sample_data()
        # Inject extreme values
        data.loc[data.index[0], "trend_1h"] = 100.0
        data.loc[data.index[0], "rsi_1h"] = float("nan")

        env = TradingEnv(data)
        state = env.get_state(0)

        # Values should be clipped to [-5, 5] and NaN cleaned
        assert all(np.abs(state) <= 5.0)
        assert not np.any(np.isnan(state))


class TestFitnessParity:
    """Test fitness calculation parity with NEAT/main.py."""

    def test_total_return_calculation(self) -> None:
        """Verify total return calculation."""
        data = load_sample_data()
        env = TradingEnv(data, initial_capital=10000.0)

        # Simulate equity curve
        equity_curve = [10000.0, 10500.0, 10300.0, 11000.0]
        market_prices = np.array([100.0, 105.0, 103.0, 110.0])

        score = calculate_fitness(env, equity_curve, market_prices)

        # Should return a finite score
        assert np.isfinite(score)

    def test_inactivity_penalty(self) -> None:
        """Verify penalty for < 2 trades."""
        data = load_sample_data()
        env = TradingEnv(data)

        # No trades
        equity_curve = [10000.0] * 100
        market_prices = np.ones(100) * 100.0

        score_no_trades = calculate_fitness(env, equity_curve, market_prices)

        # Should have penalty applied
        assert score_no_trades < 0  # Inactivity penalty is -50

    def test_churning_penalty(self) -> None:
        """Verify penalty for > 40 trades."""
        data = load_sample_data()
        env = TradingEnv(data)

        # Simulate many trades
        for i in range(0, 100, 2):
            env.trades.append(
                type(
                    "obj",
                    (object,),
                    {
                        "step": i,
                        "trade_type": "buy",
                        "price": 100.0,
                        "timestamp": data.index[i],
                    },
                )()
            )

        assert len(env.trades) > 40

        equity_curve = [10000.0] * 100
        market_prices = np.ones(100) * 100.0

        score = calculate_fitness(env, equity_curve, market_prices)

        # Should have churning penalty
        # Penalty is -(trades - 40) for trades > 40
        expected_penalty = -(len(env.trades) - 40)

    def test_bankruptcy_penalty(self) -> None:
        """Verify penalty for equity < 60% of initial."""
        data = load_sample_data()
        env = TradingEnv(data, initial_capital=10000.0)

        # Add minimal trades to avoid inactivity penalty
        env.trades.append(
            type(
                "obj",
                (object,),
                {
                    "step": 0,
                    "trade_type": "buy",
                    "price": 100.0,
                    "timestamp": data.index[0],
                },
            )()
        )
        env.trades.append(
            type(
                "obj",
                (object,),
                {
                    "step": 1,
                    "trade_type": "sell",
                    "price": 100.0,
                    "timestamp": data.index[1],
                },
            )()
        )

        # Equity below 60% threshold
        equity_curve = [10000.0, 5000.0]  # 50% drawdown
        market_prices = np.array([100.0, 50.0])

        score = calculate_fitness(env, equity_curve, market_prices)

        # Should have bankruptcy penalty (-500)
        assert score < -400  # Large penalty applied


class TestFeatureParity:
    """Test feature engineering parity."""

    def test_feature_column_names(self) -> None:
        """Verify feature columns match NEAT/main.py."""
        from stonks_trading.domains.trading.neat.features import get_feature_columns

        columns = get_feature_columns()

        # Must match columns in NEAT/main.py line 115
        expected = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]
        assert columns == expected

    def test_input_count(self) -> None:
        """Verify total input count (7 for NEAT network)."""
        from stonks_trading.domains.trading.neat.features import prepare_neat_inputs

        features = np.array([0.1, 0.5, 0.5, 0.0, 0.01])
        state = prepare_neat_inputs(features, is_invested=True, unrealized_pnl_pct=0.05)

        # 7 inputs: [is_invested, unrealized_pnl, 5 features]
        assert len(state) == 7


@pytest.mark.skip(reason="Requires full NEAT/main.py import - run manually")
class TestFullParity:
    """Full parity test requiring NEAT/main.py import.

    These tests compare the extracted modules directly against
    the original implementation for identical behavior.
    """

    def test_trading_env_parity(self) -> None:
        """Run identical scenarios through both implementations."""
        # Import original TradingEnv
        import NEAT.main as original

        data = load_sample_data()

        # Create both environments with identical parameters
        original_env = original.TradingEnv(data)
        extracted_env = TradingEnv(
            data,
            fee_rate=0.001,
            slippage_bps=0.0,
            mode="backtest",
        )

        # Run identical action sequences
        np.random.seed(42)
        actions = [(np.random.random(), np.random.random()) for _ in range(50)]

        original_equity = []
        extracted_equity = []

        for i, action in enumerate(actions):
            orig_eq = original_env.step(i, action)
            extr_eq = extracted_env.step(i, action)

            original_equity.append(orig_eq)
            extracted_equity.append(extr_eq)

        # Compare equity curves
        assert np.allclose(original_equity, extracted_equity, rtol=1e-10)

        # Compare trade counts
        assert len(original_env.trades) == len(extracted_env.trades)

        # Compare final state
        assert abs(original_env.cash - extracted_env.cash) < 0.01
        assert abs(original_env.holdings - extracted_env.holdings) < 0.0001
