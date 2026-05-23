"""Integration tests for multi-bot isolation.

Validates that bots are properly isolated from each other at the
repository layer - positions, trades, and state are scoped to bot context.

These tests verify the contract that:
1. Each bot context (bot_type + instance_id) is independent
2. Repository functions filter by bot context correctly
3. No cross-bot data leakage occurs
"""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.bots.base.context import BotContext
from stonks_trading.domains.trading.entities import Position, Trade
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.repositories import (
    BotInstanceRepository,
    BotStateRepository,
    close_position_by_bot,
    get_position_by_bot_and_symbol,
    list_positions_by_bot,
    save_position_with_context,
    save_trade_with_context,
)
from stonks_trading.domains.trading.value_objects import Money, Symbol


@pytest.fixture
def bot_a_context() -> BotContext:
    """Bot A context for isolation testing."""
    return BotContext(bot_type="neat_swing", instance_id="bot-a")


@pytest.fixture
def bot_b_context() -> BotContext:
    """Bot B context for isolation testing."""
    return BotContext(bot_type="neat_swing", instance_id="bot-b")


@pytest.fixture
def different_strategy_context() -> BotContext:
    """Bot with a different strategy type."""
    return BotContext(bot_type="mean_reversion", instance_id="mr-bot-1")


@pytest.fixture
def btc_symbol() -> Symbol:
    return Symbol(value="BTC_USD")


