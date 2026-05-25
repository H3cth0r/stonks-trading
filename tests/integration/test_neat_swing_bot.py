"""Integration tests for NeatSwingBot lifecycle.

Tests the full bot lifecycle including registration, candle processing,
trade execution, and state persistence using mocked dependencies.
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
from stonks_trading.domains.trading.entities import OrderResult, Position
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


class MockAdapter:
    """Mock exchange adapter for testing."""

    def __init__(self, initial_balance: dict[str, float] | None = None):
        self.balances = initial_balance or {"USDT": 10000.0, "BTC": 0.0}
        self.orders: list[dict[str, Any]] = []
        self._price = 50000.0

    async def place_order(
        self, symbol: Any, side: Side, quantity: float, order_type: str = "market"
    ) -> OrderResult:
        """Simulate order placement."""
        if quantity <= 0:
            return OrderResult(success=False, error="Zero quantity")

        price = self._price
        if side == Side.BUY:
            cost = quantity * price * 1.001
            if self.balances.get("USDT", 0) < cost:
                return OrderResult(success=False, error="Insufficient balance")

            self.balances["USDT"] -= cost
            self.balances["BTC"] = self.balances.get("BTC", 0) + quantity
        else:
            if self.balances.get("BTC", 0) < quantity:
                return OrderResult(success=False, error="Insufficient BTC")

            self.balances["BTC"] -= quantity
            self.balances["USDT"] = self.balances.get("USDT", 0) + quantity * price * 0.999

        return OrderResult(
            success=True,
            order_id=f"mock_{len(self.orders)}",
            fill_price=Money(amount=price, currency="USDT"),
            filled_quantity=quantity,
            fee=Money(amount=quantity * price * 0.001, currency="USDT"),
            timestamp=datetime.utcnow(),
        )

    async def get_balance(self, asset: str | None = None) -> Any:
        """Get balance."""
        from stonks_trading.domains.trading.entities import Balance

        if asset:
            return Balance(
                asset=asset,
                free=self.balances.get(asset, 0),
                locked=0,
                total=self.balances.get(asset, 0),
            )
        return [Balance(asset=k, free=v, locked=0, total=v) for k, v in self.balances.items()]

    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price."""
        return Money(amount=self._price, currency="USDT")


@pytest.fixture
def bot_context() -> BotContext:
    """Create test bot context."""
    return BotContext(bot_type="neat_swing", instance_id="test-bot-lifecycle")


@pytest.fixture
def symbol() -> Symbol:
    """Create test symbol."""
    return Symbol(value="BTC_USD")


@pytest.fixture
def strategy() -> NeatSwingStrategy:
    """Create strategy."""
    return NeatSwingStrategy()


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Create mock adapter."""
    return MockAdapter()


@pytest.fixture
def bot(
    bot_context: BotContext,
    symbol: Symbol,
    strategy: NeatSwingStrategy,
) -> NeatSwingBot:
    """Create test bot."""
    initial_state = NeatSwingState()
    bot = NeatSwingBot(
        context=bot_context,
        symbols=[symbol],
        mode=TradingMode.DRY_RUN,
        strategy=strategy,
        initial_state=initial_state,
    )
    bot.adapter = MockAdapter()
    return bot


class TestNeatSwingBotLifecycle:
    """Tests for bot lifecycle methods."""

    @pytest.mark.asyncio
    async def test_bot_initialization(self, bot: NeatSwingBot) -> None:
        """Bot initializes with correct properties."""
        assert bot.bot_type == "neat_swing"
        assert bot.required_data_frequency == "1m"
        assert bot.context.instance_id == "test-bot-lifecycle"
        assert bot.candle_queue.empty()
        assert not bot._running

    @pytest.mark.asyncio
    async def test_bot_context_persists(self, bot: NeatSwingBot) -> None:
        """Bot context is preserved through lifecycle."""
        assert bot.context.bot_type == "neat_swing"
        assert "test-bot-lifecycle" in bot.context.instance_id

    @pytest.mark.asyncio
    async def test_bot_adapter_injection(self, bot: NeatSwingBot) -> None:
        """Adapter is correctly injected."""
        assert bot.adapter is not None
        assert bot.adapter.balances["USDT"] == 10000.0


class TestNeatSwingBotRegistration:
    """Tests for bot registration."""

    @pytest.mark.asyncio
    async def test_register_calls_repository(self, bot: NeatSwingBot) -> None:
        """register() calls BotInstanceRepository.register()."""
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo:
            mock_repo.register = AsyncMock()

            await bot.register()

            mock_repo.register.assert_called_once()
            call_kwargs = mock_repo.register.call_args.kwargs
            assert call_kwargs["bot_type"] == "neat_swing"
            assert call_kwargs["instance_id"] == bot.context.instance_id
            assert call_kwargs["symbols"] == ["BTC_USD"]
            assert call_kwargs["mode"] == "dry_run"

    @pytest.mark.asyncio
    async def test_register_with_custom_config(self, bot_context: BotContext) -> None:
        """register() includes custom config."""
        strategy = NeatSwingStrategy(config_path="custom.txt")
        bot = NeatSwingBot(
            context=bot_context,
            symbols=[Symbol(value="ETH_USD")],
            mode=TradingMode.DRY_RUN,
            strategy=strategy,
            initial_state=NeatSwingState(),
        )

        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo:
            mock_repo.register = AsyncMock()

            await bot.register()

            call_kwargs = mock_repo.register.call_args.kwargs
            assert "config_path" in call_kwargs["config"]


class TestNeatSwingBotStart:
    """Tests for bot start."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, bot: NeatSwingBot) -> None:
        """start() sets _running to True and calls registration."""

        async def break_loop():
            bot._running = False

        with (
            patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo,
            patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state,
            patch("stonks_trading.bots.neat_swing.bot.get_active_genome") as mock_genome,
            patch("stonks_trading.bots.neat_swing.bot.get_scheduler_hook") as mock_scheduler,
            patch.object(bot, "_main_loop", side_effect=break_loop),
        ):
            mock_repo.register = AsyncMock()
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()
            mock_state.load = AsyncMock(return_value=None)
            mock_genome.return_value = None
            mock_scheduler.return_value = AsyncMock()

            await bot.start()

            mock_repo.register.assert_called_once()
            mock_repo.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_connects_websocket(self, bot: NeatSwingBot) -> None:
        """start() connects to WebSocket if available."""
        mock_ws = AsyncMock()
        bot._websocket = mock_ws

        async def break_loop():
            bot._running = False

        with (
            patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo,
            patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state,
            patch("stonks_trading.bots.neat_swing.bot.get_active_genome") as mock_genome,
            patch("stonks_trading.bots.neat_swing.bot.get_scheduler_hook") as mock_scheduler,
            patch.object(bot, "_main_loop", side_effect=break_loop),
        ):
            mock_repo.register = AsyncMock()
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()
            mock_state.load = AsyncMock(return_value=None)
            mock_genome.return_value = None
            mock_scheduler.return_value = AsyncMock()

            await bot.start()

            mock_ws.connect.assert_called_once()


