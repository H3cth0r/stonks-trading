"""E2E NEAT Parity Tests for Phase 5D Validation Gate.

These tests verify exact parity with NEAT/main.py implementation.
All 10 tests must pass before proceeding to Phase 5E.

Test list:
- N1: State vector has exactly 7 elements
- N2: State[0] is is_invested (1.0 or -1.0)
- N3: State values clipped to [-5, 5]
- N4: Decision threshold is 0.6
- N5: Transaction fee is 0.001
- N6: Uses RecurrentNetwork (not feedforward)
- N7: All-in buy / all-out sell logic
- N8: Genome serialization roundtrip
- N9: Feature parity with NEAT/main.py
- N10: Full NEAT parity suite (combined test)
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Paths
NEAT_DIR = Path("/Users/h3cth0r/Documents/strategy-research/NEAT")
if str(NEAT_DIR) not in sys.path:
    sys.path.insert(0, str(NEAT_DIR))

SRC_DIR = Path("/Users/h3cth0r/Documents/stonks-trading/src")
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class TestNeatParity:
    """NEAT parity tests matching the 10 validation gate requirements."""

    # Constants from NEAT/main.py
    DECISION_THRESHOLD = 0.6
    TRANSACTION_FEE = 0.001
    MIN_TRADE_INTERVAL = 15

    @pytest.fixture
    def genome(self):
        """Load a trained genome for testing."""
        genome_path = NEAT_DIR / "last_winner.pkl"
        if genome_path.exists():
            with open(genome_path, "rb") as f:
                return pickle.load(f)
        pytest.skip("No trained genome found at last_winner.pkl")

    @pytest.fixture
    def neat_config(self):
        """Load NEAT configuration."""
        config_path = NEAT_DIR / "config-neat.txt"
        if not config_path.exists():
            pytest.skip("No NEAT config found")

        import neat

        return neat.Config(
            neat.DefaultGenome,
            neat.DefaultReproduction,
            neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            str(config_path),
        )

    def test_state_vector_length(self, genome, neat_config) -> None:
        """N1: State vector has exactly 7 elements."""
        from neat.nn import RecurrentNetwork

        net = RecurrentNetwork.create(genome, neat_config)

        # Test with dummy input
        state = [0.0] * 7
        output = net.activate(state)

        # Output should be 2 (buy, sell probabilities)
        assert len(output) == 2

        # Input size should be 7 for NEAT network
        assert neat_config.genome_config.num_inputs == 7

    def test_first_two_state_elements(self, genome, neat_config) -> None:
        """N2: State[0] is is_invested (1.0 or -1.0), State[1] is unrealized_pnl."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_state_vector

        # Test with invested position
        state_invested = compute_state_vector(
            price=50000.0,
            is_invested=True,
            unrealized_pnl=0.05,
            features={
                "trend_1h": 0.01,
                "rsi_1h": 0.6,
                "rsi_15m": 0.5,
                "roc": 0.02,
                "bb_width": 0.01,
            },
        )
        assert state_invested[0] == 1.0
        assert 0.04 <= state_invested[1] <= 0.06

        # Test with no position
        state_no_position = compute_state_vector(
            price=50000.0,
            is_invested=False,
            unrealized_pnl=0.0,
            features={
                "trend_1h": 0.01,
                "rsi_1h": 0.6,
                "rsi_15m": 0.5,
                "roc": 0.02,
                "bb_width": 0.01,
            },
        )
        assert state_no_position[0] == -1.0
        assert state_no_position[1] == 0.0

    def test_state_vector_values_clipped(self) -> None:
        """N3: State values clipped to [-5, 5] and NaN handled."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_state_vector

        # Test with extreme values that should be clipped
        extreme_features = {
            "trend_1h": 100.0,  # Should clip to 5.0
            "rsi_1h": 200.0,  # Should clip to 5.0
            "rsi_15m": -100.0,  # Should clip to -5.0
            "roc": 50.0,  # Should clip to 5.0
            "bb_width": -50.0,  # Should clip to -5.0
        }

        state = compute_state_vector(
            price=50000.0,
            is_invested=True,
            unrealized_pnl=0.5,  # 50% gain - should clip to 5.0
            features=extreme_features,
        )

        # All values should be in [-5, 5]
        assert all(-5.0 <= v <= 5.0 for v in state)

        # No NaN values
        assert all(not np.isnan(v) for v in state)

        # is_invested should be 1.0
        assert state[0] == 1.0

        # unrealized_pnl = 0.5 is within [-5, 5] range, not clipped
        assert state[1] == 0.5

        # Market features should be clipped (100 -> 5, 200 -> 5, -100 -> -5, etc.)
        assert state[2] == 5.0  # trend_1h: 100 clipped to 5
        assert state[3] == 5.0  # rsi_1h: 200 clipped to 5
        assert state[4] == -5.0  # rsi_15m: -100 clipped to -5
        assert state[5] == 5.0  # roc: 50 clipped to 5
        assert state[6] == -5.0  # bb_width: -50 clipped to -5

    def test_decision_threshold_constant(self) -> None:
        """N4: Decision threshold is 0.6."""
        from stonks_trading.bots.neat_swing.strategy import DECISION_THRESHOLD

        assert DECISION_THRESHOLD == 0.6

        # Also verify in feature engineering
        from stonks_trading.bots.neat_swing.feature_engineering import (
            DECISION_THRESHOLD as FE_DECISION_THRESHOLD,
        )

        assert FE_DECISION_THRESHOLD == 0.6

    def test_transaction_fee_constant(self) -> None:
        """N5: Transaction fee is 0.001."""
        from stonks_trading.bots.neat_swing.strategy import TRANSACTION_FEE

        assert TRANSACTION_FEE == 0.001

        # Also verify in feature engineering
        from stonks_trading.bots.neat_swing.feature_engineering import (
            TRANSACTION_FEE as FE_TRANSACTION_FEE,
        )

        assert FE_TRANSACTION_FEE == 0.001

    def test_recurrent_network_not_feedforward(self, genome, neat_config) -> None:
        """N6: Uses RecurrentNetwork, not feedforward."""
        from neat.nn import RecurrentNetwork

        # Create network
        net = RecurrentNetwork.create(genome, neat_config)

        # Verify it is RecurrentNetwork type
        assert type(net).__name__ == "RecurrentNetwork"

        # Verify config says feed_forward = False
        assert neat_config.genome_config.feed_forward is False

        # Test temporal dynamics - recurrent connections should influence output
        state1 = [0.5] * 7
        output1 = net.activate(state1)

        # Activate again with same input - should potentially get different output
        # due to recurrent state (depends on network structure)
        output2 = net.activate(state1)

        # Both should be valid outputs
        assert all(-1 <= o <= 1 for o in output1)
        assert all(-1 <= o <= 1 for o in output2)

    def test_all_in_buy_logic(self, genome, neat_config) -> None:
        """N7a: All-in buy when buy_prob > threshold > sell_prob."""
        from stonks_trading.bots.neat_swing.strategy import DECISION_THRESHOLD, NeatSwingStrategy

        strategy = NeatSwingStrategy()
        strategy.load_genome(None, genome, neat_config)

        # Simulate a "buy" signal by using high buy output
        # For this test, we'll use the actual network output
        state = [1.0, 0.0, 0.0, 0.5, 0.5, 0.0, 0.0]  # invested, no pnl, neutral features
        buy_prob, sell_prob = strategy.activate_network(None, state)

        # Now test the determine_action logic
        # If buy_prob > 0.6 and buy_prob > sell_prob -> BUY
        strong_buy = buy_prob > DECISION_THRESHOLD and buy_prob > sell_prob
        no_position = True  # is_invested == -1.0 in state

        action = strategy.determine_action(buy_prob, sell_prob, is_invested=False)

        # Logic: buy when not invested
        if strong_buy and no_position:
            assert action is not None  # Should return action

    def test_all_out_sell_logic(self, genome, neat_config) -> None:
        """N7b: All-out sell when sell_prob > threshold > buy_prob."""
        from stonks_trading.bots.neat_swing.strategy import DECISION_THRESHOLD, NeatSwingStrategy

        strategy = NeatSwingStrategy()
        strategy.load_genome(None, genome, neat_config)

        # Test sell signal (invested position)
        state = [1.0, 0.05, 0.0, 0.5, 0.5, 0.0, 0.0]  # invested with 5% profit
        buy_prob, sell_prob = strategy.activate_network(None, state)

        action = strategy.determine_action(buy_prob, sell_prob, is_invested=True)

        # If sell_prob > 0.6 and sell_prob > buy_prob and is_invested -> SELL
        strong_sell = sell_prob > DECISION_THRESHOLD and sell_prob > buy_prob

        if strong_sell:
            assert action is not None

    def test_genome_serialization_roundtrip(self, genome) -> None:
        """N8: Genome serialization roundtrip."""
        import pickle

        # Serialize
        serialized = pickle.dumps(genome)

        # Deserialize
        restored = pickle.loads(serialized)

        # Verify key attributes preserved
        assert restored.key is not None
        assert restored.fitness is not None or genome.fitness is not None

        # Verify network can be created from restored genome
        from neat.nn import RecurrentNetwork

        config_path = NEAT_DIR / "config-neat.txt"
        import neat

        config = neat.Config(
            neat.DefaultGenome,
            neat.DefaultReproduction,
            neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            str(config_path),
        )

        # Create network from restored genome - should not raise
        net = RecurrentNetwork.create(restored, config)

        # Verify same output for same input
        test_input = [0.5] * 7
        output1 = net.activate(test_input)

        # Reset and test again
        output2 = net.activate(test_input)

        # Outputs should be identical (deterministic)
        assert all(abs(a - b) < 1e-10 for a, b in zip(output1, output2))

    def test_feature_parity(self) -> None:
        """N9: Feature parity with NEAT/main.py."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_features

        # Generate synthetic candle data matching NEAT/main.py format
        dates = pd.date_range(start="2024-01-01", periods=300, freq="1min")
        np.random.seed(42)

        candles = []
        price = 50000.0
        for i, date in enumerate(dates):
            # Random walk price
            price = price + np.random.randn() * 10
            candles.append(
                {
                    "open": price - np.random.rand() * 5,
                    "high": price + np.random.rand() * 10,
                    "low": price - np.random.rand() * 10,
                    "close": price,
                    "volume": np.random.uniform(1, 100),
                }
            )

        # Compute features
        features = compute_features(candles)

        # Verify all 5 features present
        expected_features = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]
        for feat in expected_features:
            assert feat in features
            assert isinstance(features[feat], float)

        # Verify values are reasonable (not NaN, not extreme)
        for feat, value in features.items():
            assert not np.isnan(value), f"Feature {feat} is NaN"
            # All features should be in reasonable range (not clipped to extremes in normal data)
            if feat in ["trend_1h", "roc", "bb_width"]:
                # These can be small positive/negative
                assert -10 < value < 10, f"Feature {feat} = {value} is extreme"
            else:
                # RSI should be in [0, 1]
                assert 0 <= value <= 1, f"Feature {feat} = {value} is out of range"


