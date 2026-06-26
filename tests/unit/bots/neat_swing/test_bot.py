"""Unit tests for NeatSwingBot core methods.

Covers the live-trading methods using the IngestionOrchestrator pattern:
- _build_state_vector
- _determine_action
- _execute_trade
- _calculate_quantity
- _load_active_genomes
- _main_loop
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
from stonks_trading.domains.trading.entities import Position
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


class FakeBalance:
    """Fake balance object for adapter mocking."""

    def __init__(self, asset: str, total: float) -> None:
        self.asset = asset
        self.total = total


@pytest.fixture
def mock_strategy() -> MagicMock:
    """Create a realistic mock strategy."""
    strategy = MagicMock(spec=NeatSwingStrategy)
    strategy.networks = {}
    strategy.neat_config = MagicMock()

    def fake_build_state_vector(
        price: float, position: Position | None, features: dict[str, Any]
    ) -> list[float]:
        is_invested = 1.0 if position and position.quantity > 0 else -1.0
        return [is_invested, 0.0, 0.0, 0.5, 0.5, 0.0, 0.0]

    strategy.build_state_vector = MagicMock(side_effect=fake_build_state_vector)
    strategy.activate_network = MagicMock(return_value=(0.7, 0.3))

    def fake_determine_action(buy_prob: float, sell_prob: float, is_invested: bool) -> Side | None:
        if buy_prob > 0.6 and buy_prob > sell_prob and not is_invested:
            return Side.BUY
        if sell_prob > 0.6 and sell_prob > buy_prob and is_invested:
            return Side.SELL
        return None

    strategy.determine_action = MagicMock(side_effect=fake_determine_action)
    return strategy


@pytest.fixture
def mock_feature_computer() -> MagicMock:
    """Create a mock LiveFeatureComputer returning a feature DataFrame."""
    computer = MagicMock()
    feature_df = pd.DataFrame(
        [
            {
                "Open": 49000.0,
                "High": 51000.0,
                "Low": 48500.0,
                "Close": 50000.0,
                "Volume": 1.5,
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }
        ]
    )
    computer.get_feature_df.return_value = feature_df
    computer.get_stats.return_value = {"has_features": True, "candles": 1}
    return computer


@pytest.fixture
def mock_orchestrator(mock_feature_computer: MagicMock) -> MagicMock:
    """Create a mock IngestionOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.get_feature_computer.return_value = mock_feature_computer
    return orchestrator


