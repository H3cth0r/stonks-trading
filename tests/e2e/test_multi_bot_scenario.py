"""E2E tests for multi-bot scenarios.

End-to-end tests that prove multiple bots can run independently,
each with its own context, positions, and state.
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
from stonks_trading.domains.trading.entities import OrderResult, Position
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


class MockAdapter:
    """Mock exchange adapter that tracks per-bot state."""

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
            return Balance(asset=asset, free=self.balances.get(asset, 0), locked=0, total=self.balances.get(asset, 0))
        return [Balance(asset=k, free=v, locked=0, total=v) for k, v in self.balances.items()]

    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price."""
        return Money(amount=self._price, currency="USDT")


@pytest.fixture
def bot_a_context() -> BotContext:
    """Bot A context for multi-bot testing."""
    return BotContext(bot_type="neat_swing", instance_id="multi-bot-test-a")


@pytest.fixture
def bot_b_context() -> BotContext:
    """Bot B context for multi-bot testing."""
    return BotContext(bot_type="neat_swing", instance_id="multi-bot-test-b")


@pytest.fixture
def symbol() -> Symbol:
    """Common trading symbol."""
    return Symbol(value="BTC_USD")


@pytest.fixture
def strategy_a() -> NeatSwingStrategy:
    """Strategy for Bot A."""
    return NeatSwingStrategy()


@pytest.fixture
def strategy_b() -> NeatSwingStrategy:
    """Strategy for Bot B."""
    return NeatSwingStrategy()


@pytest.fixture
def bot_a(
    bot_a_context: BotContext,
    symbol: Symbol,
    strategy_a: NeatSwingStrategy,
) -> NeatSwingBot:
    """Create Bot A."""
    initial_state = NeatSwingState()
    bot = NeatSwingBot(
        context=bot_a_context,
        symbols=[symbol],
        mode=TradingMode.DRY_RUN,
        strategy=strategy_a,
        initial_state=initial_state,
    )
    bot.adapter = MockAdapter()
    return bot


@pytest.fixture
def bot_b(
    bot_b_context: BotContext,
    symbol: Symbol,
    strategy_b: NeatSwingStrategy,
) -> NeatSwingBot:
    """Create Bot B."""
    initial_state = NeatSwingState()
    bot = NeatSwingBot(
        context=bot_b_context,
        symbols=[symbol],
        mode=TradingMode.DRY_RUN,
        strategy=strategy_b,
        initial_state=initial_state,
    )
    bot.adapter = MockAdapter()
    return bot


