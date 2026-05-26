"""Tortoise ORM models for database persistence.

All models in ONE file as per Phase 3 requirements.
Models are thin: fields only, no business logic.

Models:
    - TradeModel: Executed trades
    - PositionModel: Open positions
    - GenomeModel: NEAT genomes
    - RiskEventModel: Risk events
    - OrderModel: Orders (pending/filled/cancelled)
    - BotDecisionModel: Bot decision log
    - TrainingRunModel: Training session records
    - GenerationMetricModel: Per-generation metrics
    - DataGapModel: Data availability gaps
    - SystemConfigModel: System configuration key-value store
"""

from enum import Enum

from tortoise import fields
from tortoise.models import Model

from stonks_trading.domains.trading.enums import BotStatus


class TradeSide(str, Enum):
    """Trade side enum for CharEnumField."""

    BUY = "buy"
    SELL = "sell"


class TradingMode(str, Enum):
    """Trading mode enum for CharEnumField."""

    BACKTEST = "backtest"
    DRY_RUN = "dry_run"
    LIVE = "live"


# =============================================================================
# Trade Model
# =============================================================================


class TradeModel(Model):
    """Executed trade record with full Phase 3 schema."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    side = fields.CharEnumField(TradeSide)
    intended_price = fields.FloatField(null=True)
    fill_price = fields.FloatField()
    slippage_bps = fields.FloatField(default=0.0)
    quantity = fields.FloatField()
    quote_quantity = fields.FloatField(default=0.0)
    fee = fields.FloatField()
    fee_currency = fields.CharField(max_length=10, default="USDT")
    fee_rate = fields.FloatField(default=0.001)
    order_id = fields.CharField(max_length=100, unique=True, null=True)
    exchange = fields.CharField(max_length=20, default="binance")
    strategy = fields.CharField(max_length=50, default="NEAT_v1")
    mode = fields.CharEnumField(TradingMode, default=TradingMode.DRY_RUN)
    genome_id = fields.CharField(max_length=100, null=True)
    realized_pnl = fields.FloatField(null=True)
    entry_price = fields.FloatField(null=True)
    latency_ms = fields.FloatField(default=0.0)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    # Phase 5: Bot context fields
    bot_type = fields.CharField(max_length=50, index=True, default="neat_swing")
    bot_instance_id = fields.CharField(max_length=100, index=True, default="default")

    class Meta:
        table = "trades"
        indexes = (
            ("symbol", "created_at"),
            ("mode", "created_at"),
            ("bot_type", "bot_instance_id"),
            ("bot_type", "bot_instance_id", "symbol"),
        )


# =============================================================================
# Position Model
# =============================================================================


class PositionModel(Model):
    """Current position state with bot context."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)  # Removed unique=True for multi-bot
    quantity = fields.FloatField(default=0.0)
    entry_price = fields.FloatField(null=True)
    current_price = fields.FloatField(null=True)
    unrealized_pnl = fields.FloatField(default=0.0)
    updated_at = fields.DatetimeField(auto_now=True)
    # Phase 5: Bot context fields
    bot_type = fields.CharField(max_length=50, index=True, default="neat_swing")
    bot_instance_id = fields.CharField(max_length=100, index=True, default="default")

    class Meta:
        table = "positions"
        unique_together = (("bot_type", "bot_instance_id", "symbol"),)
        indexes = (("bot_type", "bot_instance_id", "symbol"),)


# =============================================================================
# Genome Model
# =============================================================================