@pytest.fixture
def bot(mock_strategy: MagicMock, mock_orchestrator: MagicMock) -> NeatSwingBot:
    """Create a NeatSwingBot with mocked strategy and orchestrator."""
    context = BotContext(bot_type="neat_swing", instance_id="test-bot")
    symbol = Symbol(value="BTC_USD")
    state = NeatSwingState()
    bot_instance = NeatSwingBot(
        context=context,
        symbols=[symbol],
        mode=TradingMode.DRY_RUN,
        strategy=mock_strategy,
        initial_state=state,
    )
    bot_instance.set_orchestrator(mock_orchestrator)
    return bot_instance


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Create a mock exchange adapter."""
    adapter = MagicMock()
    adapter.get_balance = MagicMock(
        return_value=[
            FakeBalance("USDT", 10000.0),
            FakeBalance("BTC", 0.0),
        ]
    )
    adapter.place_order = AsyncMock(
        return_value=MagicMock(
            success=True,
            order_id="mock-1",
            fill_price=Money(amount=50000.0, currency="USDT"),
            filled_quantity=0.1,
            fee=Money(amount=5.0, currency="USDT"),
        )
    )
    return adapter


class TestBuildStateVector:
    """Tests for _build_state_vector."""

    @pytest.mark.asyncio
    async def test_state_vector_length(self, bot: NeatSwingBot) -> None:
        """State vector must have exactly 7 elements."""
        vector = await bot._build_state_vector(Symbol(value="BTC_USD"))
        assert vector is not None
        assert len(vector) == 7

    @pytest.mark.asyncio
    async def test_not_invested_first_element(self, bot: NeatSwingBot) -> None:
        """When no position, first element is -1.0."""
        vector = await bot._build_state_vector(Symbol(value="BTC_USD"))
        assert vector is not None
        assert vector[0] == -1.0

    @pytest.mark.asyncio
    async def test_invested_first_element(self, bot: NeatSwingBot) -> None:
        """When holding position, first element is 1.0."""
        position = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        bot.state.positions[Symbol(value="BTC_USD")] = position
        vector = await bot._build_state_vector(Symbol(value="BTC_USD"))
        assert vector is not None
        assert vector[0] == 1.0

    @pytest.mark.asyncio
    async def test_values_clipped(self, bot: NeatSwingBot) -> None:
        """All values in state vector are within [-5, 5]."""
        vector = await bot._build_state_vector(Symbol(value="BTC_USD"))
        assert vector is not None
        assert all(-5.0 <= v <= 5.0 for v in vector)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_features(self, bot: NeatSwingBot) -> None:
        """Returns None when orchestrator has no feature data."""
        bot._orchestrator.get_feature_computer.return_value.get_feature_df.return_value = None
        vector = await bot._build_state_vector(Symbol(value="BTC_USD"))
        assert vector is None


class TestDetermineAction:
    """Tests for _determine_action."""

    def test_buy_signal_when_not_invested(self, bot: NeatSwingBot) -> None:
        """Buy signal when buy_prob > threshold and not invested."""
        action = bot._determine_action(0.7, 0.3, Symbol(value="BTC_USD"))
        assert action == Side.BUY

    def test_no_buy_when_already_invested(self, bot: NeatSwingBot) -> None:
        """No buy when already holding position."""
        position = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        bot.state.positions[Symbol(value="BTC_USD")] = position
        action = bot._determine_action(0.7, 0.3, Symbol(value="BTC_USD"))
        assert action is None

    def test_sell_signal_when_invested(self, bot: NeatSwingBot) -> None:
        """Sell signal when sell_prob > threshold and invested."""
        position = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        bot.state.positions[Symbol(value="BTC_USD")] = position
        action = bot._determine_action(0.3, 0.7, Symbol(value="BTC_USD"))
        assert action == Side.SELL

    def test_no_sell_when_not_invested(self, bot: NeatSwingBot) -> None:
        """No sell when not holding position."""
        action = bot._determine_action(0.3, 0.7, Symbol(value="BTC_USD"))
        assert action is None

    def test_no_action_below_threshold(self, bot: NeatSwingBot) -> None:
        """No action when probabilities below threshold."""
        action = bot._determine_action(0.3, 0.2, Symbol(value="BTC_USD"))
        assert action is None

    def test_trade_interval_enforced(self, bot: NeatSwingBot) -> None:
        """No trade within 15 minutes of last trade."""
        now = datetime.utcnow()
        bot.state.last_trade_time = now
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = now.timestamp() + 1
            action = bot._determine_action(0.7, 0.3, Symbol(value="BTC_USD"))
        assert action is None

    def test_trade_interval_passed_allows_trade(self, bot: NeatSwingBot) -> None:
        """Trade allowed when last trade was more than 15 min ago."""
        now = datetime.utcnow()
        bot.state.last_trade_time = now
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = now.timestamp() + 16 * 60
            action = bot._determine_action(0.7, 0.3, Symbol(value="BTC_USD"))
        assert action == Side.BUY


class TestCalculateQuantity:
    """Tests for _calculate_quantity."""

    def test_buy_all_in(self, bot: NeatSwingBot, mock_adapter: MagicMock) -> None:
        """Buy calculates all-in quantity."""
        bot.adapter = mock_adapter
        candle = {"close": 50000.0}
        position = None
        quantity = bot._calculate_quantity(Symbol(value="BTC_USD"), candle, Side.BUY, position)
        assert quantity > 0
        # With 10k USDT at 50k price, minus 0.1% fee
        assert quantity < 0.2

    def test_buy_fallback_to_equity(self, bot: NeatSwingBot) -> None:
        """Buy falls back to current_equity when no adapter."""
        bot.adapter = None
        bot.state.current_equity = 5000.0
        candle = {"close": 50000.0}
        quantity = bot._calculate_quantity(Symbol(value="BTC_USD"), candle, Side.BUY, None)
        assert quantity > 0

    def test_sell_all_out(self, bot: NeatSwingBot) -> None:
        """Sell returns full position quantity."""
        candle = {"close": 50000.0}
        position = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        quantity = bot._calculate_quantity(Symbol(value="BTC_USD"), candle, Side.SELL, position)
        assert quantity == 0.1

    def test_sell_no_position(self, bot: NeatSwingBot) -> None:
        """Sell with no position returns 0."""
        candle = {"close": 50000.0}
        quantity = bot._calculate_quantity(Symbol(value="BTC_USD"), candle, Side.SELL, None)
        assert quantity == 0.0

    def test_buy_with_non_list_balance(self, bot: NeatSwingBot) -> None:
        """Buy handles adapter returning a single balance object."""
        adapter = MagicMock()
        adapter.get_balance = MagicMock(return_value=FakeBalance("USDT", 5000.0))
        bot.adapter = adapter
        candle = {"close": 50000.0}
        quantity = bot._calculate_quantity(Symbol(value="BTC_USD"), candle, Side.BUY, None)
        assert quantity > 0
        assert quantity < 0.11


class TestExecuteTrade:
    """Tests for _execute_trade."""

    @pytest.mark.asyncio
    async def test_no_adapter_returns_none(self, bot: NeatSwingBot) -> None:
        """_execute_trade returns None when no adapter."""
        bot.adapter = None
        result = await bot._execute_trade(Symbol(value="BTC_USD"), Side.BUY, 50000.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_buy_updates_positions(
        self, bot: NeatSwingBot, mock_adapter: MagicMock
    ) -> None:
        """Successful buy updates state.positions."""
        bot.adapter = mock_adapter
        fake_trade = MagicMock()
        fake_trade.quantity = 0.1
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.BUY, 50000.0)

            assert trade is not None
            assert Symbol(value="BTC_USD") in bot.state.positions

    @pytest.mark.asyncio
    async def test_successful_sell_removes_position(
        self, bot: NeatSwingBot, mock_adapter: MagicMock
    ) -> None:
        """Successful sell removes position when fully closed."""
        bot.adapter = mock_adapter
        bot.state.positions[Symbol(value="BTC_USD")] = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        fake_trade = MagicMock()
        fake_trade.quantity = 0.1
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.SELL, 50000.0)

            assert trade is not None
            assert Symbol(value="BTC_USD") not in bot.state.positions

    @pytest.mark.asyncio
    async def test_failed_trade_returns_none(self, bot: NeatSwingBot) -> None:
        """Failed trade returns None."""
        bot.adapter = MagicMock()
        bot.adapter.get_balance = MagicMock(
            return_value=[
                FakeBalance("USDT", 10000.0),
            ]
        )
        fake_result = MagicMock()
        fake_result.success = False
        fake_result.trade = None
        fake_result.error = "Risk check failed"

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.BUY, 50000.0)

            assert trade is None

    @pytest.mark.asyncio
    async def test_buy_adds_to_existing_position(
        self, bot: NeatSwingBot, mock_adapter: MagicMock
    ) -> None:
        """Successful buy adds to existing position."""
        bot.adapter = mock_adapter
        bot.state.positions[Symbol(value="BTC_USD")] = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.05,
            entry_price=Money(amount=48000.0, currency="USDT"),
        )
        fake_trade = MagicMock()
        fake_trade.quantity = 0.05
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.BUY, 50000.0)

            assert trade is not None
            position = bot.state.positions[Symbol(value="BTC_USD")]
            assert position.quantity == 0.1  # 0.05 + 0.05

    @pytest.mark.asyncio
    async def test_sell_partially_closes_position(
        self, bot: NeatSwingBot, mock_adapter: MagicMock
    ) -> None:
        """Successful sell partially closes position."""
        bot.adapter = mock_adapter
        bot.state.positions[Symbol(value="BTC_USD")] = Position(
            symbol=Symbol(value="BTC_USD"),
            quantity=0.1,
            entry_price=Money(amount=49000.0, currency="USDT"),
        )
        fake_trade = MagicMock()
        fake_trade.quantity = 0.05
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.SELL, 50000.0)

            assert trade is not None
            assert Symbol(value="BTC_USD") in bot.state.positions
            assert bot.state.positions[Symbol(value="BTC_USD")].quantity == 0.05

    @pytest.mark.asyncio
    async def test_sell_without_position(self, bot: NeatSwingBot, mock_adapter: MagicMock) -> None:
        """Sell trade without existing position returns trade but does not modify state."""
        bot.adapter = mock_adapter
        fake_trade = MagicMock()
        fake_trade.quantity = 0.0
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        with patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class:
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            trade = await bot._execute_trade(Symbol(value="BTC_USD"), Side.SELL, 50000.0)

            assert trade is not None
            assert Symbol(value="BTC_USD") not in bot.state.positions


class TestLoadActiveGenomes:
    """Tests for _load_active_genomes."""

    @pytest.mark.asyncio
    async def test_loads_genome_for_each_symbol(self, bot: NeatSwingBot) -> None:
        """Load active genomes for all symbols."""
        genome = MagicMock()
        genome.genome_data = b"test_genome"

        with patch(
            "stonks_trading.bots.neat_swing.bot.get_active_genome",
            new_callable=AsyncMock,
            return_value=genome,
        ):
            await bot._load_active_genomes()
            bot.strategy.load_genome.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_missing_genomes(self, bot: NeatSwingBot) -> None:
        """Skip symbols with no active genome."""
        with patch(
            "stonks_trading.bots.neat_swing.bot.get_active_genome",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await bot._load_active_genomes()
            bot.strategy.load_genome.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_load_exception(self, bot: NeatSwingBot) -> None:
        """Log warning when genome load fails."""
        genome = MagicMock()
        genome.genome_data = b"bad_data"
        bot.strategy.load_genome.side_effect = ValueError("bad genome")

        with patch(
            "stonks_trading.bots.neat_swing.bot.get_active_genome",
            new_callable=AsyncMock,
            return_value=genome,
        ):
            await bot._load_active_genomes()
            bot.strategy.load_genome.assert_called_once()


class TestMainLoop:
    """Tests for _main_loop."""

    @pytest.mark.asyncio
    async def test_processes_single_candle(self, bot: NeatSwingBot) -> None:
        """Main loop processes one polling iteration and exits."""
        bot.strategy.networks[Symbol(value="BTC_USD")] = MagicMock()
        bot._running = True
        call_count = 0
        real_sleep = asyncio.sleep

        async def short_sleep(*_):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                bot._running = False
            await real_sleep(0)

        with patch(
            "stonks_trading.bots.neat_swing.bot.asyncio.sleep",
            side_effect=short_sleep,
        ):
            await bot._main_loop()

    @pytest.mark.asyncio
    async def test_main_loop_executes_trade(
        self, bot: NeatSwingBot, mock_adapter: MagicMock
    ) -> None:
        """Main loop generates signal and executes trade."""
        bot.adapter = mock_adapter
        bot.strategy.networks[Symbol(value="BTC_USD")] = MagicMock()
        bot._running = True
        call_count = 0
        real_sleep = asyncio.sleep

        fake_trade = MagicMock()
        fake_trade.quantity = 0.1
        fake_trade.fill_price = Money(amount=50000.0, currency="USDT")
        fake_trade.realized_pnl = None

        fake_result = MagicMock()
        fake_result.success = True
        fake_result.trade = fake_trade
        fake_result.error = None

        async def short_sleep(*_):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                bot._running = False
            await real_sleep(0)

        with (
            patch("stonks_trading.bots.neat_swing.bot.ExecuteBotTradeUseCase") as mock_uc_class,
            patch(
                "stonks_trading.bots.neat_swing.bot.asyncio.sleep",
                side_effect=short_sleep,
            ),
            patch.object(bot, "persist_state", new_callable=AsyncMock),
        ):
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_result)
            mock_uc_class.return_value = mock_uc

            await bot._main_loop()

        assert Symbol(value="BTC_USD") in bot.state.positions

    @pytest.mark.asyncio
    async def test_main_loop_exception_caught(self, bot: NeatSwingBot) -> None:
        """Exception in main loop is caught and logged."""
        bot.strategy.networks[Symbol(value="BTC_USD")] = MagicMock()
        bot._orchestrator.get_feature_computer.side_effect = ValueError("boom")
        bot._running = True
        call_count = 0
        real_sleep = asyncio.sleep

        async def short_sleep(*_):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                bot._running = False
            await real_sleep(0)

        with (
            patch(
                "stonks_trading.bots.neat_swing.bot.asyncio.sleep",
                side_effect=short_sleep,
            ),
            patch("stonks_trading.bots.neat_swing.bot.logger") as mock_logger,
        ):
            await bot._main_loop()

        mock_logger.error.assert_called_once()