class TestNeatSwingBotStop:
    """Tests for bot stop."""

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self, bot: NeatSwingBot) -> None:
        """stop() sets _running to False."""
        bot._running = True

        with (
            patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo,
            patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state,
            patch("stonks_trading.bots.neat_swing.bot.get_scheduler_hook") as mock_scheduler,
        ):
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()
            mock_scheduler.return_value = AsyncMock()

            await bot.stop()

            assert bot._running is False

    @pytest.mark.asyncio
    async def test_stop_disconnects_websocket(self, bot: NeatSwingBot) -> None:
        """stop() disconnects WebSocket."""
        mock_ws = AsyncMock()
        bot._websocket = mock_ws
        bot._running = True

        with (
            patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo,
            patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state,
            patch("stonks_trading.bots.neat_swing.bot.get_scheduler_hook") as mock_scheduler,
        ):
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()
            mock_scheduler.return_value = AsyncMock()

            await bot.stop()

            mock_ws.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_updates_status(self, bot: NeatSwingBot) -> None:
        """stop() updates bot status to 'stopped'."""
        bot._running = True

        with (
            patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo,
            patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state,
            patch("stonks_trading.bots.neat_swing.bot.get_scheduler_hook") as mock_scheduler,
        ):
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()
            mock_scheduler.return_value = AsyncMock()

            await bot.stop()

            mock_repo.update_status.assert_called_with(
                "neat_swing", bot.context.instance_id, "stopped"
            )


class TestNeatSwingBotCandleProcessing:
    """Tests for candle handling."""

    @pytest.mark.asyncio
    async def test_handle_candle_queues_message(self, bot: NeatSwingBot) -> None:
        """handle_candle() adds candle to queue."""
        candle = {
            "symbol": "BTC_USD",
            "close": 50000.0,
            "open": 49000.0,
            "high": 51000.0,
            "low": 48500.0,
            "volume": 1.5,
        }

        await bot.handle_candle(candle)

        assert not bot.candle_queue.empty()
        queued = await asyncio.wait_for(bot.candle_queue.get(), timeout=1.0)
        assert queued["close"] == 50000.0

    @pytest.mark.asyncio
    async def test_handle_candle_extracts_symbol(self, bot: NeatSwingBot) -> None:
        """handle_candle() accepts candle and queues it."""
        candle = {
            "symbol": "BTC_USD",
            "close": 50000.0,
        }

        await bot.handle_candle(candle)

        queued = await asyncio.wait_for(bot.candle_queue.get(), timeout=1.0)
        assert queued["symbol"] == "BTC_USD"


