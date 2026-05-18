"""Use cases for trading domain.

Use cases orchestrate business logic by calling services and repositories.
They contain no direct SQL or HTTP calls.
"""

from stonks_trading.domains.trading.entities import (
    CheckRiskResult,
    EvaluateSignalResult,
    ExecuteTradeResult,
    Position,
    RiskEvent,
    Trade,
)
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.repositories import (
    save_position,
    save_risk_event,
    save_trade,
)
from stonks_trading.domains.trading.services import (
    FeeCalculator,
    InstrumentMapper,
    RiskChecker,
)
from stonks_trading.domains.trading.value_objects import Money, Symbol


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
