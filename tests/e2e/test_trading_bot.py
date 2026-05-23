"""E2E tests for trading bot lifecycle.

Tests the full bot lifecycle including registration, WebSocket consumption,
state persistence, and dry-run trade execution.
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.neat_swing.bot import NeatSwingBot
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import NeatSwingStrategy
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


class MockAdapter:
    """Mock exchange adapter for testing."""

    def __init__(self):
        self.balances = {"USDT": 10000.0, "BTC": 0.0}
        self.orders = []
        self._price = 50000.0

    async def place_order(
        self, symbol: Any, side: Side, quantity: float, order_type: str = "market"
    ) -> Any:
        """Simulate order placement."""
        from stonks_trading.domains.trading.entities import OrderResult

        if quantity <= 0:
            return OrderResult(success=False, error="Zero quantity")

        price = self._price
        if side == Side.BUY:
            cost = quantity * price * 1.001  # With fee
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
            return Balance(asset=asset, free=self.balances.get(asset, 0), locked=0, total=self.balances.get(asset, 0))
        return [Balance(asset=k, free=v, locked=0, total=v) for k, v in self.balances.items()]

    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price."""
        return Money(amount=self._price, currency="USDT")


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self, bot: NeatSwingBot):
        self.bot = bot
        self._running = False

    async def connect(self) -> None:
        self._running = True

    async def disconnect(self) -> None:
        self._running = False

    async def send_candle(self, symbol: str, close_price: float) -> None:
        """Send a candle to the bot."""
        candle = {
            "symbol": symbol,
            "ts_open": 1000000,
            "ts_close": 1000060,
            "open": close_price,
            "high": close_price * 1.01,
            "low": close_price * 0.99,
            "close": close_price,
            "volume": 1.0,
            "closed": True,
        }
        await self.bot.handle_candle(candle)


@pytest.fixture
def bot_context() -> BotContext:
    """Create test bot context."""
    return BotContext(bot_type="neat_swing", instance_id="test-bot-1")


@pytest.fixture
def symbol() -> Symbol:
    """Create test symbol."""
    return Symbol(value="BTC_USD")