class GenomeModel(Model):
    """NEAT genome metadata and storage."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    genome_data = fields.BinaryField(null=True)
    model_family = fields.CharField(max_length=50, default="NEAT_RNN_V1")
    artifact_uri = fields.CharField(max_length=500, null=True)
    trainer_git_sha = fields.CharField(max_length=40, null=True)
    feature_schema_id = fields.CharField(max_length=64, null=True)
    is_active = fields.BooleanField(default=False, index=True)
    roi_validation = fields.FloatField(null=True)
    roi_test = fields.FloatField(null=True)
    max_drawdown = fields.FloatField(null=True)
    num_trades = fields.IntField(null=True)
    total_return = fields.FloatField(null=True)
    fitness_score = fields.FloatField(null=True)
    fee_rate_used = fields.FloatField(default=0.001)
    trained_at = fields.DatetimeField()
    activated_at = fields.DatetimeField(null=True)
    deactivated_at = fields.DatetimeField(null=True)
    # Phase 5: Bot activation context (null if not bot-specific)
    active_for_bot_type = fields.CharField(max_length=50, index=True, null=True)
    active_for_instance_id = fields.CharField(max_length=100, index=True, null=True)

    class Meta:
        table = "genomes"
        indexes = (
            ("symbol", "is_active"),
            ("symbol", "trained_at"),
            ("active_for_bot_type", "active_for_instance_id", "is_active"),
        )


# =============================================================================
# Order Model
# =============================================================================


class OrderModel(Model):
    """Venue order lifecycle."""

    id = fields.BigIntField(pk=True)
    client_order_id = fields.CharField(max_length=100, null=True, index=True)
    venue_order_id = fields.CharField(max_length=100, null=True, index=True)
    symbol = fields.CharField(max_length=20, index=True)
    side = fields.CharEnumField(TradeSide)
    status = fields.CharField(max_length=30, index=True)
    requested_qty = fields.FloatField()
    filled_qty = fields.FloatField(default=0.0)
    avg_fill_price = fields.FloatField(null=True)
    mode = fields.CharEnumField(TradingMode, default=TradingMode.DRY_RUN)
    genome_id = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True)
    # Phase 5: Bot context fields
    bot_type = fields.CharField(max_length=50, index=True, default="neat_swing")
    bot_instance_id = fields.CharField(max_length=100, index=True, default="default")

    class Meta:
        table = "orders"
        indexes = (("bot_type", "bot_instance_id"),)


# =============================================================================
# Bot Decision Model
# =============================================================================


class BotDecisionModel(Model):
    """One row per symbol per closed 1m candle — observability only."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    genome_id = fields.CharField(max_length=100, null=True)
    buy_prob = fields.FloatField()
    sell_prob = fields.FloatField()
    action = fields.CharField(max_length=20)  # "buy", "sell", "hold"
    reason = fields.CharField(max_length=200, null=True)
    mode = fields.CharEnumField(TradingMode, default=TradingMode.DRY_RUN)
    candle_close_at = fields.DatetimeField(index=True)
    executed = fields.BooleanField(default=False)
    trade_id = fields.BigIntField(null=True)
    # Phase 5: Bot context fields
    bot_type = fields.CharField(max_length=50, index=True, default="neat_swing")
    bot_instance_id = fields.CharField(max_length=100, index=True, default="default")

    class Meta:
        table = "bot_decisions"
        indexes = (
            ("symbol", "candle_close_at"),
            ("bot_type", "bot_instance_id"),
            ("bot_type", "bot_instance_id", "symbol", "candle_close_at"),
        )


# =============================================================================
# Training Run Model
# =============================================================================