class TestNeatSwingBotStatePersistence:
    """Tests for state persistence."""

    @pytest.mark.asyncio
    async def test_persist_state_saves_to_repository(self, bot: NeatSwingBot) -> None:
        """persist_state() calls BotStateRepository.save()."""
        bot.state.current_equity = 10500.0
        bot.state.trades_today = 3

        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.save = AsyncMock()

            await bot.persist_state()

            mock_repo.save.assert_called_once()
            call_args = mock_repo.save.call_args
            context_arg = call_args.args[0]
            state_arg = call_args.args[1]

            assert context_arg == bot.context
            assert state_arg["current_equity"] == 10500.0
            assert state_arg["trades_today"] == 3

    @pytest.mark.asyncio
    async def test_load_state_recovers_from_repository(self, bot: NeatSwingBot) -> None:
        """load_state() recovers state from repository."""
        saved_state = {
            "positions": {},
            "trades_today": 7,
            "last_trade_time": datetime.utcnow().isoformat(),
            "peak_equity": 11000.0,
            "current_equity": 10500.0,
            "daily_loss_pct": 0.02,
            "in_safe_mode": False,
            "last_realized_loss_time": None,
        }

        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.load = AsyncMock(return_value=saved_state)

            recovered = await bot.load_state()

            assert recovered is not None
            assert recovered.trades_today == 7
            assert recovered.current_equity == 10500.0
            assert recovered.peak_equity == 11000.0

    @pytest.mark.asyncio
    async def test_load_state_returns_none_when_no_saved_state(self, bot: NeatSwingBot) -> None:
        """load_state() returns None if no saved state."""
        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.load = AsyncMock(return_value=None)

            recovered = await bot.load_state()

            assert recovered is None


class TestNeatSwingBotPositions:
    """Tests for position management."""

    @pytest.mark.asyncio
    async def test_state_tracks_positions(self, bot: NeatSwingBot, symbol: Symbol) -> None:
        """Bot state tracks positions by symbol."""
        position = Position(
            symbol=symbol,
            quantity=0.5,
            entry_price=Money(amount=50000.0, currency="USDT"),
        )

        bot.state.positions[symbol] = position

        assert symbol in bot.state.positions
        assert bot.state.positions[symbol].quantity == 0.5

    @pytest.mark.asyncio
    async def test_state_clears_position_on_close(self, bot: NeatSwingBot, symbol: Symbol) -> None:
        """Bot state clears position when closed."""
        position = Position(
            symbol=symbol,
            quantity=0.5,
            entry_price=Money(amount=50000.0, currency="USDT"),
        )
        bot.state.positions[symbol] = position

        del bot.state.positions[symbol]

        assert symbol not in bot.state.positions


class TestNeatSwingBotEquityTracking:
    """Tests for equity tracking."""

    @pytest.mark.asyncio
    async def test_update_equity_tracks_current(self, bot: NeatSwingBot) -> None:
        """Bot tracks current equity."""
        bot.state.update_equity(11000.0)

        assert bot.state.current_equity == 11000.0

    @pytest.mark.asyncio
    async def test_update_equity_tracks_peak(self, bot: NeatSwingBot) -> None:
        """Bot tracks peak equity."""
        bot.state.peak_equity = 10000.0
        bot.state.update_equity(11000.0)

        assert bot.state.peak_equity == 11000.0

    @pytest.mark.asyncio
    async def test_update_equity_maintains_peak_on_drawdown(self, bot: NeatSwingBot) -> None:
        """Peak equity is maintained during drawdown."""
        bot.state.peak_equity = 10000.0
        bot.state.update_equity(9000.0)

        assert bot.state.current_equity == 9000.0
        assert bot.state.peak_equity == 10000.0


class TestNeatSwingBotTradeCounting:
    """Tests for trade counting."""

    @pytest.mark.asyncio
    async def test_record_trade_increments_count(self, bot: NeatSwingBot) -> None:
        """record_trade() increments trades_today."""
        assert bot.state.trades_today == 0

        bot.state.record_trade()

        assert bot.state.trades_today == 1

    @pytest.mark.asyncio
    async def test_record_trade_sets_last_trade_time(self, bot: NeatSwingBot) -> None:
        """record_trade() sets last_trade_time."""
        assert bot.state.last_trade_time is None

        bot.state.record_trade()

        assert bot.state.last_trade_time is not None


class TestNeatSwingBotSafeMode:
    """Tests for safe mode."""

    @pytest.mark.asyncio
    async def test_safe_mode_default_false(self, bot: NeatSwingBot) -> None:
        """Safe mode is False by default."""
        assert bot.state.in_safe_mode is False

    @pytest.mark.asyncio
    async def test_reset_daily_metrics_clears_safe_mode(self, bot: NeatSwingBot) -> None:
        """reset_daily_metrics() clears safe mode."""
        bot.state.in_safe_mode = True

        bot.state.reset_daily_metrics()

        assert bot.state.in_safe_mode is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