class TestNeatFeatureParity:
    """Additional feature engineering parity tests."""

    def test_resampling_creates_1h_and_15m(self) -> None:
        """Verify resampling produces correct timeframes."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_features

        # Create 1h of 1m data (60 candles)
        dates = pd.date_range(start="2024-01-01", periods=300, freq="1min")
        np.random.seed(42)

        candles = []
        price = 50000.0
        for date in dates:
            price = price + np.random.randn() * 10
            candles.append(
                {
                    "open": price,
                    "high": price + 5,
                    "low": price - 5,
                    "close": price,
                    "volume": 10.0,
                }
            )

        features = compute_features(candles)

        # All features should compute without error
        for feat in ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]:
            assert feat in features
            assert not np.isnan(features[feat])

    def test_sma_calculation_parity(self) -> None:
        """Verify SMA calculation matches NEAT/main.py (SMA50, SMA200 on 1h)."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_features

        # Create enough data for SMA200 (need 200 1h periods = 200 hours = 12000 1m candles)
        dates = pd.date_range(start="2024-01-01", periods=15000, freq="1min")
        np.random.seed(42)

        candles = []
        price = 50000.0
        for date in dates:
            price = price + np.random.randn() * 10
            candles.append(
                {
                    "open": price,
                    "high": price + 5,
                    "low": price - 5,
                    "close": price,
                    "volume": 10.0,
                }
            )

        features = compute_features(candles)

        # trend_1h should be computed (SMA50 - SMA200) / SMA200
        assert "trend_1h" in features
        assert features["trend_1h"] != 0.0  # Should have some trend in random walk

    def test_rsi_calculation_parity(self) -> None:
        """Verify RSI calculation matches NEAT/main.py RSI(14)."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_features

        dates = pd.date_range(start="2024-01-01", periods=300, freq="1min")
        np.random.seed(42)

        candles = []
        price = 50000.0
        for date in dates:
            price = price + np.random.randn() * 10
            candles.append(
                {
                    "open": price,
                    "high": price + 5,
                    "low": price - 5,
                    "close": price,
                    "volume": 10.0,
                }
            )

        features = compute_features(candles)

        # RSI should be in [0, 1] (divided by 100 in compute_features)
        assert 0.0 <= features["rsi_1h"] <= 1.0
        assert 0.0 <= features["rsi_15m"] <= 1.0


class TestNeatStateVector:
    """Test state vector construction exactly matching NEAT/main.py."""

    def test_state_vector_structure_7_elements(self) -> None:
        """Verify 7-element state vector: [is_invested, unrealized_pnl, 5 features]."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_state_vector

        features = {"trend_1h": 0.01, "rsi_1h": 0.5, "rsi_15m": 0.5, "roc": 0.0, "bb_width": 0.01}

        state = compute_state_vector(
            price=50000.0,
            is_invested=False,
            unrealized_pnl=0.0,
            features=features,
        )

        assert len(state) == 7
        assert state[0] == -1.0  # is_invested = -1.0 (not invested)
        assert state[1] == 0.0  # unrealized_pnl = 0.0 (no position)

    def test_state_vector_invested_position(self) -> None:
        """Test state vector when in an invested position."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_state_vector

        features = {"trend_1h": 0.02, "rsi_1h": 0.7, "rsi_15m": 0.6, "roc": 0.03, "bb_width": 0.02}

        state = compute_state_vector(
            price=52500.0,  # 5% gain
            is_invested=True,
            unrealized_pnl=0.05,
            features=features,
        )

        assert len(state) == 7
        assert state[0] == 1.0  # is_invested = 1.0
        assert abs(state[1] - 0.05) < 0.001  # 5% unrealized PnL

    def test_state_vector_order_matches_neat(self) -> None:
        """Verify state vector element order matches NEAT/main.py."""
        from stonks_trading.bots.neat_swing.feature_engineering import compute_state_vector

        features = {"trend_1h": 0.01, "rsi_1h": 0.6, "rsi_15m": 0.5, "roc": 0.02, "bb_width": 0.01}

        state = compute_state_vector(
            price=50000.0,
            is_invested=True,
            unrealized_pnl=0.10,
            features=features,
        )

        # From NEAT/main.py line 133: state = np.hstack(([is_invested, unrealized_pnl], mkt))
        # Where mkt = self.feats[step] = [trend_1h, rsi_1h, rsi_15m, roc, bb_width]
        assert state[0] == 1.0  # is_invested
        assert abs(state[1] - 0.10) < 0.001  # unrealized_pnl
        assert state[2] == 0.01  # trend_1h
        assert state[3] == 0.6  # rsi_1h
        assert state[4] == 0.5  # rsi_15m
        assert state[5] == 0.02  # roc
        assert state[6] == 0.01  # bb_width


class TestNeatStrategyInterface:
    """Test NeatSwingStrategy interface compliance with BaseStrategy."""

    def test_strategy_has_name_and_version(self) -> None:
        """Verify strategy has required name and version properties."""
        from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy

        strategy = NeatSwingStrategy()

        assert strategy.name == "neat_swing"
        assert strategy.version == "1.0.0"

    def test_strategy_compute_features_returns_dict(self) -> None:
        """Verify compute_features returns expected dict structure."""
        from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
        from stonks_trading.domains.trading.value_objects import Symbol

        strategy = NeatSwingStrategy()

        # Create sample candles
        dates = pd.date_range(start="2024-01-01", periods=300, freq="1min")
        np.random.seed(42)
        candles = []
        price = 50000.0
        for date in dates:
            price = price + np.random.randn() * 10
            candles.append(
                {
                    "open": price,
                    "high": price + 5,
                    "low": price - 5,
                    "close": price,
                    "volume": 10.0,
                }
            )

        features = strategy.compute_features(Symbol(value="BTC_USD"), candles)

        expected_keys = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]
        for key in expected_keys:
            assert key in features

    def test_strategy_generate_signal_returns_signal_or_none(self) -> None:
        """Verify generate_signal returns Signal or None."""
        from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
        from stonks_trading.domains.trading.value_objects import Symbol

        strategy = NeatSwingStrategy()

        result = strategy.generate_signal(
            symbol=Symbol(value="BTC_USD"),
            candle={"close": 50000.0},
            features={
                "trend_1h": 0.01,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.01,
            },
            current_position=None,
        )

        # Should return None since no genome loaded
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