class TrainingRunModel(Model):
    """Training run metadata."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    model_family = fields.CharField(max_length=50, default="NEAT_RNN_V1")
    artifact_prefix_uri = fields.CharField(max_length=500, null=True)
    trainer_git_sha = fields.CharField(max_length=40, null=True)
    generations = fields.IntField()
    best_fitness = fields.FloatField(null=True)
    best_roi_validation = fields.FloatField(null=True)
    best_roi_test = fields.FloatField(null=True)
    episode_steps = fields.IntField(default=20160)
    pop_size = fields.IntField(default=150)
    fee_rate = fields.FloatField(default=0.001)
    started_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=20, default="running", index=True)
    config_snapshot = fields.JSONField(null=True)  # NEAT config for reproducibility

    class Meta:
        table = "training_runs"


# =============================================================================
# Generation Metric Model
# =============================================================================


class GenerationMetricModel(Model):
    """Per-generation metrics during training."""

    id = fields.BigIntField(pk=True)
    run = fields.ForeignKeyField("models.TrainingRunModel", related_name="metrics")  # type: ignore[var-annotated]
    generation = fields.IntField()
    best_fitness = fields.FloatField()
    mean_fitness = fields.FloatField()
    worst_fitness = fields.FloatField(null=True)
    num_species = fields.IntField(null=True)
    num_genomes = fields.IntField(null=True)
    best_roi_validation = fields.FloatField(null=True)
    stagnation_count = fields.IntField(null=True)
    num_trades_best = fields.IntField(null=True)
    max_drawdown_best = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "generation_metrics"
        indexes = (("run_id", "generation"),)


# =============================================================================
# Risk Event Model
# =============================================================================


class RiskEventModel(Model):
    """Risk limit breaches and warnings."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    event_type = fields.CharField(max_length=50, index=True)
    severity = fields.CharField(max_length=20, default="warning")
    value = fields.FloatField()
    threshold = fields.FloatField()
    message = fields.TextField()
    notified = fields.BooleanField(default=False)
    mode = fields.CharEnumField(TradingMode, default=TradingMode.DRY_RUN)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    acknowledged_at = fields.DatetimeField(null=True)
    acknowledged_by = fields.CharField(max_length=100, null=True)
    action_taken = fields.TextField(null=True)
    portfolio_value = fields.FloatField(null=True)
    position_value = fields.FloatField(null=True)
    metric_name = fields.CharField(max_length=50, null=True)
    metric_value = fields.FloatField(null=True)
    # Phase 5: Bot context fields (null=True for system-level events)
    bot_type = fields.CharField(max_length=50, index=True, default="neat_swing")
    bot_instance_id = fields.CharField(max_length=100, index=True, null=True, default="default")

    class Meta:
        table = "risk_events"
        indexes = (("bot_type", "bot_instance_id"),)


# =============================================================================
# Data Gap Model
# =============================================================================