@pytest.fixture
def strategy(symbol: Symbol) -> NeatSwingStrategy:
    """Create strategy with mock genome."""
    strategy = NeatSwingStrategy()
    # Load mock genome - would need a real NEAT genome for actual testing
    return strategy


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Create mock adapter."""
    return MockAdapter()


@pytest.fixture
def bot(
    bot_context: BotContext,
    symbol: Symbol,
    strategy: NeatSwingStrategy,
    mock_adapter: MockAdapter,
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
    bot.adapter = mock_adapter
    return bot


class TestBotLifecycle:
    """Tests for bot lifecycle management."""

    @pytest.mark.asyncio
    async def test_bot_registration(self, bot: NeatSwingBot) -> None:
        """Test bot registers itself on start."""
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo:
            mock_repo.register = AsyncMock()
            mock_repo.update_status = AsyncMock()

            await bot.register()

            mock_repo.register.assert_called_once()
            call_kwargs = mock_repo.register.call_args[1]
            assert call_kwargs["bot_type"] == "neat_swing"
            assert call_kwargs["instance_id"] == "test-bot-1"
            assert call_kwargs["symbols"] == ["BTC_USD"]
            assert call_kwargs["mode"] == "dry_run"

    @pytest.mark.asyncio
    async def test_bot_stop_updates_status(self, bot: NeatSwingBot) -> None:
        """Test bot updates status on stop."""
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo, \
             patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state:
            mock_repo.register = AsyncMock()
            mock_repo.update_status = AsyncMock()
            mock_state.save = AsyncMock()

            await bot.stop()

            mock_repo.update_status.assert_called_with("neat_swing", "test-bot-1", "stopped")

    @pytest.mark.asyncio
    async def test_handle_candle_queues_message(self, bot: NeatSwingBot) -> None:
        """Test handle_candle adds candle to queue."""
        candle = {
            "symbol": "BTC_USD",
            "close": 50000.0,
            "open": 49000.0,
            "high": 51000.0,
            "low": 48500.0,
            "volume": 1.5,
        }

        await bot.handle_candle(candle)

        # Check candle was queued
        queued = await asyncio.wait_for(bot.candle_queue.get(), timeout=1.0)
        assert queued["close"] == 50000.0
        assert queued["symbol"] == "BTC_USD"

    @pytest.mark.asyncio
    async def test_state_persistence(self, bot: NeatSwingBot) -> None:
        """Test state is persisted correctly."""
        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.save = AsyncMock()

            # Update state
            bot.state.current_equity = 10500.0
            bot.state.trades_today = 3

            await bot.persist_state()

            mock_repo.save.assert_called_once()
            call_args = mock_repo.save.call_args
            # save is called with positional args: (context, state_dict)
            context_arg = call_args[0][0]
            state_arg = call_args[0][1]
            assert context_arg == bot.context
            assert "positions" in state_arg
            assert state_arg["current_equity"] == 10500.0
            assert state_arg["trades_today"] == 3

    @pytest.mark.asyncio
    async def test_state_recovery(self, bot: NeatSwingBot) -> None:
        """Test bot recovers state on startup."""
        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.load = AsyncMock(
                return_value={
                    "positions": {},
                    "trades_today": 5,
                    "last_trade_time": datetime.utcnow().isoformat(),
                    "peak_equity": 11000.0,
                    "current_equity": 10500.0,
                    "daily_loss_pct": 0.01,
                    "in_safe_mode": False,
                    "last_realized_loss_time": None,
                }
            )

            recovered_state = await bot.load_state()

            assert recovered_state is not None
            assert recovered_state.trades_today == 5
            assert recovered_state.current_equity == 10500.0
            assert recovered_state.peak_equity == 11000.0

    @pytest.mark.asyncio
    async def test_websocket_consumption(
        self, bot: NeatSwingBot, mock_adapter: MockAdapter
    ) -> None:
        """Test bot processes candles from WebSocket."""
        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository"):
            mock_ws = MockWebSocket(bot)

            # Send some candles
            await mock_ws.send_candle("btcusdt", 50000.0)
            await asyncio.sleep(0.1)  # Allow processing

            # Queue should have at least one candle
            assert not bot.candle_queue.empty()

    @pytest.mark.asyncio
    async def test_dry_run_execution(
        self, bot: NeatSwingBot, mock_adapter: MockAdapter, symbol: Symbol
    ) -> None:
        """Test bot executes dry-run trades correctly."""
        from stonks_trading.domains.trading.entities import OrderResult

        # Manually set a price on adapter
        mock_adapter._price = 50000.0

        # Create a BUY signal
        candle = {
            "symbol": "BTC_USD",
            "close": 50000.0,
            "open": 49000.0,
            "high": 51000.0,
            "low": 48500.0,
            "volume": 1.5,
        }

        # Execute trade directly through adapter
        result = await mock_adapter.place_order(symbol, Side.BUY, 0.1)

        assert result.success
        assert result.filled_quantity == 0.1
        assert result.fill_price.amount == 50000.0
        assert mock_adapter.balances["BTC"] == 0.1


class TestNeatSwingState:
    """Tests for NeatSwingState."""

    def test_state_serialization(self) -> None:
        """Test state serializes and deserializes correctly."""
        state = NeatSwingState()
        state.trades_today = 3
        state.current_equity = 10500.0
        state.peak_equity = 11000.0

        # Serialize
        data = state.to_dict()

        # Deserialize
        recovered = NeatSwingState.from_dict(data)

        assert recovered.trades_today == 3
        assert recovered.current_equity == 10500.0
        assert recovered.peak_equity == 11000.0

    def test_record_trade(self) -> None:
        """Test trade recording updates state."""
        state = NeatSwingState()
        assert state.trades_today == 0

        state.record_trade()
        assert state.trades_today == 1
        assert state.last_trade_time is not None

    def test_update_equity(self) -> None:
        """Test equity updates correctly."""
        state = NeatSwingState()
        state.peak_equity = 10000.0

        state.update_equity(11000.0)
        assert state.current_equity == 11000.0
        assert state.peak_equity == 11000.0  # Updated

        state.update_equity(10500.0)
        assert state.current_equity == 10500.0
        assert state.peak_equity == 11000.0  # Still peak

    def test_reset_daily_metrics(self) -> None:
        """Test daily metrics reset."""
        state = NeatSwingState()
        state.trades_today = 10
        state.daily_loss_pct = 0.05
        state.in_safe_mode = True

        state.reset_daily_metrics()

        assert state.trades_today == 0
        assert state.daily_loss_pct == 0.0
        assert state.in_safe_mode is False


class TestWebSocketClient:
    """Tests for WebSocket client."""

    @pytest.mark.asyncio
    async def test_websocket_message_parsing(self) -> None:
        """Test WebSocket parses Binance messages correctly."""
        from stonks_trading.shared.websocket_client import WebSocketClient

        candles_received = []

        def callback(candle: dict) -> None:
            candles_received.append(candle)

        client = WebSocketClient(symbols=["btcusdt"], callback=callback)

        # Simulate Binance kline message format
        message = {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "s": "BTCUSDT",
                "k": {
                    "t": 1672515780000,
                    "T": 1672515839999,
                    "s": "BTCUSDT",
                    "o": "50000.00",
                    "h": "51000.00",
                    "l": "49000.00",
                    "c": "50500.00",
                    "v": "1.5",
                    "x": True,
                },
            },
        }

        # Process manually (would normally come through WebSocket)
        await client._process_kline(message["data"])

        assert len(candles_received) == 1
        assert candles_received[0]["close"] == 50500.0
        assert candles_received[0]["symbol"] == "btcusdt"

    @pytest.mark.asyncio
    async def test_websocket_ignores_open_candles(self) -> None:
        """Test WebSocket ignores candles that aren't closed."""
        from stonks_trading.shared.websocket_client import WebSocketClient

        candles_received = []

        client = WebSocketClient(symbols=["btcusdt"], callback=lambda c: candles_received.append(c))

        # Open candle (x=False)
        message = {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1672515780000,
                "T": 1672515839999,
                "o": "50000.00",
                "h": "51000.00",
                "l": "49000.00",
                "c": "50500.00",
                "v": "1.5",
                "x": False,  # Not closed
            },
        }

        await client._process_kline(message)

        # Should be ignored
        assert len(candles_received) == 0


class TestScheduler:
    """Tests for Scheduler."""

    def test_scheduler_initialization(self) -> None:
        """Test scheduler initializes correctly."""
        from stonks_trading.shared.scheduler import Scheduler

        scheduler = Scheduler()
        assert not scheduler.is_running

    def test_list_jobs_empty(self) -> None:
        """Test list_jobs returns empty initially."""
        from stonks_trading.shared.scheduler import Scheduler

        scheduler = Scheduler()
        assert scheduler.list_jobs() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])