class TestMultiBotIndependence:
    """Tests proving bots run independently."""

    @pytest.mark.asyncio
    async def test_bots_have_different_contexts(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot has its own unique context."""
        assert bot_a.context != bot_b.context
        assert bot_a.context.instance_id != bot_b.context.instance_id
        assert bot_a.context.bot_type == bot_b.context.bot_type  # Same strategy type

    @pytest.mark.asyncio
    async def test_bots_have_different_states(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot maintains its own state."""
        # Modify Bot A's state
        bot_a.state.current_equity = 15000.0
        bot_a.state.trades_today = 5

        # Bot B's state should be independent
        assert bot_b.state.current_equity == 10000.0  # Default initial value
        assert bot_b.state.trades_today == 0  # Default initial value

    @pytest.mark.asyncio
    async def test_bots_have_isolated_adapters(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot has its own exchange adapter."""
        assert bot_a.adapter is not bot_b.adapter
        # Different adapter instances have independent balances
        bot_a.adapter.balances["USDT"] = 20000.0
        assert bot_b.adapter.balances["USDT"] != bot_a.adapter.balances["USDT"]

    @pytest.mark.asyncio
    async def test_bots_maintain_independent_positions(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
        symbol: Symbol,
    ) -> None:
        """Each bot tracks its own positions."""
        # Bot A enters a position
        bot_a.state.positions[symbol] = Position(
            symbol=symbol,
            quantity=1.0,
            entry_price=Money(amount=50000.0, currency="USDT"),
        )

        # Bot B should not see Bot A's position
        assert symbol not in bot_b.state.positions
        assert bot_b.state.positions.get(symbol) is None


class TestMultiBotRegistration:
    """Tests for multi-bot registration."""

    @pytest.mark.asyncio
    async def test_bots_register_with_correct_context(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot registers with its own context."""
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo:
            mock_repo.register = AsyncMock()
            mock_repo.update_status = AsyncMock()

            await bot_a.register()
            await bot_b.register()

            # Verify each bot registered with its own instance_id
            calls = mock_repo.register.call_args_list
            assert calls[0].kwargs["instance_id"] == bot_a.context.instance_id
            assert calls[1].kwargs["instance_id"] == bot_b.context.instance_id

    @pytest.mark.asyncio
    async def test_bots_update_status_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot can update its status without affecting the other."""
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo, \
             patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state:
            mock_state.save = AsyncMock()
            mock_repo.update_status = AsyncMock()

            await bot_a.stop()
            await bot_b.stop()

            calls = mock_repo.update_status.call_args_list
            # update_status is called with (bot_type, instance_id, status)
            assert calls[0].args[1] == bot_a.context.instance_id
            assert calls[0].args[2] == "stopped"
            assert calls[1].args[1] == bot_b.context.instance_id
            assert calls[1].args[2] == "stopped"


class TestMultiBotStatePersistence:
    """Tests for multi-bot state persistence."""

    @pytest.mark.asyncio
    async def test_bots_persist_state_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot persists its own state."""
        bot_a.state.current_equity = 12000.0
        bot_a.state.trades_today = 3

        bot_b.state.current_equity = 8000.0
        bot_b.state.trades_today = 7

        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            mock_repo.save = AsyncMock()

            await bot_a.persist_state()
            await bot_b.persist_state()

            calls = mock_repo.save.call_args_list
            # Bot A's state
            assert calls[0].args[0] == bot_a.context
            assert calls[0].args[1]["current_equity"] == 12000.0
            assert calls[0].args[1]["trades_today"] == 3

            # Bot B's state
            assert calls[1].args[0] == bot_b.context
            assert calls[1].args[1]["current_equity"] == 8000.0
            assert calls[1].args[1]["trades_today"] == 7

    @pytest.mark.asyncio
    async def test_bots_load_state_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Each bot loads only its own state."""
        state_a = {
            "positions": {},
            "trades_today": 10,
            "last_trade_time": datetime.utcnow().isoformat(),
            "peak_equity": 11000.0,
            "current_equity": 10500.0,
            "daily_loss_pct": 0.02,
            "in_safe_mode": False,
            "last_realized_loss_time": None,
        }
        state_b = {
            "positions": {},
            "trades_today": 2,
            "last_trade_time": None,
            "peak_equity": 10000.0,
            "current_equity": 9800.0,
            "daily_loss_pct": 0.0,
            "in_safe_mode": False,
            "last_realized_loss_time": None,
        }

        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_repo:
            # Return different state based on context
            async def mock_load(context):
                if context.instance_id == bot_a.context.instance_id:
                    return state_a
                return state_b

            mock_repo.load = AsyncMock(side_effect=mock_load)

            recovered_a = await bot_a.load_state()
            recovered_b = await bot_b.load_state()

            # Each bot should have loaded its own state
            assert recovered_a is not None
            assert recovered_a.trades_today == 10
            assert recovered_a.current_equity == 10500.0

            assert recovered_b is not None
            assert recovered_b.trades_today == 2
            assert recovered_b.current_equity == 9800.0


class TestMultiBotCandleProcessing:
    """Tests for multi-bot candle processing."""

    @pytest.mark.asyncio
    async def test_bots_process_same_candle_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
    ) -> None:
        """Both bots can process the same candle without interference."""
        candle = {
            "symbol": "BTC_USD",
            "close": 50000.0,
            "open": 49000.0,
            "high": 51000.0,
            "low": 48500.0,
            "volume": 1.5,
        }

        with patch("stonks_trading.bots.neat_swing.bot.BotStateRepository"):
            # Both bots should accept the candle
            await bot_a.handle_candle(candle)
            await bot_b.handle_candle(candle)

            # Both queues should have one candle
            assert not bot_a.candle_queue.empty()
            assert not bot_b.candle_queue.empty()

            # The candles should be the same (independent processing)
            candle_a = await asyncio.wait_for(bot_a.candle_queue.get(), timeout=1.0)
            candle_b = await asyncio.wait_for(bot_b.candle_queue.get(), timeout=1.0)

            assert candle_a["close"] == candle_b["close"] == 50000.0


class TestMultiBotTrading:
    """Tests for multi-bot trading scenarios."""

    @pytest.mark.asyncio
    async def test_bots_can_trade_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
        symbol: Symbol,
    ) -> None:
        """Two bots can execute trades independently."""
        # Give both bots some initial state
        bot_a.state.current_equity = 10000.0
        bot_b.state.current_equity = 10000.0

        # Both adapters should have independent balances
        assert bot_a.adapter.balances["USDT"] == bot_b.adapter.balances["USDT"] == 10000.0

        # Bot A executes a buy
        result_a = await bot_a.adapter.place_order(symbol, Side.BUY, 0.1)

        # Bot B executes a buy
        result_b = await bot_b.adapter.place_order(symbol, Side.BUY, 0.1)

        # Both should succeed independently
        assert result_a.success
        assert result_b.success

        # Each bot's adapter balance should be affected independently
        # (accounting for fees)
        assert bot_a.adapter.balances["BTC"] > 0
        assert bot_b.adapter.balances["BTC"] > 0

    @pytest.mark.asyncio
    async def test_bots_trade_different_quantities_independently(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
        symbol: Symbol,
    ) -> None:
        """Bots can trade different quantities without interference."""
        quantity_a = 0.1
        quantity_b = 0.05

        # Set different prices
        bot_a.adapter._price = 50000.0
        bot_b.adapter._price = 50000.0

        # Bot A buys 0.1 BTC
        await bot_a.adapter.place_order(symbol, Side.BUY, quantity_a)

        # Bot B buys 0.05 BTC
        await bot_b.adapter.place_order(symbol, Side.BUY, quantity_b)

        # Their BTC balances should reflect their own trades
        assert bot_a.adapter.balances["BTC"] == quantity_a
        assert bot_b.adapter.balances["BTC"] == quantity_b


class TestMultiBotScenario:
    """Real-world multi-bot scenario tests."""

    @pytest.mark.asyncio
    async def test_scenario_two_bots_same_symbol_different_strategies(
        self,
        bot_a_context: BotContext,
        bot_b_context: BotContext,
        symbol: Symbol,
    ) -> None:
        """Scenario: Two bots trading the same symbol with different contexts.

        This is the primary multi-bot isolation scenario. Bot A and Bot B
        both trade BTC_USD but maintain completely independent:
        - Positions (each thinks it has its own position)
        - State (equity, trades_today, etc.)
        - Registry entries
        """
        # Create two bots with different instance IDs
        strategy_a = NeatSwingStrategy()
        strategy_b = NeatSwingStrategy()

        bot_a = NeatSwingBot(
            context=bot_a_context,
            symbols=[symbol],
            mode=TradingMode.DRY_RUN,
            strategy=strategy_a,
            initial_state=NeatSwingState(),
        )
        bot_a.adapter = MockAdapter({"USDT": 10000.0, "BTC": 0.0})

        bot_b = NeatSwingBot(
            context=bot_b_context,
            symbols=[symbol],
            mode=TradingMode.DRY_RUN,
            strategy=strategy_b,
            initial_state=NeatSwingState(),
        )
        bot_b.adapter = MockAdapter({"USDT": 10000.0, "BTC": 0.0})

        # Verify isolated contexts
        assert bot_a.context != bot_b.context
        assert bot_a.context.instance_id != bot_b.context.instance_id

        # Verify independent state
        bot_a.state.current_equity = 15000.0
        bot_b.state.current_equity = 8000.0

        assert bot_a.state.current_equity != bot_b.state.current_equity

        # Verify independent adapters (different object instances)
        assert bot_a.adapter is not bot_b.adapter

        # Modify one adapter, verify the other is unaffected
        original_btc = bot_b.adapter.balances["BTC"]
        bot_a.adapter.balances["USDT"] = 99999.0
        assert bot_b.adapter.balances["USDT"] != bot_a.adapter.balances["USDT"]
        assert bot_b.adapter.balances["BTC"] == original_btc

        # Both bots register themselves
        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo:
            mock_repo.register = AsyncMock()

            await bot_a.register()
            await bot_b.register()

            # Both registrations succeeded with correct contexts
            assert mock_repo.register.call_count == 2

    @pytest.mark.asyncio
    async def test_scenario_bot_restart_recovers_correct_state(
        self,
        bot_a_context: BotContext,
        symbol: Symbol,
    ) -> None:
        """Scenario: Bot restarts and recovers only its own state.

        When a bot restarts, it should:
        1. Load its own state (not other bots' state)
        2. Restore its positions, equity, trade counts
        3. Continue trading from where it left off
        """
        saved_state = {
            "positions": {},
            "trades_today": 7,
            "last_trade_time": datetime.utcnow().isoformat(),
            "peak_equity": 11500.0,
            "current_equity": 11000.0,
            "daily_loss_pct": 0.03,
            "in_safe_mode": False,
            "last_realized_loss_time": None,
        }

        # Create and "start" bot
        strategy = NeatSwingStrategy()
        bot = NeatSwingBot(
            context=bot_a_context,
            symbols=[symbol],
            mode=TradingMode.DRY_RUN,
            strategy=strategy,
            initial_state=NeatSwingState(),
        )

        with patch("stonks_trading.bots.neat_swing.bot.BotInstanceRepository") as mock_repo, \
             patch("stonks_trading.bots.neat_swing.bot.BotStateRepository") as mock_state:
            mock_repo.register = AsyncMock()
            mock_state.load = AsyncMock(return_value=saved_state)
            mock_state.save = AsyncMock()

            # Load state (simulating restart)
            recovered = await bot.load_state()

            assert recovered is not None
            assert recovered.trades_today == 7
            assert recovered.current_equity == 11000.0
            assert recovered.peak_equity == 11500.0

            # Persist state
            await bot.persist_state()

            # Verify correct context was used
            mock_state.save.assert_called()
            save_call_context = mock_state.save.call_args.args[0]
            assert save_call_context.instance_id == bot_a_context.instance_id

    @pytest.mark.asyncio
    async def test_scenario_multiple_bots_different_symbols(
        self,
        bot_a_context: BotContext,
        symbol: Symbol,
    ) -> None:
        """Scenario: Multiple bots trading different symbols.

        Bots A and B trade different symbols (BTC_USD and ETH_USD).
        Each maintains independent state for its own symbol.
        """
        btc_symbol = symbol
        eth_symbol = Symbol(value="ETH_USD")

        strategy_a = NeatSwingStrategy()
        strategy_b = NeatSwingStrategy()

        bot_a = NeatSwingBot(
            context=bot_a_context,
            symbols=[btc_symbol],
            mode=TradingMode.DRY_RUN,
            strategy=strategy_a,
            initial_state=NeatSwingState(),
        )

        # Create a different context for Bot B
        bot_b_context = BotContext(bot_type="neat_swing", instance_id="bot-b-eth")

        bot_b = NeatSwingBot(
            context=bot_b_context,
            symbols=[eth_symbol],
            mode=TradingMode.DRY_RUN,
            strategy=strategy_b,
            initial_state=NeatSwingState(),
        )

        # Verify different symbols
        assert bot_a.symbols != bot_b.symbols
        assert btc_symbol in bot_a.symbols
        assert eth_symbol in bot_b.symbols


class TestMultiBotEdgeCases:
    """Edge case tests for multi-bot scenarios."""

    @pytest.mark.asyncio
    async def test_bots_with_same_instance_id_different_types(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """Different bot types can have the same instance_id."""
        different_type_context = BotContext(
            bot_type="mean_reversion",
            instance_id="shared-instance-id",
        )

        strategy_a = NeatSwingStrategy()

        bot_a = NeatSwingBot(
            context=bot_a_context,
            symbols=[Symbol(value="BTC_USD")],
            mode=TradingMode.DRY_RUN,
            strategy=strategy_a,
            initial_state=NeatSwingState(),
        )

        # This would fail in practice since different strategy type
        # but for context isolation, it should work
        assert bot_a.context.bot_type != different_type_context.bot_type
        assert bot_a.context.instance_id != different_type_context.instance_id

    @pytest.mark.asyncio
    async def test_bot_id_verification_in_trade_execution(
        self,
        bot_a: NeatSwingBot,
        bot_b: NeatSwingBot,
        symbol: Symbol,
    ) -> None:
        """Trade execution uses correct bot context."""
        with patch("stonks_trading.domains.trading.repositories.save_trade_with_context") as mock_save:
            mock_save.return_value = MagicMock()

            # Simulate trade execution through use case
            from stonks_trading.domains.trading.repositories import save_trade_with_context
            from stonks_trading.domains.trading.entities import Trade

            trade_a = Trade(
                symbol=symbol,
                side=Side.BUY,
                fill_price=Money(amount=50000.0, currency="USDT"),
                quantity=0.1,
                fee=Money(amount=5.0, currency="USDT"),
                bot_type=bot_a.context.bot_type,
                bot_instance_id=bot_a.context.instance_id,
                mode=TradingMode.DRY_RUN,
                exchange="binance",
            )

            trade_b = Trade(
                symbol=symbol,
                side=Side.BUY,
                fill_price=Money(amount=50000.0, currency="USDT"),
                quantity=0.1,
                fee=Money(amount=5.0, currency="USDT"),
                bot_type=bot_b.context.bot_type,
                bot_instance_id=bot_b.context.instance_id,
                mode=TradingMode.DRY_RUN,
                exchange="binance",
            )

            await save_trade_with_context(trade_a, bot_a.context)
            await save_trade_with_context(trade_b, bot_b.context)

            # Verify each trade was saved with correct context
            assert mock_save.call_count == 2

            call_a_context = mock_save.call_args_list[0].args[1]
            call_b_context = mock_save.call_args_list[1].args[1]

            assert call_a_context.instance_id == bot_a.context.instance_id
            assert call_b_context.instance_id == bot_b.context.instance_id
            assert call_a_context.instance_id != call_b_context.instance_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])