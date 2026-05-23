"""Cross-cutting notification services.

Used by bot, API, and use cases for Discord alerts.
No business logic — only formatting and delivery.
"""

from datetime import datetime
from typing import Any

import httpx

from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Money


class DiscordNotifier:
    """Discord webhook notifier for alerts and reports.

    Sends rich embeds for trade execution, risk events, and daily summaries.
    """

    def __init__(self, webhook_url: str, bot_context: Any = None):
        self.webhook_url = webhook_url
        self.client = httpx.AsyncClient(timeout=10.0)
        self.bot_context = bot_context

    def with_bot_context(self, bot_type: str, instance_id: str) -> "DiscordNotifier":
        """Create a notifier instance with bot context for notifications.

        Args:
            bot_type: Type of bot (e.g., "neat_swing")
            instance_id: Bot instance ID

        Returns:
            DiscordNotifier with bot context set
        """
        notifier = DiscordNotifier(self.webhook_url)
        notifier.bot_context = {"bot_type": bot_type, "instance_id": instance_id}
        return notifier

    async def send_message(
        self,
        content: str,
        embeds: list[dict[str, Any]] | None = None,
    ) -> bool:
        if not self.webhook_url:
            return False

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            response = await self.client.post(self.webhook_url, json=payload)
            return response.status_code in (200, 204)
        except Exception:
            return False

    async def send_trade(
        self,
        trade: Trade,
        portfolio_value: Money | None = None,
    ) -> bool:
        """Send trade execution notification."""
        color = 0x00FF00 if trade.side == Side.BUY else 0xFF0000

        fields = [
            {"name": "Symbol", "value": trade.symbol.value, "inline": True},
            {"name": "Side", "value": trade.side.value.upper(), "inline": True},
            {"name": "Price", "value": f"${trade.fill_price.amount:,.2f}", "inline": True},
            {"name": "Quantity", "value": f"{trade.quantity:.6f}", "inline": True},
            {
                "name": "Fee",
                "value": f"${trade.fee.amount:.2f} {trade.fee_currency}",
                "inline": True,
            },
            {"name": "Slippage", "value": f"{trade.slippage_bps:.1f} bps", "inline": True},
        ]

        if portfolio_value:
            fields.append(
                {
                    "name": "Portfolio",
                    "value": f"${portfolio_value.amount:,.2f}",
                    "inline": False,
                }
            )

        # Build bot context footer
        if self.bot_context:
            footer_text = f"Bot: {self.bot_context['bot_type']}/{self.bot_context['instance_id']}"
            if trade.genome_id:
                footer_text += f" • Genome #{trade.genome_id}"
            footer_text += f" • {trade.exchange}"
        else:
            footer_text = f"Genome #{trade.genome_id or 'N/A'} • {trade.exchange}"

        embed = {
            "title": f"Trade Executed: {trade.symbol.value}",
            "description": f"Mode: **{trade.mode.value}**",
            "color": color,
            "fields": fields,
            "timestamp": trade.created_at.isoformat()
            if trade.created_at
            else datetime.utcnow().isoformat(),
            "footer": {"text": footer_text},
        }

        return await self.send_message(
            f"Trade: {trade.side.value.upper()} {trade.symbol.value}",
            embeds=[embed],
        )

    async def send_risk_alert(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Send risk alert with color-coded severity."""
        color_map = {
            "critical": 0xFF0000,
            "warning": 0xFFA500,
            "info": 0x3498DB,
        }
        color = color_map.get(severity.lower(), 0xFFA500)

        fields = [{"name": k, "value": str(v), "inline": True} for k, v in (details or {}).items()]

        # Add bot context field if available
        if self.bot_context:
            fields.insert(
                0,
                {
                    "name": "Bot",
                    "value": f"{self.bot_context['bot_type']}/{self.bot_context['instance_id']}",
                    "inline": True,
                },
            )

        embed = {
            "title": f"Risk Alert: {event_type}",
            "description": message,
            "color": color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
        }

        mention = "@here" if severity.lower() in ("critical", "emergency") else ""
        return await self.send_message(
            f"{mention} Risk Alert ({severity.upper()})",
            embeds=[embed],
        )

    async def send_daily_summary(
        self,
        date: str,
        mode: str,
        capital: float,
        trades_count: int,
        buys: int,
        sells: int,
        realized_pnl: float,
        max_drawdown: float,
        position_qty: float,
        symbol: str,
        genome_id: str | None,
        genome_roi: float | None,
    ) -> bool:
        """Send daily summary embed."""
        embed = {
            "title": f"Daily Summary — {date}",
            "description": f"Mode: **{mode.upper()}**",
            "color": 0x3498DB,
            "fields": [
                {"name": "Capital", "value": f"${capital:,.2f}", "inline": False},
                {
                    "name": "Trades Today",
                    "value": f"{trades_count} ({buys}B, {sells}S)",
                    "inline": True,
                },
                {"name": "Realized P&L", "value": f"${realized_pnl:+.2f}", "inline": True},
                {"name": "Max Drawdown", "value": f"{max_drawdown:.2%}", "inline": True},
                {"name": "Position", "value": f"{position_qty:.6f} {symbol}", "inline": True},
                {
                    "name": "Genome",
                    "value": f"#{genome_id or 'N/A'} (ROI {genome_roi:+.2%})"
                    if genome_roi
                    else f"#{genome_id or 'N/A'}",
                    "inline": True,
                },
            ],
            "footer": {"text": "Retraining starts at 00:00 UTC"},
        }

        # Add bot context to embed if available
        if self.bot_context:
            embed["description"] = (
                f"Bot: **{self.bot_context['bot_type']}/{self.bot_context['instance_id']}**\n"
                + embed["description"]
            )
        return await self.send_message("Daily Trading Summary", embeds=[embed])

    async def close(self) -> None:
        await self.client.aclose()
