"""Unit tests for strategy base interfaces.

Tests IStrategy and ITrainableStrategy interfaces.
"""

import pytest
from abc import ABC

from stonks_trading.domains.strategies.base.interfaces import IStrategy, ITrainableStrategy
from stonks_trading.domains.strategies.base.entities import (
    EvaluationResult,
    Model,
    Signal,
    StrategyConfig,
    TrainingData,
    TrainingResult,
)
from stonks_trading.domains.strategies.base.registry import StrategyRegistry
from stonks_trading.domains.trading.value_objects import Symbol


class TestIStrategy:
    """Test IStrategy interface contract."""

    def test_is_abc(self):
        """IStrategy should be an abstract base class."""
        assert issubclass(IStrategy, ABC)

    def test_required_methods_exist(self):
        """IStrategy should have all required methods."""
        assert hasattr(IStrategy, 'generate_signal')
        assert hasattr(IStrategy, 'compute_features')
        assert hasattr(IStrategy, 'load_model')
        assert hasattr(IStrategy, 'save_model')
        assert hasattr(IStrategy, 'get_strategy_type')
        assert hasattr(IStrategy, 'get_required_data_frequency')

    def test_generate_signal_is_async(self):
        """generate_signal should be async abstractmethod."""
        import inspect
        assert inspect.iscoroutinefunction(IStrategy.generate_signal)

    def test_compute_features_is_async(self):
        """compute_features should be async abstractmethod."""
        import inspect
        assert inspect.iscoroutinefunction(IStrategy.compute_features)

    def test_load_model_is_async(self):
        """load_model should be async abstractmethod."""
        import inspect
        assert inspect.iscoroutinefunction(IStrategy.load_model)

    def test_save_model_is_async(self):
        """save_model should be async abstractmethod."""
        import inspect
        assert inspect.iscoroutinefunction(IStrategy.save_model)


class TestITrainableStrategy:
    """Test ITrainableStrategy interface."""

    def test_is_abc(self):
        """ITrainableStrategy should be an abstract base class."""
        assert issubclass(ITrainableStrategy, ABC)

    def test_extends_is_strategy(self):
        """ITrainableStrategy should extend IStrategy."""
        assert issubclass(ITrainableStrategy, IStrategy)

    def test_train_method_exists(self):
        """train should be async abstractmethod."""
        import inspect
        assert hasattr(ITrainableStrategy, 'train')
        assert inspect.iscoroutinefunction(ITrainableStrategy.train)

    def test_evaluate_method_exists(self):
        """evaluate should be async abstractmethod."""
        import inspect
        assert hasattr(ITrainableStrategy, 'evaluate')
        assert inspect.iscoroutinefunction(ITrainableStrategy.evaluate)

    def test_get_feature_schema_exists(self):
        """get_feature_schema should be abstractmethod."""
        assert hasattr(ITrainableStrategy, 'get_feature_schema')


class TestModel:
    """Test Model entity."""

    def test_creation(self):
        """Model can be created with model_data."""
        model = Model(model_data=b"test data")
        assert model.model_data == b"test data"
        assert model.id is None
        assert model.strategy_type == ""
        assert model.created_at is not None

    def test_is_active_returns_false_when_not_activated(self):
        """is_active should return False when not activated."""
        model = Model(model_data=b"test")
        assert model.is_active() is False

    def test_is_active_returns_true_when_activated(self):
        """is_active should return True when activated with no deactivation."""
        from datetime import datetime
        model = Model(
            model_data=b"test",
            activated_at=datetime.utcnow(),
            deactivated_at=None,
        )
        assert model.is_active() is True


class TestSignal:
    """Test Signal entity."""

    def test_creation(self):
        """Signal can be created with action and confidence."""
        signal = Signal(action="buy", confidence=0.8)
        assert signal.action == "buy"
        assert signal.confidence == 0.8
        assert signal.metadata == {}

    def test_with_metadata(self):
        """Signal can include metadata."""
        signal = Signal(
            action="sell",
            confidence=0.6,
            metadata={"reason": "overbought"},
        )
        assert signal.metadata["reason"] == "overbought"


class TestStrategyConfig:
    """Test StrategyConfig entity."""

    def test_creation_with_defaults(self):
        """StrategyConfig has sensible defaults."""
        config = StrategyConfig(
            strategy_type="neat_swing",
            symbol="BTC_USD",
        )
        assert config.strategy_type == "neat_swing"
        assert config.symbol == "BTC_USD"
        assert config.fee_rate == 0.001
        assert config.generations == 30
        assert config.pop_size == 150

    def test_creation_with_custom_values(self):
        """StrategyConfig can be customized."""
        config = StrategyConfig(
            strategy_type="fibras",
            symbol="ETH_USD",
            fee_rate=0.002,
            slippage_bps=10,
        )
        assert config.fee_rate == 0.002
        assert config.slippage_bps == 10


class TestTrainingData:
    """Test TrainingData entity."""

    def test_creation(self):
        """TrainingData can be created with candles."""
        candles = [
            {"open": 100, "high": 105, "low": 99, "close": 104, "volume": 1000},
        ]
        data = TrainingData(candles=candles, symbol="BTC_USD")
        assert data.candles == candles
        assert data.symbol == "BTC_USD"
        assert data.timeframe == "1m"
        assert data.labels is None


class TestStrategyRegistry:
    """Test StrategyRegistry class."""

    def test_register_single_strategy(self):
        """Can register a strategy class."""
        class MockStrategy(IStrategy):
            async def generate_signal(self, symbol, candle, features, position):
                return None
            async def compute_features(self, symbol, candles):
                return {}
            async def load_model(self, model_data):
                pass
            async def save_model(self):
                return b""
            def get_strategy_type(self):
                return "mock"
            def get_required_data_frequency(self):
                return "1m"

        registry = StrategyRegistry()
        registry.register("mock", MockStrategy)
        assert registry.is_registered("mock")

    def test_get_registered_strategy(self):
        """Can get registered strategy class."""
        class MockStrategy(IStrategy):
            async def generate_signal(self, symbol, candle, features, position):
                return None
            async def compute_features(self, symbol, candles):
                return {}
            async def load_model(self, model_data):
                pass
            async def save_model(self):
                return b""
            def get_strategy_type(self):
                return "mock"
            def get_required_data_frequency(self):
                return "1m"

        StrategyRegistry.register("mock2", MockStrategy)
        retrieved = StrategyRegistry.get("mock2")
        assert retrieved == MockStrategy

    def test_get_unknown_strategy_raises(self):
        """Getting unknown strategy raises KeyError."""
        registry = StrategyRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_list_strategies(self):
        """Can list registered strategy types."""
        strategies = StrategyRegistry.list_strategies()
        assert isinstance(strategies, list)

    def test_clear(self):
        """Can clear all registrations."""
        StrategyRegistry.clear()
        assert len(StrategyRegistry.list_strategies()) == 0
