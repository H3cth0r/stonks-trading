"""Tests for notification services."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.notifications import DiscordNotifier


class TestDiscordNotifier:
    """Tests for DiscordNotifier."""

    def test_initialization(self) -> None:
        """Test notifier initializes correctly."""
        notifier = DiscordNotifier("https://discord.com/webhook")

        assert notifier.webhook_url == "https://discord.com/webhook"
        assert notifier.bot_context is None

    def test_with_bot_context(self) -> None:
        """Test creating notifier with bot context."""
        base_notifier = DiscordNotifier("https://discord.com/webhook")
        notifier = base_notifier.with_bot_context("neat_swing", "bot-001")

        assert notifier.bot_context == {"bot_type": "neat_swing", "instance_id": "bot-001"}

    @pytest.mark.asyncio
    async def test_send_message_no_webhook(self) -> None:
        """Test send_message returns False when no webhook."""
        notifier = DiscordNotifier("")
        result = await notifier.send_message("Test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        """Test successful message sending."""
        notifier = DiscordNotifier("https://discord.com/webhook")

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 204
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=mock_response)

        result = await notifier.send_message("Test message")

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_trade(self) -> None:
        """Test trade notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        trade = Trade(
            symbol=Symbol(value="BTC_USD"),
            side=Side.BUY,
            quantity=0.1,
            fill_price=Money(amount=50000.0, currency="USDT"),
            fee=Money(amount=5.0, currency="USDT"),
            fee_currency="USDT",
            slippage_bps=5.0,
            genome_id=1,
            exchange="binance",
            mode=Side.BUY,  # Trade.mode is Side enum
            created_at=datetime.utcnow(),
        )

        result = await notifier.send_trade(trade)

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_risk_alert(self) -> None:
        """Test risk alert notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        result = await notifier.send_risk_alert(
            event_type="HIGH_DRAWDOWN",
            severity="warning",
            message="Drawdown exceeded threshold",
            details={"current_dd": "15.5%", "threshold": "15%"},
        )

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_daily_summary(self) -> None:
        """Test daily summary notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        result = await notifier.send_daily_summary(
            date="2024-01-15",
            mode="dry_run",
            capital=10500.0,
            trades_count=5,
            buys=3,
            sells=2,
            realized_pnl=500.0,
            max_drawdown=0.05,
            position_qty=0.1,
            symbol="BTC_USD",
            genome_id="1",
            genome_roi=0.05,
        )

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_retraining_start(self) -> None:
        """Test retraining start notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        result = await notifier.send_retraining_start(
            symbols=["BTC_USD", "ETH_USD"],
            config={"generations": 30, "population_size": 150},
        )

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_retraining_complete(self) -> None:
        """Test retraining complete notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        results = [
            {"symbol": "BTC_USD", "improved": True, "new_roi": 15.0, "prev_roi": 10.0, "improvement_pct": 5.0, "new_genome_id": 2, "prev_genome_id": 1, "reason": "Better performance"},
            {"symbol": "ETH_USD", "improved": False, "new_roi": 8.0, "prev_roi": 12.0, "improvement_pct": -4.0, "new_genome_id": 3, "prev_genome_id": 1, "reason": "Worse performance"},
        ]

        result = await notifier.send_retraining_complete(results)

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_genome_comparison(self) -> None:
        """Test genome comparison notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        result = await notifier.send_genome_comparison(
            symbol="BTC_USD",
            new_genome_id=2,
            prev_genome_id=1,
            new_roi=15.0,
            prev_roi=10.0,
            improvement_pct=5.0,
            swapped=True,
        )

        assert result is True
        notifier.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_daily_summary_with_retraining(self) -> None:
        """Test daily summary with retraining status notification."""
        notifier = DiscordNotifier("https://discord.com/webhook")
        notifier.client = MagicMock()
        notifier.client.post = AsyncMock(return_value=MagicMock(status_code=204))

        retraining_results = [
            {"symbol": "BTC_USD", "improved": True, "new_roi": 15.0, "prev_roi": 10.0, "improvement_pct": 5.0, "new_genome_id": 2, "prev_genome_id": 1, "reason": "Better"},
        ]

        result = await notifier.send_daily_summary_with_retraining(
            date="2024-01-15",
            mode="dry_run",
            capital=10500.0,
            trades_count=5,
            buys=3,
            sells=2,
            realized_pnl=500.0,
            max_drawdown=0.05,
            position_qty=0.1,
            symbol="BTC_USD",
            genome_id="1",
            genome_roi=0.05,
            retraining_status="completed",
            retraining_results=retraining_results,
        )

        assert result is True
        notifier.client.post.assert_called_once()
