"""Tortoise ORM models for database persistence.

All models are in a single file as per Phase 1 requirements.
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
"""

from tortoise import fields
from tortoise.models import Model


class TradeModel(Model):
    """Executed trade record."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    side = fields.CharField(max_length=10)  # buy/sell
    fill_price = fields.FloatField()
    quantity = fields.FloatField()
    fee = fields.FloatField()
    fee_currency = fields.CharField(max_length=3, default="USD")
    realized_pnl = fields.FloatField(null=True)
    order_id = fields.CharField(max_length=64, null=True)
    venue_trade_id = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "trades"
        ordering = ["-created_at"]


class PositionModel(Model):
    """Open position record."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    quantity = fields.FloatField()
    entry_price = fields.FloatField(null=True)
    entry_price_currency = fields.CharField(max_length=3, default="USD")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "positions"


class GenomeModel(Model):
    """NEAT genome record."""

    id = fields.IntField(pk=True)
    genome_data = fields.BinaryField()  # Pickled genome
    fitness = fields.FloatField()
    generation = fields.IntField(default=0)
    symbol = fields.CharField(max_length=20, null=True)
    # Training parameters
    fee_rate = fields.FloatField(default=0.001)
    slippage_bps = fields.IntField(default=0)
    mode = fields.CharField(max_length=20, default="backtest")
    # Metadata
    created_at = fields.DatetimeField(auto_now_add=True)
    is_active = fields.BooleanField(default=False)
    trades_count = fields.IntField(default=0)
    max_drawdown = fields.FloatField(default=0.0)
    total_return = fields.FloatField(default=0.0)
    notes = fields.TextField(null=True)

    class Meta:
        table = "genomes"
        ordering = ["-created_at"]


class RiskEventModel(Model):
    """Risk event record for audit trail."""

    id = fields.IntField(pk=True)
    event_type = fields.CharField(max_length=50)
    severity = fields.CharField(max_length=20)  # warning, critical, emergency
    message = fields.TextField()
    symbol = fields.CharField(max_length=20, null=True)
    metric_name = fields.CharField(max_length=50, null=True)
    metric_value = fields.FloatField(null=True)
    threshold_value = fields.FloatField(null=True)
    portfolio_value = fields.FloatField(null=True)
    position_value = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    acknowledged_at = fields.DatetimeField(null=True)
    acknowledged_by = fields.CharField(max_length=100, null=True)
    action_taken = fields.TextField(null=True)

    class Meta:
        table = "risk_events"
        ordering = ["-created_at"]


class OrderModel(Model):
    """Order record."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    side = fields.CharField(max_length=10)
    order_type = fields.CharField(max_length=20)  # market, limit
    quantity = fields.FloatField()
    price = fields.FloatField(null=True)
    status = fields.CharField(max_length=20, default="pending")  # pending, filled, cancelled
    venue_order_id = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    filled_at = fields.DatetimeField(null=True)

    class Meta:
        table = "orders"
        ordering = ["-created_at"]


class BotDecisionModel(Model):
    """Bot decision log."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    genome_id = fields.IntField(null=True)
    buy_prob = fields.FloatField()
    sell_prob = fields.FloatField()
    decision = fields.CharField(max_length=10, null=True)  # buy, sell, hold
    executed = fields.BooleanField(default=False)
    trade_id = fields.IntField(null=True)
    timestamp = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "bot_decisions"
        ordering = ["-timestamp"]


class TrainingRunModel(Model):
    """Training session record."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    start_time = fields.DatetimeField(auto_now_add=True)
    end_time = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=20, default="running")  # running, completed, failed
    generations = fields.IntField(default=0)
    pop_size = fields.IntField(default=150)
    episode_steps = fields.IntField(default=20160)
    fee_rate = fields.FloatField(default=0.001)
    best_genome_id = fields.IntField(null=True)
    best_fitness = fields.FloatField(null=True)
    config_snapshot = fields.JSONField(null=True)

    class Meta:
        table = "training_runs"
        ordering = ["-start_time"]


class GenerationMetricModel(Model):
    """Per-generation training metrics."""

    id = fields.IntField(pk=True)
    training_run = fields.ForeignKeyField(
        "models.TrainingRunModel",
        related_name="metrics",
    )
    generation = fields.IntField()
    best_fitness = fields.FloatField()
    avg_fitness = fields.FloatField()
    worst_fitness = fields.FloatField()
    num_species = fields.IntField()
    num_genomes = fields.IntField()
    timestamp = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "generation_metrics"


class DataGapModel(Model):
    """Data availability gap record."""

    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=20)
    start_time = fields.DatetimeField()
    end_time = fields.DatetimeField()
    detected_at = fields.DatetimeField(auto_now_add=True)
    filled = fields.BooleanField(default=False)
    filled_at = fields.DatetimeField(null=True)

    class Meta:
        table = "data_gaps"
