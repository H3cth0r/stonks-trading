"""Use cases for trading domain.

Use cases orchestrate business logic by calling services and repositories.
They contain no direct SQL or HTTP calls.
"""

from contextlib import suppress
from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.adapters import IExchangeAdapter
from stonks_trading.domains.trading.entities import (
    ActivityItem,
    Balance,
    CheckRiskResult,
    EvaluateSignalResult,
    ExecuteTradeResult,
    Order,
    Position,
    RiskEvent,
    Trade,
    TrainingRun,
)
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.repositories import (
    list_orders,
    list_risk_events,
    list_risk_events_by_bot,
    list_trades,
    list_trades_by_bot,
    list_training_runs,
    prune_genomes,
    save_position,
    save_position_with_context,
    save_risk_event,
    save_trade,
    save_trade_with_context,
)
from stonks_trading.domains.trading.services import (
    FeeCalculator,
    RiskChecker,
)
from stonks_trading.domains.trading.value_objects import BotContext, InstrumentMapper, Money, Symbol


class ExecuteTradeUseCase:
    """Execute trade use case.

    Orchestrates trade execution with risk checks, fee calculation,
    and persistence. Used by both bot and API.
    """

    def __init__(
        self,
        risk_checker: RiskChecker,
        fee_calculator: FeeCalculator,
        instrument_mapper: InstrumentMapper,
    ):
        """Initialize use case with services.

        Args:
            risk_checker: Risk validation service
            fee_calculator: Fee calculation service
            instrument_mapper: Symbol mapping service
        """
        self.risk_checker = risk_checker
        self.fee_calculator = fee_calculator
        self.instrument_mapper = instrument_mapper

    async def execute(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: Money,
        portfolio_value: Money,
        current_position: Position | None = None,
        daily_trade_count: int = 0,
        minutes_since_last_trade: int = 999,
        current_drawdown: float = 0.0,
        venue: str = "binance",
        order_id: str | None = None,
    ) -> ExecuteTradeResult:
        """Execute trade with full validation and persistence.

        Args:
            symbol: Trading symbol (canonical)
            side: Buy or sell
            quantity: Amount to trade
            price: Execution price
            portfolio_value: Current portfolio value
            current_position: Existing position if any
            daily_trade_count: Trades executed today
            minutes_since_last_trade: Time since last trade
            current_drawdown: Current portfolio drawdown
            venue: Target venue for execution
            order_id: External order ID if available

        Returns:
            ExecuteTradeResult with trade details or error
        """
        # Calculate notional value
        notional = Money(amount=price.amount * quantity, currency=price.currency)

        # Risk check
        risk_result = self.risk_checker.check_trade(
            side=side,
            notional=notional,
            portfolio_value=portfolio_value,
            current_position=current_position,
            daily_trade_count=daily_trade_count,
            minutes_since_last_trade=minutes_since_last_trade,
            current_drawdown=current_drawdown,
        )

        if not risk_result.allowed:
            return ExecuteTradeResult(
                success=False,
                risk_check=risk_result,
                error=f"Risk check failed: {risk_result.reason}",
            )

        # Calculate fee
        fee = self.fee_calculator.calculate_fee(notional, is_maker=False)

        # Create trade entity
        trade = Trade(
            symbol=symbol,
            side=side,
            fill_price=price,
            quantity=quantity,
            fee=fee,
            order_id=order_id,
        )

        # Persist trade
        saved_trade = await save_trade(trade)

        # Update position
        if side == Side.BUY:
            if current_position:
                current_position.add_to_position(quantity, price)
            else:
                current_position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=price,
                )
        else:  # SELL
            if current_position:
                current_position.reduce_position(quantity)

        if current_position:
            saved_position = await save_position(current_position)
        else:
            saved_position = None

        return ExecuteTradeResult(
            success=True,
            trade=saved_trade,
            position=saved_position,
            risk_check=risk_result,
        )