class DataGapModel(Model):
    """Data ingestion gaps detected."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, index=True)
    gap_start = fields.DatetimeField()
    gap_end = fields.DatetimeField(null=True)
    gap_type = fields.CharField(max_length=20, default="ws_disconnect")
    backfilled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    filled_at = fields.DatetimeField(null=True)

    class Meta:
        table = "data_gaps"


# =============================================================================
# System Config Model
# =============================================================================


class SystemConfigModel(Model):
    """System configuration key-value store."""

    id = fields.BigIntField(pk=True)
    key = fields.CharField(max_length=100, unique=True)
    value = fields.JSONField()  # type: ignore[var-annotated]
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "system_config"


# =============================================================================
# Bot Instance Model (Phase 5)
# =============================================================================


class BotInstanceModel(Model):
    """Bot instance registry for multi-bot architecture."""

    id = fields.BigIntField(pk=True)
    bot_type = fields.CharField(max_length=50, index=True)
    instance_id = fields.CharField(max_length=100, unique=True)
    symbols = fields.JSONField()  # type: ignore[var-annotated]
    mode = fields.CharField(max_length=20)
    status = fields.CharEnumField(BotStatus, default=BotStatus.STOPPED)
    config = fields.JSONField(null=True)  # type: ignore[var-annotated]
    last_seen_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "bot_instances"
        indexes = (("bot_type", "status"),)


# =============================================================================
# Bot State Model (Phase 5)
# =============================================================================


class BotStateModel(Model):
    """Bot state persistence for crash recovery."""

    id = fields.BigIntField(pk=True)
    bot_type = fields.CharField(max_length=50, index=True)
    bot_instance_id = fields.CharField(max_length=100, index=True)
    state_json = fields.JSONField()  # type: ignore[var-annotated]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "bot_states"
        indexes = (("bot_type", "bot_instance_id"),)


# =============================================================================
# Bot Heartbeat Model (Phase 9A)
# =============================================================================


class BotHeartbeatModel(Model):
    """Bot heartbeat for health monitoring."""

    id = fields.BigIntField(pk=True)
    bot_type = fields.CharField(max_length=50, index=True)
    bot_instance_id = fields.CharField(max_length=100, index=True)
    timestamp = fields.DatetimeField(auto_now_add=True, index=True)
    state_hash = fields.CharField(max_length=64, null=True)
    candle_timestamp = fields.DatetimeField(null=True)

    class Meta:
        table = "bot_heartbeats"
        indexes = (("bot_type", "bot_instance_id", "timestamp"),)


# =============================================================================
# Reconciliation Report Model (Phase 9C)
# =============================================================================


class ReconciliationReportModel(Model):
    """Reconciliation report for venue trade matching."""

    id = fields.BigIntField(pk=True)
    run_id = fields.CharField(max_length=100, unique=True)
    venue = fields.CharField(max_length=20)
    symbol = fields.CharField(max_length=20, index=True)
    start_time = fields.DatetimeField()
    end_time = fields.DatetimeField()
    total_internal = fields.IntField(default=0)
    total_venue = fields.IntField(default=0)
    matched = fields.IntField(default=0)
    mismatches = fields.IntField(default=0)
    missing_internal = fields.IntField(default=0)
    missing_venue = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "reconciliation_reports"
        indexes = (("venue", "created_at"), ("symbol", "created_at"))


# =============================================================================
# Reconciliation Diff Model (Phase 9C)
# =============================================================================


class ReconciliationDiffModel(Model):
    """Individual differences found during reconciliation."""

    id = fields.BigIntField(pk=True)
    report = fields.ForeignKeyField(
        "models.ReconciliationReportModel",
        related_name="diffs",
    )
    status = fields.CharField(max_length=20)  # matched, mismatch, missing_internal, missing_venue
    internal_trade_id = fields.BigIntField(null=True, index=True)
    venue_trade_id = fields.CharField(max_length=100, null=True, index=True)
    field_differences = fields.JSONField(null=True)
    symbol = fields.CharField(max_length=20, null=True)
    side = fields.CharField(max_length=10, null=True)
    internal_price = fields.FloatField(null=True)
    venue_price = fields.FloatField(null=True)
    internal_quantity = fields.FloatField(null=True)
    venue_quantity = fields.FloatField(null=True)
    internal_timestamp = fields.DatetimeField(null=True)
    venue_timestamp = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "reconciliation_diffs"
        indexes = (("report_id", "status"),)


# =============================================================================
# Bot Process Model (Phase 9F)
# =============================================================================


class BotProcessModel(Model):
    """Bot process lifecycle for API-driven bot control.

    Tracks the state of bot processes managed via the Bot Control domain.
    Enables starting, stopping, and monitoring bot instances through the API.
    """

    id = fields.BigIntField(pk=True)
    bot_type = fields.CharField(max_length=50, index=True)
    bot_instance_id = fields.CharField(max_length=100, index=True)
    mode = fields.CharField(max_length=20)
    symbols = fields.JSONField(default=list)
    pid = fields.IntField(null=True)
    status = fields.CharField(
        max_length=20, index=True
    )  # registered, starting, running, stopping, stopped, error
    started_at = fields.DatetimeField(null=True)
    stopped_at = fields.DatetimeField(null=True)
    exit_code = fields.IntField(null=True)
    error_message = fields.TextField(null=True)
    config_path = fields.CharField(max_length=255, default="config-neat.txt")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "bot_processes"
        indexes = (
            ("bot_type", "bot_instance_id"),
            ("status", "updated_at"),
        )
