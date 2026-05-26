"""Tests for BotRegistry and BotFactory."""

from dataclasses import dataclass
from typing import Any

import pytest

from stonks_trading.bots import (
    BaseBot,
    BaseBotState,
    BaseStrategy,
    BotContext,
    BotFactory,
    BotRegistry,
)
from stonks_trading.domains.trading.entities import Signal
from stonks_trading.domains.trading.enums import TradingMode
from stonks_trading.domains.trading.value_objects import Symbol


# Test fixtures
@dataclass
class MockState(BaseBotState):
    """Mock state for testing."""

    counter: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "counter": self.counter,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockState":
        state = cls(counter=data.get("counter", 0))
        return state


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""

    @property
    def name(self) -> str:
        return "mock_strategy"

    @property
    def version(self) -> str:
        return "1.0.0"

    def compute_features(self, symbol: Symbol, candles: list[dict[str, Any]]) -> dict[str, Any]:
        return {"mock": True}

    def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        current_position: Any | None,
    ) -> Signal | None:
        return None


@BotRegistry.register("mock_bot")
class MockBot(BaseBot[MockState, MockStrategy]):
    """Mock bot for testing."""

    def __init__(
        self,
        context: BotContext,
        symbols: list[Symbol],
        mode: TradingMode,
        strategy: MockStrategy | None = None,
        initial_state: MockState | None = None,
    ):
        super().__init__(
            context=context,
            symbols=symbols,
            mode=mode,
            strategy=strategy or MockStrategy(),
            initial_state=initial_state or MockState(),
        )

    @property
    def bot_type(self) -> str:
        return "mock_bot"

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

    async def load_state(self) -> MockState | None:
        return None

    async def heartbeat(self) -> None:
        pass


class TestBotRegistry:
    """Test suite for BotRegistry."""

    def test_register_bot_class(self) -> None:
        """Should register bot class."""
        assert "mock_bot" in BotRegistry.list_bots()
        assert BotRegistry.get("mock_bot") == MockBot

    def test_get_unknown_bot_type(self) -> None:
        """Should raise error for unknown bot type."""
        with pytest.raises(ValueError) as exc:
            BotRegistry.get("unknown_bot")

        assert "Unknown bot type" in str(exc.value)
        assert "mock_bot" in str(exc.value)

    def test_list_bots_includes_mock(self) -> None:
        """Should include mock_bot in list."""
        bots = BotRegistry.list_bots()

        assert "mock_bot" in bots

    def test_is_registered_true(self) -> None:
        """Should return True for registered bot."""
        assert BotRegistry.is_registered("mock_bot") is True

    def test_is_registered_false(self) -> None:
        """Should return False for unregistered bot."""
        assert BotRegistry.is_registered("not_registered") is False

    def test_duplicate_registration_raises(self) -> None:
        """Should raise error for duplicate registration."""

        @BotRegistry.register("temp_bot")
        class TempBot(MockBot):
            pass

        with pytest.raises(ValueError) as exc:

            @BotRegistry.register("temp_bot")
            class AnotherTempBot(MockBot):
                pass

        assert "already registered" in str(exc.value)

        # Cleanup
        BotRegistry.unregister("temp_bot")


class TestBotFactory:
    """Test suite for BotFactory."""

    def test_create_basic(self) -> None:
        """Should create bot instance."""
        bot = BotFactory.create(
            bot_type="mock_bot",
            instance_id="test-1",
            symbols=["BTC_USD"],
            mode="dry_run",
        )

        assert isinstance(bot, MockBot)
        assert bot.context.bot_type == "mock_bot"
        assert bot.context.instance_id == "test-1"
        assert len(bot.symbols) == 1
        assert str(bot.symbols[0]) == "BTC_USD"
        assert bot.mode == TradingMode.DRY_RUN

    def test_create_multiple_symbols(self) -> None:
        """Should handle multiple symbols."""
        bot = BotFactory.create(
            bot_type="mock_bot",
            instance_id="test-1",
            symbols=["BTC_USD", "ETH_USD"],
            mode="dry_run",
        )

        assert len(bot.symbols) == 2
        symbol_values = [str(s) for s in bot.symbols]
        assert "BTC_USD" in symbol_values
        assert "ETH_USD" in symbol_values

    def test_create_live_mode(self) -> None:
        """Should create with live mode."""
        bot = BotFactory.create(
            bot_type="mock_bot",
            instance_id="test-1",
            symbols=["BTC_USD"],
            mode="live",
        )

        assert bot.mode == TradingMode.LIVE

    def test_create_unknown_bot_type(self) -> None:
        """Should raise error for unknown bot type."""
        with pytest.raises(ValueError) as exc:
            BotFactory.create(
                bot_type="unknown_bot",
                instance_id="test-1",
                symbols=["BTC_USD"],
                mode="dry_run",
            )

        assert "Unknown bot type" in str(exc.value)

    def test_create_invalid_mode(self) -> None:
        """Should raise error for invalid mode."""
        with pytest.raises(ValueError):
            BotFactory.create(
                bot_type="mock_bot",
                instance_id="test-1",
                symbols=["BTC_USD"],
                mode="invalid_mode",
            )

    def test_create_passes_kwargs(self) -> None:
        """Should pass extra kwargs to bot constructor."""
        strategy = MockStrategy()
        state = MockState(counter=42)

        bot = BotFactory.create(
            bot_type="mock_bot",
            instance_id="test-1",
            symbols=["BTC_USD"],
            mode="dry_run",
            strategy=strategy,
            initial_state=state,
        )

        assert bot.strategy is strategy
        assert bot.state is state
        assert bot.state.counter == 42

    def test_create_context(self) -> None:
        """Should create BotContext."""
        context = BotFactory.create_context(
            bot_type="neat_swing",
            instance_id="instance-1",
        )

        assert context.bot_type == "neat_swing"
        assert context.instance_id == "instance-1"
        assert isinstance(context, BotContext)