class EvaluateSignalUseCase:
    """Evaluate NEAT signal and determine if trade should execute.

    Converts NEAT network output (buy_prob, sell_prob) into
    trading decisions with confidence scoring.
    """

    def __init__(
        self,
        risk_checker: RiskChecker,
        decision_threshold: float = 0.6,
    ):
        """Initialize use case.

        Args:
            risk_checker: Risk validation service
            decision_threshold: Probability threshold for action
        """
        self.risk_checker = risk_checker
        self.decision_threshold = decision_threshold

    def evaluate(
        self,
        buy_prob: float,
        sell_prob: float,
        current_position: Position | None,
        portfolio_value: Money,
        daily_trade_count: int = 0,
        minutes_since_last_trade: int = 999,
    ) -> EvaluateSignalResult:
        """Evaluate NEAT signal and return trading decision.

        Args:
            buy_prob: Network buy probability
            sell_prob: Network sell probability
            current_position: Current position if any
            portfolio_value: Current portfolio value
            daily_trade_count: Trades today
            minutes_since_last_trade: Time since last trade

        Returns:
            EvaluateSignalResult with action and confidence
        """
        # Determine action (matches NEAT/main.py logic)
        if buy_prob > self.decision_threshold and buy_prob > sell_prob:
            action = Side.BUY
            confidence = buy_prob
        elif sell_prob > self.decision_threshold and sell_prob > buy_prob:
            action = Side.SELL
            confidence = sell_prob
        else:
            return EvaluateSignalResult(
                action=None,
                confidence=max(buy_prob, sell_prob),
                should_trade=False,
                reason="No signal exceeds threshold",
            )

        # Check if action is valid given position
        if action == Side.BUY and current_position and current_position.is_open():
            return EvaluateSignalResult(
                action=action,
                confidence=confidence,
                should_trade=False,
                reason="Already in position (NEAT: all-in/all-out)",
            )

        if action == Side.SELL and (not current_position or not current_position.is_open()):
            return EvaluateSignalResult(
                action=action,
                confidence=confidence,
                should_trade=False,
                reason="No position to sell",
            )

        return EvaluateSignalResult(
            action=action,
            confidence=confidence,
            should_trade=True,
        )


class MonitorRiskUseCase:
    """Monitor risk limits and generate risk events.

    Used by bot to continuously check risk status.
    """

    def __init__(
        self,
        risk_checker: RiskChecker,
    ):
        """Initialize use case.

        Args:
            risk_checker: Risk validation service
        """
        self.risk_checker = risk_checker

    async def check(
        self,
        current_equity: Money,
        peak_equity: Money,
        daily_trade_count: int,
        symbol: Symbol | None = None,
    ) -> CheckRiskResult:
        """Run risk checks and generate events if needed.

        Args:
            current_equity: Current portfolio equity
            peak_equity: Peak equity (for drawdown calc)
            daily_trade_count: Trades executed today
            symbol: Current trading symbol

        Returns:
            CheckRiskResult with status and any risk events
        """
        events: list[RiskEvent] = []
        should_halt = False

        # Check drawdown
        dd_result = self.risk_checker.check_drawdown(current_equity, peak_equity)

        if dd_result.risk_level == RiskLevel.CRITICAL:
            event = RiskEvent(
                event_type="drawdown_breach",
                severity=RiskLevel.CRITICAL.value,
                message=dd_result.reason or "Max drawdown exceeded",
                symbol=symbol,
                metric_name="drawdown",
                metric_value=(peak_equity.amount - current_equity.amount) / peak_equity.amount,
                threshold_value=self.risk_checker.max_drawdown_pct,
                portfolio_value=current_equity,
            )
            events.append(event)
            await save_risk_event(event)
            should_halt = True

        elif dd_result.risk_level == RiskLevel.WARNING:
            event = RiskEvent(
                event_type="drawdown_warning",
                severity=RiskLevel.WARNING.value,
                message=dd_result.reason or "High drawdown warning",
                symbol=symbol,
                metric_name="drawdown",
                metric_value=(peak_equity.amount - current_equity.amount) / peak_equity.amount,
                threshold_value=self.risk_checker.max_drawdown_pct,
                portfolio_value=current_equity,
            )
            events.append(event)
            await save_risk_event(event)

        # Check trade limit
        if daily_trade_count >= self.risk_checker.max_trades_per_day:
            event = RiskEvent(
                event_type="trade_limit",
                severity=RiskLevel.WARNING.value,
                message=f"Daily trade limit reached: {daily_trade_count}",
                symbol=symbol,
                metric_name="daily_trades",
                metric_value=daily_trade_count,
                threshold_value=self.risk_checker.max_trades_per_day,
            )
            events.append(event)
            await save_risk_event(event)

        status = RiskLevel.OK
        if any(e.severity == RiskLevel.CRITICAL.value for e in events):
            status = RiskLevel.CRITICAL
        elif any(e.severity == RiskLevel.WARNING.value for e in events):
            status = RiskLevel.WARNING

        return CheckRiskResult(
            status=status,
            events=events,
            should_halt=should_halt,
        )


