"""Domain entities for trading domain.

Entities are pure dataclasses with zero framework dependencies.
They represent core business objects with identity and behavior.

Key principle: Domain entities have no imports from outer layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stonks_trading.domains.trading.enums import RiskLevel, Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol


@dataclass
class ExecuteTradeResult:
    """Result of trade execution.

    Domain entity representing the outcome of executing a trade.
    Returned by ExecuteTradeUseCase.
    """

    success: bool
    trade: Trade | None = None
    position: Position | None = None
    risk_check: RiskCheckResult | None = None
    error: str | None = None


@dataclass
class Signal:
    """Trading signal from strategy.

    Domain entity representing a buy/sell signal with confidence.
    Returned by strategy.generate_signal().
    """

    action: Side
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluateSignalResult:
    """Result of signal evaluation.

    Domain entity representing the outcome of evaluating a NEAT signal.
    Returned by EvaluateSignalUseCase.
    """

    action: Side | None
    confidence: float
    should_trade: bool
    reason: str | None = None


@dataclass
class CheckRiskResult:
    """Result of risk monitoring check.

    Domain entity representing the outcome of a risk check.
    Returned by MonitorRiskUseCase.
    """

    status: RiskLevel
    events: list[RiskEvent]
    should_halt: bool


@dataclass
class OrderResult:
    """Result of order execution.

    Represents the outcome of placing an order through an exchange.
    Domain entity that is returned by adapters and processed by use cases.
    """

    success: bool
    order_id: str | None = None
    fill_price: Money | None = None
    filled_quantity: float = 0.0
    fee: Money | None = None
    error: str | None = None
    timestamp: datetime | None = None


@dataclass
class Balance:
    """Account balance for an asset.

    Represents cash or asset holdings from an exchange account.
    Domain entity used by adapters and use cases.
    """

    asset: str
    free: float
    locked: float
    total: float


@dataclass
class RiskCheckResult:
    """Result of risk check.

    Pure dataclass representing the outcome of a risk validation.
    Used by RiskChecker service and returned to use cases.
    """

    allowed: bool
    reason: str | None = None
    risk_level: RiskLevel = RiskLevel.OK


@dataclass
class Trade:
    """Trade entity - pure dataclass with zero framework dependencies.

    Represents a completed trade execution with all relevant
    details for P&L calculation and tax reporting.

    Note:
        - unrealized_pnl_pct is for NEAT state vector (matches NEAT/main.py)
        - realized_pnl is ONLY for tax/SAT export, NOT trading logic
    """

    symbol: Symbol
    side: Side
    fill_price: Money
    quantity: float
    fee: Money
    # Tax only, not NEAT
    realized_pnl: Money | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    order_id: str | None = None
    venue_trade_id: str | None = None
    # Phase 3 expanded fields
    intended_price: Money | None = None
    slippage_bps: float = 0.0
    quote_quantity: float = 0.0
    fee_rate: float = 0.001
    fee_currency: str = "USDT"
    mode: TradingMode = TradingMode.DRY_RUN
    genome_id: str | None = None
    entry_price: Money | None = None
    latency_ms: float = 0.0
    exchange: str = "binance"
    strategy: str = "NEAT_v1"
    # Phase 5: Bot context fields with defaults for backward compatibility
    bot_type: str = "neat_swing"
    bot_instance_id: str = "default"

    def calculate_value(self) -> Money:
        """Calculate total value of trade (price * quantity)."""
        return Money(
            amount=self.fill_price.amount * self.quantity,
            currency=self.fill_price.currency,
        )

    def calculate_cost_basis(self) -> Money:
        """Calculate cost basis including fees."""
        value = self.calculate_value()
        if self.side == Side.BUY:
            return value + self.fee
        return value - self.fee

    def get_notional(self) -> Money:
        """Get notional value (price * quantity)."""
        return self.calculate_value()


@dataclass
class Position:
    """Position entity representing current holdings.

    Tracks open position state including entry price,
    quantity, and unrealized P&L for NEAT state vector.
    """

    symbol: Symbol
    quantity: float = 0.0
    entry_price: Money | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    # Phase 3 expanded fields
    current_price: Money | None = None
    unrealized_pnl: float = 0.0
    # Phase 5: Bot context fields with defaults for backward compatibility
    bot_type: str = "neat_swing"
    bot_instance_id: str = "default"

    def is_open(self) -> bool:
        """Check if position has non-zero quantity."""
        return self.quantity > 0

    def calculate_unrealized_pnl(self, current_price: Money) -> Money:
        """Calculate unrealized P&L at current price."""
        if not self.is_open() or self.entry_price is None:
            return Money(amount=0.0, currency=current_price.currency)

        price_diff = current_price.amount - self.entry_price.amount
        return Money(
            amount=price_diff * self.quantity,
            currency=current_price.currency,
        )

    def calculate_unrealized_pnl_pct(self, current_price: Money) -> float:
        """Calculate unrealized P&L percentage for NEAT state vector.

        This matches the calculation in NEAT/main.py line 122:
        unrealized_pnl = (price - entry_price) / entry_price
        """
        if not self.is_open() or self.entry_price is None:
            return 0.0

        if self.entry_price.amount == 0:
            return 0.0

        return (current_price.amount - self.entry_price.amount) / self.entry_price.amount

    def calculate_market_value(self, current_price: Money) -> Money:
        """Calculate current market value of position."""
        return Money(
            amount=self.quantity * current_price.amount,
            currency=current_price.currency,
        )

    def add_to_position(self, quantity: float, price: Money) -> None:
        """Add to existing position with average price update."""
        if self.quantity == 0:
            self.entry_price = price
            self.quantity = quantity
        else:
            # Calculate new average entry price
            current_value = self.quantity * (self.entry_price.amount if self.entry_price else 0)
            new_value = quantity * price.amount
            total_quantity = self.quantity + quantity
            avg_price = (current_value + new_value) / total_quantity

            self.entry_price = Money(amount=avg_price, currency=price.currency)
            self.quantity = total_quantity

        self.updated_at = datetime.utcnow()

    def reduce_position(self, quantity: float) -> None:
        """Reduce position by quantity."""
        if quantity >= self.quantity:
            self.quantity = 0.0
            self.entry_price = None
        else:
            self.quantity -= quantity

        self.updated_at = datetime.utcnow()


@dataclass
class Genome:
    """NEAT genome entity for persistence and retrieval.

    Stores a trained NEAT genome with its metadata
    for reproduction and continued training.
    """

    genome_data: bytes  # Pickled genome object
    id: int | None = None
    fitness: float = 0.0
    generation: int = 0
    symbol: Symbol | None = None
    # Training parameters used (must match NEAT/main.py for parity)
    fee_rate: float = 0.001
    slippage_bps: int = 0
    mode: str = "backtest"  # backtest, dry_run, live
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = False
    trades_count: int = 0
    max_drawdown: float = 0.0
    total_return: float = 0.0
    notes: str | None = None
    # Phase 3 expanded fields
    model_family: str = "NEAT_RNN_V1"
    artifact_uri: str | None = None
    trainer_git_sha: str | None = None
    feature_schema_id: str | None = None
    roi_validation: float | None = None
    roi_test: float | None = None
    fee_rate_used: float = 0.001
    trained_at: datetime | None = None
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    # Phase 5: Bot activation context (null if not bot-specific)
    active_for_bot_type: str | None = None
    active_for_instance_id: str | None = None

    def get_config_summary(self) -> dict[str, Any]:
        """Get training configuration summary for display."""
        return {
            "fee_rate": self.fee_rate,
            "slippage_bps": self.slippage_bps,
            "mode": self.mode,
            "fitness": self.fitness,
            "generation": self.generation,
        }


@dataclass
class RiskEvent:
    """Risk event entity for audit trail and notifications.

    Tracks risk-related events like drawdown breaches,
    limit violations, and kill switch triggers.
    """

    event_type: str  # drawdown_breach, trade_limit, kill_switch, etc.
    severity: str  # warning, critical, emergency
    message: str
    id: int | None = None
    symbol: Symbol | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    threshold_value: float | None = None
    # Phase 3 fields
    value: float = 0.0
    threshold: float = 0.0
    notified: bool = False
    mode: TradingMode = TradingMode.DRY_RUN
    # Context
    portfolio_value: Money | None = None
    position_value: Money | None = None
    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    action_taken: str | None = None
    # Phase 5: Bot context fields (null for system-level events)
    bot_type: str = "neat_swing"
    bot_instance_id: str | None = None

    def acknowledge(self, user: str, action: str | None = None) -> None:
        """Mark risk event as acknowledged."""
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = user
        self.action_taken = action


@dataclass
class Order:
    """Order entity for venue order lifecycle tracking.

    Represents a placed order through its lifecycle:
    pending -> filled/cancelled/rejected.
    """

    symbol: Symbol
    side: Side
    quantity: float
    price: Money | None = None
    id: int | None = None
    order_type: str = "market"  # market, limit
    status: str = "pending"  # pending, filled, cancelled, rejected
    client_order_id: str | None = None
    venue_order_id: str | None = None
    filled_quantity: float = 0.0
    avg_fill_price: Money | None = None
    mode: TradingMode = TradingMode.DRY_RUN
    genome_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None
    # Phase 5: Bot context fields with defaults for backward compatibility
    bot_type: str = "neat_swing"
    bot_instance_id: str = "default"

    def is_open(self) -> bool:
        """Check if order is still pending."""
        return self.status == "pending"

    def is_filled(self) -> bool:
        """Check if order is filled."""
        return self.status == "filled"


@dataclass
class BotDecision:
    """Bot decision record for observability.

    One row per symbol per closed 1m candle —
    logs NEAT output and the action taken.
    """

    symbol: Symbol
    buy_prob: float
    sell_prob: float
    action: str | None = None  # buy, sell, hold
    id: int | None = None
    genome_id: str | None = None
    reason: str | None = None
    mode: TradingMode = TradingMode.DRY_RUN
    candle_close_at: datetime = field(default_factory=datetime.utcnow)
    executed: bool = False
    trade_id: int | None = None
    # Phase 5: Bot context fields with defaults for backward compatibility
    bot_type: str = "neat_swing"
    bot_instance_id: str = "default"


@dataclass
class TrainingRun:
    """Training run entity for NEAT training sessions.

    Tracks metadata for a complete training session.
    """

    symbol: Symbol | None = None
    id: int | None = None
    model_family: str = "NEAT_RNN_V1"
    artifact_prefix_uri: str | None = None
    trainer_git_sha: str | None = None
    generations: int = 0
    best_fitness: float = 0.0
    best_roi_validation: float | None = None
    best_roi_test: float | None = None
    episode_steps: int = 20160
    pop_size: int = 150
    fee_rate: float = 0.001
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    status: str = "running"  # running, completed, failed
    config_snapshot: dict[str, Any] | None = None


@dataclass
class GenerationMetric:
    """Per-generation training metrics entity.

    Captures fitness and diversity metrics at each
    generation during a training run.
    """

    run_id: int
    generation: int
    best_fitness: float
    mean_fitness: float = 0.0
    id: int | None = None
    # Extended metrics
    worst_fitness: float = 0.0
    num_species: int = 0
    num_genomes: int = 0
    best_roi_validation: float | None = None
    stagnation_count: int | None = None
    num_trades_best: int | None = None
    max_drawdown_best: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DataGap:
    """Data availability gap entity.

    Tracks detected gaps in market data ingestion.
    """

    symbol: Symbol
    gap_start: datetime
    id: int | None = None
    gap_end: datetime | None = None
    gap_type: str = "ws_disconnect"  # ws_disconnect, rest_gap, malformed
    backfilled: bool = False
    detected_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None

    def is_filled(self) -> bool:
        """Check if gap has been backfilled."""
        return self.backfilled and self.filled_at is not None


@dataclass
class SystemConfig:
    """System configuration key-value store.

    Used for runtime configuration management.
    """

    key: str
    value: Any
    id: int | None = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_kv(cls, key: str, value: Any) -> SystemConfig:
        """Create from key-value pair."""
        return cls(key=key, value=value)


@dataclass
class MarketData:
    """Market data entity for a single candle/bar.

    Immutable representation of OHLCV data.
    """

    symbol: Symbol
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # Optional features (pre-computed)
    trend_1h: float | None = None
    rsi_1h: float | None = None
    rsi_15m: float | None = None
    roc: float | None = None
    bb_width: float | None = None

    def get_ohlcv(self) -> tuple[float, float, float, float, float]:
        """Return OHLCV tuple."""
        return (self.open, self.high, self.low, self.close, self.volume)

    def price_range(self) -> float:
        """Calculate price range (high - low)."""
        return self.high - self.low

    def is_bullish(self) -> bool:
        """Check if close > open (bullish candle)."""
        return self.close > self.open

    def is_bearish(self) -> bool:
        """Check if close < open (bearish candle)."""
        return self.close < self.open


@dataclass
class BotInstance:
    """Bot instance entity for multi-bot registry.

    Tracks registered bot instances with their configuration
    and current status.
    """

    bot_type: str
    instance_id: str
    symbols: list[str]
    mode: TradingMode
    id: int | None = None
    status: str = "stopped"  # running, stopped, paused, error
    config: dict[str, Any] | None = None
    last_seen_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_active(self) -> bool:
        """Check if bot is in active state."""
        return self.status == "running"


@dataclass
class BotState:
    """Bot state entity for crash recovery.

    Persists bot runtime state for recovery after restart.
    """

    bot_type: str
    bot_instance_id: str
    state_json: dict[str, Any]
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
