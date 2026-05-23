"""Base bot class for multi-bot architecture.

Abstract base class that all trading bots must implement.
Provides lifecycle hooks and state management contracts.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from stonks_trading.bots.base.context import BotContext
from stonks_trading.bots.base.state import BaseBotState
from stonks_trading.bots.base.strategy import BaseStrategy
from stonks_trading.domains.trading.enums import TradingMode
from stonks_trading.domains.trading.value_objects import Symbol

StateT = TypeVar("StateT", bound=BaseBotState)
StrategyT = TypeVar("StrategyT", bound=BaseStrategy)


class BaseBot(ABC, Generic[StateT, StrategyT]):
    """Abstract base class for all trading bots.

    Contract:
    1. Initialize with context, symbols, mode, strategy, and initial state
    2. register() - Self-register with the database
    3. start() - Initialize and begin main loop
    4. stop() - Graceful shutdown
    5. handle_candle() - Process incoming market data
    6. persist_state() - Save state to database
    7. load_state() - Restore state from database

    Each bot instance is isolated by its BotContext.

    Example:
        @BotRegistry.register("neat_swing")
        class NeatSwingBot(BaseBot[NeatSwingState, NeatSwingStrategy]):
            @property
            def bot_type(self) -> str: return "neat_swing"

            @property
            def required_data_frequency(self) -> str: return "1m"

            async def register(self) -> None: ...
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def handle_candle(self, candle) -> None: ...
            async def persist_state(self) -> None: ...
            async def load_state(self) -> NeatSwingState | None: ...
    """

    def __init__(
        self,
        context: BotContext,
        symbols: list[Symbol],
        mode: TradingMode,
        strategy: StrategyT,
        initial_state: StateT,
    ):
        """Initialize bot with context and dependencies.

        Args:
            context: Bot identity context (type + instance_id).
            symbols: List of trading symbols this bot handles.
            mode: Trading mode (dry_run or live).
            strategy: Strategy instance for signal generation.
            initial_state: Initial state (used if no persisted state).
        """
        self.context = context
        self.symbols = symbols
        self.mode = mode
        self.strategy = strategy
        self.state = initial_state

        # Injected at runtime (set by start() or factory)
        self.adapter = None

    @property
    @abstractmethod
    def bot_type(self) -> str:
        """Unique bot type identifier.

        Must match the registry key and directory name (e.g., "neat_swing").

        Returns:
            Bot type string.
        """
        ...

    @property
    @abstractmethod
    def required_data_frequency(self) -> str:
        """Data frequency this bot needs.

        Used by WebSocket manager to subscribe to correct streams.

        Returns:
            Frequency string: "1m", "5m", "1h", "1d", etc.
        """
        ...

    @abstractmethod
    async def register(self) -> None:
        """Register this bot instance with the database.

        Called once during initialization to persist bot metadata
        and configuration. Should update BotInstanceRepository.
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the bot main loop.

        Initializes adapters, loads persisted state, connects to
        data streams, and begins processing.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown.

        Persists state, closes connections, and updates status.
        """
        ...

    @abstractmethod
    async def handle_candle(self, candle: dict[str, Any]) -> None:
        """Process a new candle from market data stream.

        This is the main entry point for trading decisions.
        The bot should:
        1. Extract symbol from candle
        2. Compute features via strategy
        3. Generate signal via strategy
        4. Execute trade if signal present

        Args:
            candle: OHLCV candle data with symbol.
        """
        ...

    @abstractmethod
    async def persist_state(self) -> None:
        """Save current state to database.

        Called periodically and on shutdown to ensure state recovery.
        Uses BotStateRepository for persistence.
        """
        ...

    @abstractmethod
    async def load_state(self) -> StateT | None:
        """Load previous state from database.

        Called during startup to restore interrupted sessions.

        Returns:
            Reconstructed state or None if no previous state.
        """
        ...
