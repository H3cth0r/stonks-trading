"""NEAT Swing Bot - using IngestionOrchestrator for market data.

Implements the live trading bot for NEAT swing strategy with:
- IngestionOrchestrator for market data and features
- NEAT network inference for trading decisions
- Bot-scoped position and state management
- Risk management integration
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any

from stonks_trading.shared.ingest.orchestrator import IngestionOrchestrator
from stonks_trading.shared.logger import clear_bot_context, set_bot_context
from stonks_trading.shared.metrics import MetricsExporter

from stonks_trading.bots import BotRegistry
from stonks_trading.bots.base.bot import BaseBot
from stonks_trading.bots.neat_swing.scheduler_hook import get_scheduler_hook
from stonks_trading.bots.neat_swing.state import NeatSwingState
from stonks_trading.bots.neat_swing.strategy import (
    MIN_TRADE_INTERVAL,
    NeatSwingStrategy,
)

from stonks_trading.domains.health.use_cases import RecordHeartbeatUseCase
from stonks_trading.domains.trading.entities import Position
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.repositories import (
    get_active_genome,
    load_bot_state,
    register_bot_instance,
    save_bot_state,
    update_bot_instance_status,
)
from stonks_trading.domains.trading.services import FeeCalculator, RiskChecker
from stonks_trading.domains.trading.use_cases import ExecuteBotTradeUseCase
from stonks_trading.domains.trading.value_objects import Symbol

logger = logging.getLogger(__name__)


@BotRegistry.register("neat_swing")
class NeatSwingBot(BaseBot[NeatSwingState, NeatSwingStrategy]):
    """NEAT swing trading bot.

    Live trading implementation that:
    - Connects to WebSocket for real-time candles
    - Loads trained NEAT genomes for decision making
    - Executes trades via exchange adapter
    - Persists state for recovery
    """

    def __init__(
        self,
        context: Any,
        symbols: list[Symbol],
        mode: TradingMode,
        strategy: NeatSwingStrategy,
        initial_state: NeatSwingState,
        config_path: str = "config-neat.txt",
        capital_allocation: float | None = None,
    ):
        """Initialize NEAT swing bot.

        Args:
            context: BotContext for multi-bot isolation
            symbols: List of trading symbols
            mode: Trading mode (dry_run or live)
            strategy: NeatSwingStrategy instance
            initial_state: Initial NeatSwingState
            config_path: Path to NEAT config file
            capital_allocation: Capital allocation for this bot
        """
        super().__init__(
            context=context,
            symbols=symbols,
            mode=mode,
            strategy=strategy,
            initial_state=initial_state,
            capital_allocation=capital_allocation,
        )
        self.config_path = config_path
        self._running = False
        self._orchestrator: IngestionOrchestrator | None = None

    def set_orchestrator(self, orchestrator: IngestionOrchestrator) -> None:
        """Set the IngestionOrchestrator for market data."""
        self._orchestrator = orchestrator

    @property
    def bot_type(self) -> str:
        return "neat_swing"

    @property
    def required_data_frequency(self) -> str:
        return "1m"

    async def register(self) -> None:
        """Register bot instance with database."""
        await register_bot_instance(
            bot_type=self.bot_type,
            instance_id=self.context.instance_id,
            symbols=[s.value for s in self.symbols],
            mode=self.mode.value,
            config={"config_path": self.config_path},
        )
        logger.info(f"Registered bot {self.context}")

    async def start(self) -> None:
        """Start the bot main loop."""
        self._running = True

        # Set bot context for logging
        set_bot_context(self.bot_type, self.context.instance_id)

        # Register with database
        await self.register()

        # NEW: Wait for orchestrator to be ready (gap backfill complete)
        if not self._orchestrator:
            raise RuntimeError("Orchestrator not set - call set_orchestrator() before start()")

        logger.info("Waiting for IngestionOrchestrator to be ready...")
        await self._wait_for_orchestrator_ready()
        logger.info("IngestionOrchestrator ready - features available")

        # Load active genomes
        await self._load_active_genomes()

        # Load persisted state if any
        previous_state = await self.load_state()
        if previous_state:
            self.state = previous_state
            logger.info(f"Loaded previous state: {len(self.state.positions)} positions")

        # Start scheduler hook for daily retraining
        scheduler_hook = get_scheduler_hook()
        await scheduler_hook.on_bot_start(
            bot_context=self.context,
            symbols=[s.value for s in self.symbols],
        )

        # Update status
        await update_bot_instance_status(self.bot_type, self.context.instance_id, "running")

        # Run main loop
        await self._main_loop()

    async def _wait_for_orchestrator_ready(self) -> None:
        """Wait until orchestrator has enough data for feature computation."""
        max_wait = 600  # 10 minutes max (includes backfill time)
        waited = 0

        while waited < max_wait:
            all_ready = True
            for symbol in self.symbols:
                stats = self._orchestrator.get_feature_computer().get_stats(symbol.value)
                if not stats.get("has_features", False):
                    all_ready = False
                    logger.debug(f"Waiting for {symbol.value} - {stats.get('candles', 0)} candles")
                    break

            if all_ready:
                logger.info("All symbols have feature buffers ready")
                return

            await asyncio.sleep(5)
            waited += 5

        logger.warning("Orchestrator warmup timeout - proceeding with partial data")

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info(f"Stopping bot {self.context}")
        self._running = False

        # Stop scheduler hook for daily retraining
        scheduler_hook = get_scheduler_hook()
        await scheduler_hook.on_bot_stop(self.context)

        # Persist state
        await self.persist_state()

        # Update status
        await update_bot_instance_status(self.bot_type, self.context.instance_id, "stopped")

        # Clear bot context from logs
        clear_bot_context()

    async def handle_candle(self, candle: dict[str, Any]) -> None:
        """Process a new candle from market data stream.

        DEPRECATED: Bot now polls IngestionOrchestrator directly.
        Kept for abstract base class compliance.
        """
        # No-op: Bot now polls orchestrator in _main_loop()
        pass

    async def persist_state(self) -> None:
        """Save current state to database."""
        state_dict = self.state.to_dict()
        await save_bot_state(self.context, state_dict)
        logger.debug(f"Persisted state for {self.context}")

    async def load_state(self) -> NeatSwingState | None:
        """Load previous state from database.

        Returns:
            NeatSwingState or None if no previous state
        """
        data = await load_bot_state(self.context)
        if data:
            return NeatSwingState.from_dict(data)
        return None

    async def _load_active_genomes(self) -> None:
        """Load active NEAT genomes for all symbols."""
        for symbol in self.symbols:
            genome = await get_active_genome(symbol)
            if genome and genome.genome_data:
                try:
                    self.strategy.load_genome(symbol, genome, self.strategy.neat_config)
                    logger.info(f"Loaded genome for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to load genome for {symbol}: {e}")

    async def _main_loop(self) -> None:
        """Main loop: poll orchestrator for features and trade."""
        last_processed: dict[Symbol, datetime] = {}

        while self._running:
            try:
                for symbol in self.symbols:
                    if symbol not in self.strategy.networks:
                        continue

                    # Get feature computer from orchestrator
                    feature_computer = self._orchestrator.get_feature_computer()

                    # Get latest candle timestamp from feature computer
                    stats = feature_computer.get_stats(symbol.value)
                    if not stats.get("has_features", False):
                        continue

                    # Build state vector using features from orchestrator
                    state_vector = await self._build_state_vector(symbol)
                    if state_vector is None:
                        continue

                    # Get decision from NEAT network
                    buy_prob, sell_prob = self.strategy.activate_network(symbol, state_vector)
                    action = self._determine_action(buy_prob, sell_prob, symbol)

                    if action:
                        # Get current price from feature computer's latest data
                        current_price = self._get_current_price(symbol)

                        trade = await self._execute_trade(symbol, action, current_price)
                        if trade:
                            self.state.record_trade()
                            self.state.update_equity(
                                self.state.current_equity
                                + (trade.realized_pnl.amount if trade.realized_pnl else 0)
                            )
                            await self.persist_state()

                            # Instrument metrics
                            MetricsExporter.increment_bot_trades(
                                bot_type=self.bot_type,
                                bot_instance_id=self.context.instance_id,
                                symbol=symbol.value,
                                side=action.value,
                            )
                            MetricsExporter.set_bot_equity(
                                bot_type=self.bot_type,
                                bot_instance_id=self.context.instance_id,
                                equity_usd=self.state.current_equity,
                            )
                            # Calculate drawdown from peak and current equity
                            drawdown_pct = 0.0
                            if self.state.peak_equity > 0:
                                drawdown_pct = (
                                    (self.state.peak_equity - self.state.current_equity)
                                    / self.state.peak_equity
                                    * 100
                                )
                            MetricsExporter.set_bot_drawdown(
                                bot_type=self.bot_type,
                                bot_instance_id=self.context.instance_id,
                                drawdown_pct=drawdown_pct,
                            )
                            position = self.state.positions.get(symbol)
                            if position:
                                MetricsExporter.set_bot_position(
                                    bot_type=self.bot_type,
                                    bot_instance_id=self.context.instance_id,
                                    symbol=symbol.value,
                                    quantity=position.quantity,
                                )

                            logger.info(f"Executed {action.value} for {symbol} at {current_price}")

                # Sleep between iterations (1 minute candles)
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)

    async def _build_state_vector(self, symbol: Symbol) -> list[float] | None:
        """Build 7-element state vector using features from IngestionOrchestrator."""
        position = self.state.positions.get(symbol)

        # Get features from orchestrator's LiveFeatureComputer
        feature_computer = self._orchestrator.get_feature_computer()

        # Get the feature DataFrame for this symbol
        feature_df = feature_computer.get_feature_df(symbol.value)
        if feature_df is None or len(feature_df) == 0:
            return None

        # Get latest feature values
        last = feature_df.iloc[-1]
        current_price = last["Close"]

        features = {
            "trend_1h": float(last["trend_1h"]),
            "rsi_1h": float(last["rsi_1h"]),
            "rsi_15m": float(last["rsi_15m"]),
            "roc": float(last["roc"]),
            "bb_width": float(last["bb_width"]),
        }

        # Build full state vector
        return self.strategy.build_state_vector(current_price, position, features)

    def _get_current_price(self, symbol: Symbol) -> float:
        """Get current price from orchestrator's feature computer."""
        feature_computer = self._orchestrator.get_feature_computer()
        feature_df = feature_computer.get_feature_df(symbol.value)
        if feature_df is not None and len(feature_df) > 0:
            return float(feature_df.iloc[-1]["Close"])
        return 0.0

    def _determine_action(self, buy_prob: float, sell_prob: float, symbol: Symbol) -> Side | None:
        """Determine trading action from NEAT output.

        Enforces 15-minute trade interval.

        Args:
            buy_prob: Buy probability from network
            sell_prob: Sell probability from network
            symbol: Trading symbol

        Returns:
            Side.BUY, Side.SELL, or None
        """
        # Check trade interval
        if self.state.last_trade_time:
            minutes_since = (
                asyncio.get_event_loop().time() - self.state.last_trade_time.timestamp()
            ) / 60
            if minutes_since < MIN_TRADE_INTERVAL:
                return None

        # Use strategy's determine_action
        is_invested = (
            self.state.positions.get(symbol) is not None
            and self.state.positions[symbol].quantity > 0
        )

        return self.strategy.determine_action(buy_prob, sell_prob, is_invested)

    async def _execute_trade(
        self, symbol: Symbol, side: Side, price: float
    ) -> Any | None:
        """Execute trade via use case.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            price: Current price

        Returns:
            Trade entity if successful, None otherwise
        """
        if not self.adapter:
            logger.error("No adapter configured")
            return None

        # Get current position
        position = self.state.positions.get(symbol)

        # Create candle dict for trade execution
        candle = {
            "symbol": symbol.value,
            "close": price,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Calculate quantity (all-in logic)
        quantity = self._calculate_quantity(symbol, candle, side, position)

        # Execute trade
        use_case = ExecuteBotTradeUseCase(
            adapter=self.adapter,
            risk_checker=RiskChecker(),
            fee_calculator=FeeCalculator(),
        )

        result = await use_case.execute(
            symbol=symbol,
            side=side,
            quantity=quantity,
            candle=candle,
            current_position=position,
            state=self.state,
            context=self.context,
        )

        if result.success and result.trade:
            # Update local position state
            if side == Side.BUY:
                if position:
                    position.add_to_position(result.trade.quantity, result.trade.fill_price)
                else:
                    self.state.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=result.trade.quantity,
                        entry_price=result.trade.fill_price,
                        bot_type=self.context.bot_type,
                        bot_instance_id=self.context.instance_id,
                    )
            else:  # SELL
                if position:
                    position.reduce_position(result.trade.quantity)
                    if position.quantity <= 0:
                        del self.state.positions[symbol]

            return result.trade
        else:
            if result.error:
                logger.warning(f"Trade failed: {result.error}")
            return None

    def _calculate_quantity(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        side: Side,
        position: Position | None,
    ) -> float:
        """Calculate trade quantity (all-in / all-out logic).

        Uses capital_allocation if set, otherwise falls back to available balance
        or current equity.

        Args:
            symbol: Trading symbol
            candle: Current candle
            side: Buy or sell
            position: Current position if any

        Returns:
            Quantity to trade
        """
        price = candle["close"]

        if side == Side.BUY:
            # All-in: use capital_allocation if set, otherwise available balance
            if self.capital_allocation is not None:
                usdt_balance = self.capital_allocation
            elif self.adapter:
                balances = self.adapter.get_balance()
                if isinstance(balances, list):
                    usdt_balance = next((b.total for b in balances if b.asset == "USDT"), 0.0)
                else:
                    usdt_balance = balances.total if balances.asset == "USDT" else 0.0
            else:
                usdt_balance = self.state.current_equity

            # Calculate max quantity with fees
            fee_rate = 0.001  # TRANSACTION_FEE from NEAT
            notional = usdt_balance * (1 - fee_rate)
            quantity: float = notional / price
            return quantity
        else:
            # All-out: sell entire position
            if position and position.quantity > 0:
                return position.quantity
            return 0.0

    async def heartbeat(self) -> None:
        """Send periodic heartbeat for health monitoring.

        Called by runner every 60 seconds to indicate the bot
        is alive and processing data.
        """
        try:
            # Compute state hash from current state
            state_hash = self._compute_state_hash()

            # Get last candle timestamp from strategy if available
            last_candle_ts = None
            if self.symbols:
                # Try to get the most recent candle timestamp from strategy
                symbol = self.symbols[0]
                last_candle_ts = self.strategy.get_last_candle_timestamp(symbol)

            use_case = RecordHeartbeatUseCase()
            await use_case.execute(
                context=self.context,
                state_hash=state_hash,
                candle_timestamp=last_candle_ts,
            )
            logger.debug(f"Heartbeat sent for {self.context}")
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")

    def _compute_state_hash(self) -> str:
        """Compute hash of current bot state for integrity.

        Returns:
            Hex string hash of key state values
        """
        state_parts = [
            self.context.bot_type,
            self.context.instance_id,
            str(self.state.current_equity),
            str(len(self.state.positions)),
            str(self.state.trades_today),
        ]
        state_str = "|".join(state_parts)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]
