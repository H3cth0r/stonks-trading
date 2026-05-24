"""Tests for BaseBot and base classes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stonks_trading.bots import BaseBot, BaseBotState, BaseStrategy, BotContext
from stonks_trading.domains.trading.entities import Signal
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Symbol


# Test implementations
@dataclass
class TestState(BaseBotState):
    """Concrete state for testing."""

    trades: list[str] = None

    def __post_init__(self):
        if self.trades is None:
            self.trades = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "trades": self.trades,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestState":
        state = cls(trades=data.get("trades", []))
        return state


class TestStrategy(BaseStrategy):
    """Concrete strategy for testing."""

    @property
    def name(self) -> str:
        return "test_strategy"

    @property
    def version(self) -> str:
        return "1.0.0"

    def compute_features(self, symbol: Symbol, candles: list[dict[str, Any]]) -> dict[str, Any]:
        return {"sma": 100.0}

    def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        current_position: Any | None,
    ) -> Signal | None:
        return Signal(action=Side.BUY, confidence=0.8)


class ConcreteBot(BaseBot[TestState, TestStrategy]):
    """Concrete bot for testing BaseBot."""

    def __init__(self, **kwargs):
        defaults = {
            "context": BotContext(bot_type="test", instance_id="test-1"),
            "symbols": [Symbol(value="BTC_USD")],
            "mode": TradingMode.DRY_RUN,
            "strategy": TestStrategy(),
            "initial_state": TestState(),
        }
        defaults.update(kwargs)
        super().__init__(**defaults)

    @property
    def bot_type(self) -> str:
        return "test_bot"

    @property
    def required_data_frequency(self) -> str:
        return "1m"

    async def register(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def handle_candle(self, candle: dict[str, Any]) -> None:
        pass

    async def persist_state(self) -> None:
        pass

    async def load_state(self) -> TestState | None:
        return None


class TestBaseBot:
    """Test suite for BaseBot abstract class."""

    def test_initialization(self) -> None:
        """Should initialize with required attributes."""
        context = BotContext(bot_type="test", instance_id="test-1")
        symbols = [Symbol(value="BTC_USD"), Symbol(value="ETH_USD")]
        strategy = TestStrategy()
        state = TestState()

        bot = ConcreteBot(
            context=context,
            symbols=symbols,
            mode=TradingMode.LIVE,
            strategy=strategy,
            initial_state=state,
        )

        assert bot.context == context
        assert bot.symbols == symbols
        assert bot.mode == TradingMode.LIVE
        assert bot.strategy == strategy
        assert bot.state == state
        assert bot.adapter is None

    def test_bot_type_property(self) -> None:
        """Should implement bot_type property."""
        bot = ConcreteBot()

        assert bot.bot_type == "test_bot"

    def test_required_data_frequency_property(self) -> None:
        """Should implement required_data_frequency property."""
        bot = ConcreteBot()

        assert bot.required_data_frequency == "1m"


class TestBaseBotState:
    """Test suite for BaseBotState abstract class."""

    def test_timestamps_initialized(self) -> None:
        """Should initialize timestamps."""
        before = datetime.utcnow()
        state = TestState()
        after = datetime.utcnow()

        assert before <= state.created_at <= after
        assert before <= state.updated_at <= after

    def test_to_dict_abstract(self) -> None:
        """Should require to_dict implementation."""
        state = TestState(trades=["trade1", "trade2"])

        data = state.to_dict()

        assert "trades" in data
        assert data["trades"] == ["trade1", "trade2"]
        assert "created_at" in data
        assert "updated_at" in data

    def test_from_dict_abstract(self) -> None:
        """Should require from_dict implementation."""
        original = TestState(trades=["trade1"])
        data = original.to_dict()

        restored = TestState.from_dict(data)

        assert restored.trades == ["trade1"]


class TestBaseStrategy:
    """Test suite for BaseStrategy abstract class."""

    def test_name_property(self) -> None:
        """Should implement name property."""
        strategy = TestStrategy()

        assert strategy.name == "test_strategy"

    def test_version_property(self) -> None:
        """Should implement version property."""
        strategy = TestStrategy()

        assert strategy.version == "1.0.0"

    def test_compute_features(self) -> None:
        """Should compute features from candles."""
        strategy = TestStrategy()
        symbol = Symbol(value="BTC_USD")
        candles = [{"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}]

        features = strategy.compute_features(symbol, candles)

        assert "sma" in features
        assert features["sma"] == 100.0

    def test_generate_signal(self) -> None:
        """Should generate signal from features."""
        strategy = TestStrategy()
        symbol = Symbol(value="BTC_USD")
        candle = {"close": 105}
        features = {"sma": 100.0}

        signal = strategy.generate_signal(symbol, candle, features, None)

        assert signal is not None
        assert signal.action == Side.BUY
        assert signal.confidence == 0.8