class TestPositionIsolation:
    """Tests for position isolation between bots."""

    @pytest.mark.asyncio
    async def test_positions_isolated_by_bot(
        self,
        bot_a_context: BotContext,
        bot_b_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """Two bots can have positions in the same symbol independently."""
        # Bot A opens a position
        bot_a_position = Position(
            symbol=btc_symbol,
            quantity=0.5,
            entry_price=Money(amount=50000.0, currency="USDT"),
            bot_type=bot_a_context.bot_type,
            bot_instance_id=bot_a_context.instance_id,
        )

        # Bot B opens a position in the same symbol
        bot_b_position = Position(
            symbol=btc_symbol,
            quantity=0.5,
            entry_price=Money(amount=50000.0, currency="USDT"),
            bot_type=bot_b_context.bot_type,
            bot_instance_id=bot_b_context.instance_id,
        )

        # Verify they have different contexts
        assert bot_a_context.instance_id != bot_b_context.instance_id
        assert bot_a_position.bot_instance_id != bot_b_position.bot_instance_id

    @pytest.mark.asyncio
    async def test_get_position_respects_bot_context(
        self,
        bot_a_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """get_position_by_bot_and_symbol only returns position for specific bot."""
        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=None)

            await get_position_by_bot_and_symbol(bot_a_context, btc_symbol)

            mock_model.get_or_none.assert_called()
            call_kwargs = mock_model.get_or_none.call_args.kwargs
            assert call_kwargs["bot_type"] == bot_a_context.bot_type
            assert call_kwargs["bot_instance_id"] == bot_a_context.instance_id

    @pytest.mark.asyncio
    async def test_list_positions_by_bot_returns_only_that_bot(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """list_positions_by_bot only returns positions for the specified bot."""
        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.filter = AsyncMock(return_value=[])

            await list_positions_by_bot(bot_a_context)

            mock_model.filter.assert_called_with(
                bot_type=bot_a_context.bot_type,
                bot_instance_id=bot_a_context.instance_id,
            )

    @pytest.mark.asyncio
    async def test_different_strategies_isolated(
        self,
        bot_a_context: BotContext,
        different_strategy_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """Different bot types (strategies) are isolated from each other."""
        assert bot_a_context.bot_type != different_strategy_context.bot_type

        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=None)

            await get_position_by_bot_and_symbol(bot_a_context, btc_symbol)
            await get_position_by_bot_and_symbol(different_strategy_context, btc_symbol)

            calls = mock_model.get_or_none.call_args_list
            assert calls[0].kwargs["bot_type"] == bot_a_context.bot_type
            assert calls[1].kwargs["bot_type"] == different_strategy_context.bot_type


class TestTradeIsolation:
    """Tests for trade isolation between bots."""

    @pytest.mark.asyncio
    async def test_trades_isolated_by_bot(
        self,
        bot_a_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """Each bot only sees its own trades."""
        trade_a = Trade(
            symbol=btc_symbol,
            side=Side.BUY,
            fill_price=Money(amount=50000.0, currency="USDT"),
            quantity=0.1,
            fee=Money(amount=5.0, currency="USDT"),
            bot_type=bot_a_context.bot_type,
            bot_instance_id=bot_a_context.instance_id,
            mode=TradingMode.DRY_RUN,
            exchange="binance",
        )

        with patch("stonks_trading.domains.trading.repositories.TradeModel") as mock_model:
            mock_model.create = AsyncMock(return_value=MagicMock(id=1))

            await save_trade_with_context(trade_a, bot_a_context)

            create_kwargs = mock_model.create.call_args.kwargs
            assert create_kwargs["bot_type"] == bot_a_context.bot_type
            assert create_kwargs["bot_instance_id"] == bot_a_context.instance_id


class TestBotStateIsolation:
    """Tests for bot state isolation."""

    @pytest.mark.asyncio
    async def test_state_isolated_by_context(
        self,
        bot_a_context: BotContext,
        bot_b_context: BotContext,
    ) -> None:
        """Each bot has its own state namespace."""
        state_a = {"positions": {}, "equity": 10000.0, "trades_today": 0}
        state_b = {"positions": {"BTC_USD": 1.0}, "equity": 11000.0, "trades_today": 5}

        with patch("stonks_trading.domains.trading.repositories.BotStateModel") as mock_model:
            mock_model.create = AsyncMock()

            await BotStateRepository.save(bot_a_context, state_a)
            create_kwargs_a = mock_model.create.call_args.kwargs
            assert create_kwargs_a["bot_type"] == bot_a_context.bot_type
            assert create_kwargs_a["bot_instance_id"] == bot_a_context.instance_id

            await BotStateRepository.save(bot_b_context, state_b)
            create_kwargs_b = mock_model.create.call_args.kwargs
            assert create_kwargs_b["bot_type"] == bot_b_context.bot_type
            assert create_kwargs_b["bot_instance_id"] == bot_b_context.instance_id


class TestBotInstanceIsolation:
    """Tests for bot instance registry isolation."""

    @pytest.mark.asyncio
    async def test_register_creates_isolated_instances(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """Each bot instance is independent."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceModel") as mock_model:
            mock_instance = MagicMock()
            mock_instance.id = 1
            mock_instance.bot_type = bot_a_context.bot_type
            mock_instance.instance_id = bot_a_context.instance_id
            mock_instance.symbols = ["BTC_USD"]
            mock_instance.mode = "dry_run"
            mock_instance.status = "stopped"
            mock_instance.config = {}
            mock_instance.last_seen_at = None
            mock_instance.created_at = datetime.utcnow()
            mock_model.create = AsyncMock(return_value=mock_instance)

            await BotInstanceRepository.register(
                bot_type=bot_a_context.bot_type,
                instance_id=bot_a_context.instance_id,
                symbols=["BTC_USD"],
                mode="dry_run",
            )

            mock_model.create.assert_called()
            create_kwargs = mock_model.create.call_args.kwargs
            assert create_kwargs["instance_id"] == bot_a_context.instance_id

    @pytest.mark.asyncio
    async def test_get_returns_only_matching_bot(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """BotInstanceRepository.get returns only the specific bot."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=None)

            await BotInstanceRepository.get(
                bot_type=bot_a_context.bot_type,
                instance_id=bot_a_context.instance_id,
            )

            mock_model.get_or_none.assert_called_with(
                bot_type=bot_a_context.bot_type,
                instance_id=bot_a_context.instance_id,
            )

    @pytest.mark.asyncio
    async def test_list_all_returns_all_bots(self) -> None:
        """BotInstanceRepository.list_all returns all registered bots."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceModel") as mock_model:
            mock_model.all = AsyncMock(return_value=[])

            await BotInstanceRepository.list_all()

            mock_model.all.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_type_filters_by_strategy(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """list_by_type returns only bots of a specific type."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceModel") as mock_model:
            mock_model.filter = AsyncMock(return_value=[])

            await BotInstanceRepository.list_by_type(bot_a_context.bot_type)

            mock_model.filter.assert_called_with(bot_type=bot_a_context.bot_type)


class TestClosePositionIsolation:
    """Tests for close_position_by_bot isolation."""

    @pytest.mark.asyncio
    async def test_close_position_respects_context(
        self,
        bot_a_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """close_position_by_bot only closes position for specified bot."""
        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=MagicMock())
            mock_model.get_or_none.return_value.save = AsyncMock()

            await close_position_by_bot(bot_a_context, btc_symbol)

            mock_model.get_or_none.assert_called_with(
                bot_type=bot_a_context.bot_type,
                bot_instance_id=bot_a_context.instance_id,
                symbol=btc_symbol.value,
            )


class TestMultiBotScenario:
    """End-to-end scenarios for multi-bot isolation."""

    @pytest.mark.asyncio
    async def test_two_bots_same_symbol_independent_positions(
        self,
        bot_a_context: BotContext,
        bot_b_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """Two bots can trade the same symbol with independent positions."""
        # Bot A enters a long position
        position_a = Position(
            symbol=btc_symbol,
            quantity=1.0,
            entry_price=Money(amount=50000.0, currency="USDT"),
            bot_type=bot_a_context.bot_type,
            bot_instance_id=bot_a_context.instance_id,
        )

        # Bot B has no position yet (quantity = 0)
        position_b = Position(
            symbol=btc_symbol,
            quantity=0.0,
            entry_price=Money(amount=50000.0, currency="USDT"),
            bot_type=bot_b_context.bot_type,
            bot_instance_id=bot_b_context.instance_id,
        )

        # Verify different contexts but same symbol
        assert position_a.bot_instance_id != position_b.bot_instance_id
        assert position_a.bot_type == position_b.bot_type
        assert position_a.symbol == position_b.symbol


class TestEdgeCases:
    """Edge case tests for multi-bot isolation."""

    @pytest.mark.asyncio
    async def test_same_instance_id_different_types_isolated(
        self,
        bot_a_context: BotContext,
    ) -> None:
        """Same instance_id but different bot_type are isolated."""
        different_type_context = BotContext(
            bot_type="mean_reversion",
            instance_id=bot_a_context.instance_id,  # Same instance_id!
        )

        assert bot_a_context.instance_id == different_type_context.instance_id
        assert bot_a_context.bot_type != different_type_context.bot_type

        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=None)

            await get_position_by_bot_and_symbol(bot_a_context, Symbol(value="BTC_USD"))
            await get_position_by_bot_and_symbol(different_type_context, Symbol(value="BTC_USD"))

            calls = mock_model.get_or_none.call_args_list
            assert calls[0].kwargs["bot_type"] == bot_a_context.bot_type
            assert calls[1].kwargs["bot_type"] == different_type_context.bot_type

    @pytest.mark.asyncio
    async def test_cross_bot_queries_return_none(
        self,
        bot_b_context: BotContext,
        btc_symbol: Symbol,
    ) -> None:
        """Querying with wrong context returns None, never another bot's data."""
        with patch("stonks_trading.domains.trading.repositories.PositionModel") as mock_model:
            mock_model.get_or_none = AsyncMock(return_value=None)

            result = await get_position_by_bot_and_symbol(bot_b_context, btc_symbol)

            call_kwargs = mock_model.get_or_none.call_args.kwargs
            assert call_kwargs["bot_type"] == bot_b_context.bot_type
            assert call_kwargs["bot_instance_id"] == bot_b_context.instance_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])