class FetchBalancesUseCase:
    """Fetch account balances from exchange.

    Orchestrates adapter call and mapping to domain entities.
    """

    def __init__(self, adapter: IExchangeAdapter):
        self.adapter = adapter

    async def execute(self) -> list[Balance]:
        """Fetch balances from configured exchange."""
        result = await self.adapter.get_balance()
        if isinstance(result, Balance):
            return [result]
        return result


class GetMarketDataUseCase:
    """Get current market price for a symbol."""

    def __init__(self, adapter: IExchangeAdapter):
        self.adapter = adapter

    async def execute(self, symbol: Symbol) -> Money:
        """Get current price."""
        return await self.adapter.get_price(symbol)


class FetchFeesUseCase:
    """Fetch and cache live fee tier from exchange."""

    def __init__(self, adapter: IExchangeAdapter, fee_calculator: FeeCalculator):
        self.adapter = adapter
        self.fee_calculator = fee_calculator

    async def execute(self) -> dict[str, float]:
        """Refresh fee tier and return rates."""
        tier = await self.fee_calculator.refresh_tier(self.adapter)
        return {"maker_rate": tier.maker_rate, "taker_rate": tier.taker_rate}


class GetCandlesUseCase:
    """Get OHLCV candles for a symbol from exchange."""

    def __init__(self, adapter: IExchangeAdapter):
        self.adapter = adapter

    async def execute(
        self,
        symbol: Symbol,
        interval: str = "1m",
        limit: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch candles from exchange.

        Args:
            symbol: Trading symbol (canonical)
            interval: Candle interval (1m, 5m, 1h, 1d)
            limit: Number of candles to fetch
            start: Start time (optional)
            end: End time (optional)

        Returns:
            List of OHLCV candle dictionaries
        """
        # Convert datetime to milliseconds timestamp if provided
        start_time = int(start.timestamp() * 1000) if start else None
        end_time = int(end.timestamp() * 1000) if end else None

        candles = await self.adapter.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

        return candles


class PlaceOrderUseCase:
    """Place order on exchange via adapter.

    Orchestrates the full order flow: price fetch, risk check,
    order placement, and persistence. This is the CLEAN architecture
    way to handle exchange interaction from the API layer.
    """

    def __init__(
        self,
        adapter: IExchangeAdapter,
        risk_checker: RiskChecker,
        fee_calculator: FeeCalculator,
    ):
        self.adapter = adapter
        self.risk_checker = risk_checker
        self.fee_calculator = fee_calculator

    async def execute(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: Money | None,
        current_position: Position | None,
        daily_trade_count: int,
        minutes_since_last_trade: int,
        current_drawdown: float = 0.0,
        daily_loss_pct: float = 0.0,
        in_safe_mode: bool = False,
    ) -> ExecuteTradeResult:
        """Execute trade with exchange adapter.

        Args:
            symbol: Trading symbol (canonical)
            side: Buy or sell
            quantity: Amount to trade
            price: Optional limit price (None for market orders)
            current_position: Existing position if any
            daily_trade_count: Trades executed today
            minutes_since_last_trade: Time since last trade
            current_drawdown: Current portfolio drawdown
            daily_loss_pct: Daily loss percentage
            in_safe_mode: Whether safe mode is active

        Returns:
            ExecuteTradeResult with trade details or error
        """

        # Get current price from exchange
        current_price = await self.adapter.get_price(symbol)
        execution_price = price or current_price

        # Calculate notional value
        notional = Money(
            amount=execution_price.amount * quantity,
            currency=execution_price.currency,
        )

        # Get portfolio value from exchange balances
        balances = await self.adapter.get_balance()
        if isinstance(balances, Balance):
            balances = [balances]
        total_value = sum(b.total for b in balances)
        portfolio_value = Money(amount=total_value, currency=execution_price.currency)

        # Risk check
        risk_result = self.risk_checker.check_trade(
            side=side,
            notional=notional,
            portfolio_value=portfolio_value,
            current_position=current_position,
            daily_trade_count=daily_trade_count,
            minutes_since_last_trade=minutes_since_last_trade,
            current_drawdown=current_drawdown,
            daily_loss_pct=daily_loss_pct,
            in_safe_mode=in_safe_mode,
        )

        if not risk_result.allowed:
            return ExecuteTradeResult(
                success=False,
                risk_check=risk_result,
                error=f"Risk check failed: {risk_result.reason}",
            )

        # Place order on exchange
        order_result = await self.adapter.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="market" if price is None else "limit",
            price=execution_price if price else None,
        )

        if not order_result.success:
            return ExecuteTradeResult(
                success=False,
                risk_check=risk_result,
                error=f"Order failed: {order_result.error}",
            )

        # Calculate fee based on fill
        fill_notional = Money(
            amount=(
                order_result.fill_price.amount
                if order_result.fill_price
                else execution_price.amount
            )
            * order_result.filled_quantity,
            currency=execution_price.currency,
        )
        fee = self.fee_calculator.calculate_fee(fill_notional, is_maker=False)

        # Create trade entity from order result
        trade = Trade(
            symbol=symbol,
            side=side,
            fill_price=order_result.fill_price or execution_price,
            quantity=order_result.filled_quantity,
            fee=fee,
            order_id=order_result.order_id,
        )

        # Persist trade
        saved_trade = await save_trade(trade)

        # Update position
        if side == Side.BUY:
            if current_position:
                current_position.add_to_position(
                    order_result.filled_quantity, order_result.fill_price or execution_price
                )
            else:
                current_position = Position(
                    symbol=symbol,
                    quantity=order_result.filled_quantity,
                    entry_price=order_result.fill_price or execution_price,
                )
        else:  # SELL
            if current_position:
                current_position.reduce_position(order_result.filled_quantity)

        if current_position:
            saved_position = await save_position(current_position)
        else:
            saved_position = None

        return ExecuteTradeResult(
            success=True,
            trade=saved_trade,
            position=saved_position,
            risk_check=risk_result,
        )


class ExecuteBotTradeUseCase:
    """Execute trade for bot with full state and context tracking.

    Orchestrates trade execution for the live bot with:
    - BotContext for multi-bot isolation
    - NeatSwingState integration (equity, peak, trades_today)
    - Bot-scoped persistence
    - Full risk validation
    """

    def __init__(
        self,
        adapter: IExchangeAdapter,
        risk_checker: RiskChecker,
        fee_calculator: FeeCalculator,
    ):
        """Initialize use case with services.

        Args:
            adapter: Exchange adapter for order execution
            risk_checker: Risk validation service
            fee_calculator: Fee calculation service
        """
        self.adapter = adapter
        self.risk_checker = risk_checker
        self.fee_calculator = fee_calculator

    async def execute(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        candle: dict[str, Any],
        current_position: Position | None,
        state: Any,
        context: BotContext,
    ) -> ExecuteTradeResult:
        """Execute trade with bot context and state.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Amount to trade
            candle: Current candle dict with 'close' price
            current_position: Existing position if any
            state: NeatSwingState with equity, peak_equity, trades_today, etc.
            context: BotContext for multi-bot isolation

        Returns:
            ExecuteTradeResult with trade details or error
        """
        # Get current price
        price = Money(amount=candle["close"], currency="USDT")
        notional = Money(amount=price.amount * quantity, currency=price.currency)

        # Compute risk parameters from state
        portfolio_value = Money(amount=state.current_equity, currency="USDT")
        minutes_since_last_trade = 999
        if state.last_trade_time:
            delta = datetime.utcnow() - state.last_trade_time
            minutes_since_last_trade = int(delta.total_seconds() / 60)
        current_drawdown = 0.0
        if state.peak_equity > 0:
            current_drawdown = (state.peak_equity - state.current_equity) / state.peak_equity

        # Risk check
        risk_result = self.risk_checker.check_trade(
            side=side,
            notional=notional,
            portfolio_value=portfolio_value,
            current_position=current_position,
            daily_trade_count=state.trades_today,
            minutes_since_last_trade=minutes_since_last_trade,
            current_drawdown=current_drawdown,
            daily_loss_pct=state.daily_loss_pct,
            in_safe_mode=state.in_safe_mode,
            last_realized_loss_time=state.last_realized_loss_time,
        )

        if not risk_result.allowed:
            return ExecuteTradeResult(
                success=False,
                risk_check=risk_result,
                error=f"Risk check failed: {risk_result.reason}",
            )

        # Execute via adapter
        order_result = await self.adapter.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="market",
        )

        if not order_result.success:
            return ExecuteTradeResult(
                success=False,
                risk_check=risk_result,
                error=f"Order failed: {order_result.error}",
            )

        # Calculate fee
        fill_price = order_result.fill_price or price
        fill_notional = Money(
            amount=fill_price.amount * order_result.filled_quantity,
            currency=fill_price.currency,
        )
        fee = self.fee_calculator.calculate_fee(fill_notional, is_maker=False)

        # Build trade entity with bot context
        trade = Trade(
            symbol=symbol,
            side=side,
            fill_price=fill_price,
            quantity=order_result.filled_quantity,
            fee=fee,
            order_id=order_result.order_id,
            bot_type=context.bot_type,
            bot_instance_id=context.instance_id,
        )

        # Persist with bot context
        saved_trade = await save_trade_with_context(trade, context)

        # Update position
        updated_position = self._update_position(current_position, side, trade, context)
        if updated_position:
            await save_position_with_context(updated_position, context)

        return ExecuteTradeResult(
            success=True,
            trade=saved_trade,
            position=updated_position,
            risk_check=risk_result,
        )

    def _update_position(
        self,
        current: Position | None,
        side: Side,
        trade: Trade,
        context: BotContext,
    ) -> Position | None:
        """Update position after trade."""
        if side == Side.BUY:
            if current:
                current.add_to_position(trade.quantity, trade.fill_price)
                return current
            return Position(
                symbol=trade.symbol,
                quantity=trade.quantity,
                entry_price=trade.fill_price,
                bot_type=context.bot_type,
                bot_instance_id=context.instance_id,
            )
        else:  # SELL
            if current:
                current.reduce_position(trade.quantity)
                return current if current.quantity > 0 else None
            return None


# =============================================================================
# Phase 6 Use Cases - Dashboard Support
# =============================================================================


class ListActivityUseCase:
    """Aggregate activity from multiple sources for unified timeline.

    This is BUSINESS LOGIC - it coordinates multiple repository calls
    and aggregates results into a unified timeline. This belongs in the
    use case layer, not the repository layer.
    """

    async def execute(
        self,
        bot_context: BotContext | None = None,
        types: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[ActivityItem], str | None]:
        """Aggregate activity from trades, risk events, etc.

        Args:
            bot_context: Optional bot context filter
            types: Optional list of activity types to include
            cursor: Optional cursor for pagination (timestamp-based)
            limit: Maximum number of results

        Returns:
            Tuple of (activity items, next cursor)
        """
        activities: list[ActivityItem] = []
        cutoff: datetime | None = None

        if cursor:
            with suppress(ValueError):
                cutoff = datetime.fromisoformat(cursor)

        # Get trades and convert to activity items
        if not types or "trade" in types:
            trades = (
                await list_trades_by_bot(bot_context, limit=limit)
                if bot_context
                else await list_trades(limit=limit)
            )
            for trade in trades:
                if cutoff and trade.created_at >= cutoff:
                    continue
                activities.append(
                    ActivityItem(
                        id=trade.id or 0,
                        type="trade",
                        timestamp=trade.created_at,
                        symbol=trade.symbol,
                        data={
                            "side": trade.side.value,
                            "quantity": trade.quantity,
                            "fill_price": trade.fill_price.amount if trade.fill_price else 0.0,
                            "fee": trade.fee.amount if trade.fee else 0.0,
                        },
                        bot_type=trade.bot_type,
                        bot_instance_id=trade.bot_instance_id,
                    )
                )

        # Get risk events and convert to activity items
        if not types or "risk_event" in types:
            risk_events = (
                await list_risk_events_by_bot(bot_context, limit=limit)
                if bot_context
                else await list_risk_events(limit=limit)
            )
            for event in risk_events:
                if cutoff and event.created_at >= cutoff:
                    continue
                activities.append(
                    ActivityItem(
                        id=event.id or 0,
                        type="risk_event",
                        timestamp=event.created_at,
                        symbol=event.symbol,
                        data={
                            "event_type": event.event_type,
                            "severity": event.severity,
                            "message": event.message,
                        },
                        bot_type=event.bot_type,
                        bot_instance_id=event.bot_instance_id,
                    )
                )

        # Sort by timestamp descending and limit
        activities.sort(key=lambda x: x.timestamp, reverse=True)
        activities = activities[:limit]

        # Generate next cursor
        next_cursor = None
        if activities and len(activities) == limit:
            next_cursor = activities[-1].timestamp.isoformat()

        return activities, next_cursor


class ListOrdersUseCase:
    """List orders with filtering.

    Thin wrapper around repository - use case allows for future
    business logic (permissions, transformations) without modifying repository.
    """

    async def execute(
        self,
        bot_context: BotContext | None = None,
        status: str | None = None,
        symbol: Symbol | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Order]:
        """List orders with optional filtering.

        Args:
            bot_context: Optional bot context filter
            status: Optional status filter
            symbol: Optional symbol filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Order entities
        """
        return await list_orders(
            bot_context=bot_context,
            status=status,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )


class ListTrainingRunsUseCase:
    """List training runs with filtering."""

    async def execute(
        self,
        status: str | None = None,
        symbol: Symbol | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TrainingRun]:
        """List training runs with optional filtering.

        Args:
            status: Optional status filter
            symbol: Optional symbol filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of TrainingRun entities
        """
        return await list_training_runs(
            status=status,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )


class PruneGenomesUseCase:
    """Prune old genomes based on retention policy.

    Business logic for genome retention - coordinates pruning operation.
    """

    async def execute(
        self,
        retention_days: int = 30,
        keep_active: bool = True,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Execute genome pruning with retention policy.

        Args:
            retention_days: Number of days to retain genomes
            keep_active: Whether to keep the currently active genome
            dry_run: If True, return what would be pruned without deleting

        Returns:
            Dict with pruned_count, kept_count, pruned_ids
        """
        pruned_count, pruned_ids = await prune_genomes(
            retention_days=retention_days,
            keep_active=keep_active,
            dry_run=dry_run,
        )

        return {
            "pruned_count": pruned_count,
            "kept_count": 0,  # Would need additional query to calculate
            "pruned_ids": pruned_ids,
            "dry_run": dry_run,
        }


class GetVenueBalancesUseCase:
    """Get venue balances from exchange.

    Business logic for fetching and formatting venue balances.
    Groups balances by venue and adds metadata.
    """

    def __init__(self, adapter: IExchangeAdapter):
        self.adapter = adapter

    async def execute(self) -> list[dict[str, Any]]:
        """Fetch balances and format as venue groups.

        Returns:
            List of venue balance dicts with venue, balances, synced_at
        """
        fetch_use_case = FetchBalancesUseCase(self.adapter)
        balances = await fetch_use_case.execute()

        # Group by venue (for now using "default" as venue)
        venue_balances: dict[str, list[dict[str, Any]]] = {}
        for balance in balances:
            venue = "default"
            if venue not in venue_balances:
                venue_balances[venue] = []

            venue_balances[venue].append(
                {
                    "asset": balance.asset,
                    "free": balance.free,
                    "locked": balance.locked,
                    "total": balance.total,
                }
            )

        # Format response
        result = []
        synced_at = datetime.utcnow()
        for venue, items in venue_balances.items():
            result.append(
                {
                    "venue": venue,
                    "balances": items,
                    "synced_at": synced_at,
                }
            )

        return result


class GetMarketPricesUseCase:
    """Get market prices for multiple symbols.

    Business logic for fetching current prices from exchange.
    """

    def __init__(self, adapter: IExchangeAdapter):
        self.adapter = adapter

    async def execute(
        self,
        symbols: list[Symbol],
    ) -> list[dict[str, Any]]:
        """Fetch prices for multiple symbols.

        Args:
            symbols: List of symbols to fetch prices for

        Returns:
            List of price dicts with symbol, price, timestamp
        """
        prices = []
        for symbol in symbols:
            try:
                price_use_case = GetMarketDataUseCase(self.adapter)
                price = await price_use_case.execute(symbol)

                prices.append(
                    {
                        "symbol": symbol.value,
                        "price": price.amount,
                        "bid": None,  # Adapter doesn't provide bid/ask yet
                        "ask": None,
                        "volume_24h": None,  # Adapter doesn't provide volume yet
                        "timestamp": datetime.utcnow(),
                    }
                )
            except Exception:
                # Skip symbols that fail to fetch
                continue

        return prices
