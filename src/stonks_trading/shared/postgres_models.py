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

    class Meta:
        table = "trades"
        indexes = (("symbol", "created_at"), ("mode", "created_at"))


# =============================================================================
# Position Model
# =============================================================================


class PositionModel(Model):
    """Current position state."""

    id = fields.BigIntField(pk=True)
    symbol = fields.CharField(max_length=20, unique=True)
    quantity = fields.FloatField(default=0.0)
    entry_price = fields.FloatField(null=True)
    current_price = fields.FloatField(null=True)
    unrealized_pnl = fields.FloatField(default=0.0)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "positions"


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

    class Meta:
        table = "genomes"
        indexes = (("symbol", "is_active"), ("symbol", "trained_at"))


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

    class Meta:
        table = "orders"


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

    class Meta:
        table = "bot_decisions"
        indexes = (("symbol", "candle_close_at"),)


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
    best_fitness = fields.FloatField()
    best_roi_validation = fields.FloatField(null=True)
    best_roi_test = fields.FloatField(null=True)
    episode_steps = fields.IntField(default=20160)
    pop_size = fields.IntField(default=150)
    fee_rate = fields.FloatField(default=0.001)
    started_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=20, default="running", index=True)

    class Meta:
        table = "training_runs"


# =============================================================================
# Generation Metric Model
# =============================================================================


class GenerationMetricModel(Model):
    """Per-generation metrics during training."""

    id = fields.BigIntField(pk=True)
    run = fields.ForeignKeyField("models.TrainingRunModel", related_name="metrics")
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

    class Meta:
        table = "risk_events"


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
    value = fields.JSONField()
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "system_config"