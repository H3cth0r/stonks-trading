"""Scheduler lifecycle hook for NEAT Swing Bot.

Integrates the training scheduler with bot start/stop events
to enable automatic daily retraining.
"""

import logging

from stonks_trading.bots.base.context import BotContext
from stonks_trading.domains.training.scheduler_integration import (
    BotSchedulerLifecycle,
    TrainingScheduler,
)
from stonks_trading.shared.notifications import DiscordNotifier

logger = logging.getLogger(__name__)


class NeatSwingSchedulerHook:
    """Lifecycle hook for integrating scheduler with NeatSwingBot.

    Automatically enables daily retraining when the bot starts
    and disables it when the bot stops.
    """

    def __init__(
        self,
        scheduler: TrainingScheduler | None = None,
    ):
        """Initialize scheduler hook.

        Args:
            scheduler: Training scheduler instance (creates default if None)
        """
        self.scheduler = scheduler or TrainingScheduler()
        self.lifecycle = BotSchedulerLifecycle(self.scheduler)

    async def on_bot_start(
        self,
        bot_context: BotContext,
        symbols: list[str],
        notifier: DiscordNotifier | None = None,
    ) -> None:
        """Call when bot starts.

        Args:
            bot_context: Bot context
            symbols: Trading symbols
            notifier: Optional notifier for retraining alerts
        """
        # Update notifier if provided
        if notifier:
            self.scheduler._notifier = notifier

        await self.lifecycle.on_bot_start(bot_context, symbols)
        logger.info(f"Enabled scheduled retraining for {bot_context}")

    async def on_bot_stop(self, bot_context: BotContext) -> None:
        """Call when bot stops.

        Args:
            bot_context: Bot context
        """
        await self.lifecycle.on_bot_stop(bot_context)
        logger.info(f"Disabled scheduled retraining for {bot_context}")


# Global hook instance (shared across all NeatSwingBot instances)
_global_hook: NeatSwingSchedulerHook | None = None


def get_scheduler_hook() -> NeatSwingSchedulerHook:
    """Get or create the global scheduler hook."""
    global _global_hook
    if _global_hook is None:
        _global_hook = NeatSwingSchedulerHook()
    return _global_hook


def reset_scheduler_hook() -> None:
    """Reset the global scheduler hook (for testing)."""
    global _global_hook
    _global_hook = None
