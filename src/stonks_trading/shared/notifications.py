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

    async def send_retraining_start(
        self,
        symbols: list[str],
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Send notification when retraining starts.

        Args:
            symbols: List of symbols being retrained
            config: Training configuration (generations, population size, etc.)
        """
        config = config or {}
        generations = config.get("generations", 30)
        population = config.get("population_size", 150)

        fields = [
            {"name": "Symbols", "value": ", ".join(symbols), "inline": False},
            {"name": "Generations", "value": str(generations), "inline": True},
            {"name": "Population", "value": str(population), "inline": True},
        ]

        # Add bot context
        if self.bot_context:
            fields.insert(
                0,
                {
                    "name": "Bot",
                    "value": f"{self.bot_context['bot_type']}/{self.bot_context['instance_id']}",
                    "inline": False,
                },
            )

        embed = {
            "title": "🔄 Daily Retraining Started",
            "description": "NEAT genome retraining has begun for the configured symbols.",
            "color": 0x3498DB,  # Blue
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return await self.send_message("Daily Retraining Started", embeds=[embed])

    async def send_retraining_complete(
        self,
        results: list[dict[str, Any]],
    ) -> bool:
        """Send notification when retraining completes with results.

        Args:
            results: List of retraining results per symbol
        """
        improved_count = sum(1 for r in results if r.get("improved", False))
        total_symbols = len(results)

        fields = []

        # Add bot context
        if self.bot_context:
            fields.append(
                {
                    "name": "Bot",
                    "value": f"{self.bot_context['bot_type']}/{self.bot_context['instance_id']}",
                    "inline": False,
                }
            )

        fields.append(
            {
                "name": "Summary",
                "value": f"{improved_count}/{total_symbols} symbols improved",
                "inline": False,
            }
        )

        # Add results for each symbol
        for result in results:
            symbol = result.get("symbol", "Unknown")
            improved = result.get("improved", False)
            new_roi = result.get("new_roi", 0.0)
            prev_roi = result.get("prev_roi", 0.0)
            improvement = result.get("improvement_pct", 0.0)
            reason = result.get("reason", "")

            if improved:
                value = (
                    f"✅ **IMPROVED** +{improvement:.2f}%\n"
                    f"New ROI: {new_roi:.2f}% | Prev: {prev_roi:.2f}%"
                )
                color = 0x00FF00  # Green
            else:
                value = f"⬜ No improvement\n{reason}"
                color = 0x808080  # Gray

            fields.append(
                {
                    "name": f"📊 {symbol}",
                    "value": value,
                    "inline": True,
                }
            )

        embed = {
            "title": "✅ Daily Retraining Complete",
            "description": f"Completed retraining for {total_symbols} symbol(s).",
            "color": color
            if improved_count > 0
            else 0xFFA500,  # Green if improved, orange otherwise
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Hot-swap applied for improved genomes"},
        }

        return await self.send_message("Retraining Complete", embeds=[embed])

    async def send_genome_comparison(
        self,
        symbol: str,
        new_genome_id: int | None,
        prev_genome_id: int | None,
        new_roi: float,
        prev_roi: float,
        improvement_pct: float,
        swapped: bool,
    ) -> bool:
        """Send genome comparison notification.

        Args:
            symbol: Trading symbol
            new_genome_id: New genome ID
            prev_genome_id: Previous genome ID
            new_roi: New genome ROI percentage
            prev_roi: Previous genome ROI percentage
            improvement_pct: Improvement percentage points
            swapped: Whether the genome was swapped
        """
        if swapped:
            title = f"🔄 Genome Swapped: {symbol}"
            description = f"New genome outperformed previous by {improvement_pct:.2f}%"
            color = 0x00FF00  # Green
            status = "✅ ACTIVATED"
        else:
            title = f"📊 Genome Comparison: {symbol}"
            description = f"No significant improvement ({improvement_pct:.2f}%)"
            color = 0xFFA500  # Orange
            status = "⬜ KEPT PREVIOUS"

        fields = [
            {
                "name": "Status",
                "value": status,
                "inline": False,
            },
            {
                "name": "Symbol",
                "value": symbol,
                "inline": True,
            },
            {
                "name": "New Genome",
                "value": f"#{new_genome_id or 'N/A'} ({new_roi:+.2f}%)",
                "inline": True,
            },
            {
                "name": "Previous Genome",
                "value": f"#{prev_genome_id or 'N/A'} ({prev_roi:+.2f}%)",
                "inline": True,
            },
            {
                "name": "Improvement",
                "value": f"{improvement_pct:+.2f}%",
                "inline": True,
            },
        ]

        # Add bot context
        if self.bot_context:
            fields.insert(
                0,
                {
                    "name": "Bot",
                    "value": f"{self.bot_context['bot_type']}/{self.bot_context['instance_id']}",
                    "inline": False,
                },
            )

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Hot-swap decision based on validation ROI"},
        }

        return await self.send_message(
            f"Genome Comparison: {symbol}",
            embeds=[embed],
        )

    async def send_daily_summary_with_retraining(
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
        retraining_status: str,
        retraining_results: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send daily summary with retraining status.

        Args:
            date: Date string
            mode: Trading mode
            capital: Current capital
            trades_count: Total trades today
            buys: Number of buy trades
            sells: Number of sell trades
            realized_pnl: Realized P&L
            max_drawdown: Maximum drawdown
            position_qty: Current position quantity
            symbol: Trading symbol
            genome_id: Current genome ID
            genome_roi: Current genome ROI
            retraining_status: Status of retraining (completed, pending, failed)
            retraining_results: Retraining results if completed
        """
        # Determine retraining color and status
        status_colors = {
            "completed": 0x00FF00,  # Green
            "pending": 0xFFA500,  # Orange
            "failed": 0xFF0000,  # Red
            "running": 0x3498DB,  # Blue
        }
        status_color = status_colors.get(retraining_status.lower(), 0x808080)

        status_emoji = {
            "completed": "✅",
            "pending": "⏳",
            "failed": "❌",
            "running": "🔄",
        }.get(retraining_status.lower(), "⬜")

        # Build retraining info
        retraining_info = f"{status_emoji} {retraining_status.upper()}"
        if retraining_results and retraining_status.lower() == "completed":
            improved = sum(1 for r in retraining_results if r.get("improved", False))
            total = len(retraining_results)
            retraining_info += f" ({improved}/{total} improved)"

        fields = [
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
            {
                "name": "Retraining",
                "value": retraining_info,
                "inline": True,
            },
        ]

        # Add bot context
        if self.bot_context:
            fields.insert(
                0,
                {
                    "name": "Bot",
                    "value": f"{self.bot_context['bot_type']}/{self.bot_context['instance_id']}",
                    "inline": False,
                },
            )

        embed = {
            "title": f"Daily Summary — {date}",
            "description": f"Mode: **{mode.upper()}**",
            "color": status_color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Next retraining at 00:00 UTC"},
        }

        return await self.send_message("Daily Trading Summary", embeds=[embed])

    async def close(self) -> None:
        await self.client.aclose()
