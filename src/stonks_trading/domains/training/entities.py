"""Training domain entities - extends trading entities where possible.

Uses existing TrainingRun and GenerationMetric from trading.entities.
Defines training-specific entities here.

Entity rules (per architecture.md):
- Pure dataclasses with zero framework dependencies
- No imports from outer layers (routes, adapters, etc.)
- Only standard library and domain entity imports
"""

from dataclasses import dataclass
from datetime import datetime

from stonks_trading.domains.trading.value_objects import BotContext


@dataclass
class TrainingSession:
    """Active training session - ephemeral, not persisted.

    Tracks an in-progress training run for monitoring purposes.
    This is not stored in the database - it's kept in memory
    during training operations.
    """

    run_id: int
    symbol: str
    status: str  # running, completed, failed
    started_at: datetime
    current_generation: int = 0
    best_fitness_so_far: float = 0.0
    bot_type: str = "neat_swing"
    bot_instance_id: str = "default"

    def is_active(self) -> bool:
        """Check if session is still running."""
        return self.status == "running"


@dataclass
class GenomeComparisonResult:
    """Result of comparing two genomes.

    Used to decide whether to swap to a new genome after training.
    """

    improved: bool
    new_roi: float
    prev_roi: float
    improvement_pct: float
    new_genome_id: int
    prev_genome_id: int | None
    symbol: str
    reason: str  # Why decision was made

    def is_significant_improvement(self, threshold: float = 0.5) -> bool:
        """Check if improvement exceeds threshold percentage."""
        return self.improved and self.improvement_pct >= threshold


@dataclass
class RetrainingJob:
    """A single retraining job for a symbol.

    Represents a scheduled or in-progress retraining task
    for a specific bot context and symbol.
    """

    symbol: str
    bot_context: BotContext
    status: str = "pending"  # pending, running, completed, failed
    result: GenomeComparisonResult | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    def is_pending(self) -> bool:
        """Check if job is pending."""
        return self.status == "pending"

    def is_completed(self) -> bool:
        """Check if job completed successfully."""
        return self.status == "completed"

    def is_failed(self) -> bool:
        """Check if job failed."""
        return self.status == "failed"


@dataclass
class CheckpointRetentionPolicy:
    """Configuration for checkpoint retention thinning.

    Controls how many checkpoints are kept during training.
    """

    keep_every_nth: int = 5  # Keep every 5th generation
    max_checkpoints: int = 20  # Maximum checkpoints to retain
    retain_best: bool = True  # Always retain best genome checkpoint
    retain_final: bool = True  # Always retain final generation

    def should_retain(self, generation: int, is_best: bool = False) -> bool:
        """Determine if checkpoint should be retained."""
        if self.retain_final and generation == -1:
            return True
        if self.retain_best and is_best:
            return True
        return generation % self.keep_every_nth == 0


@dataclass
class TrainingJob:
    """Training job entity for Worker-delegated training.

    Represents an async training job tracked via Redis.
    This is ephemeral - not persisted to database.
    """

    job_id: str
    symbol: str
    status: str  # running, completed, failed, stopped, queued
    generations_total: int
    generations_completed: int = 0
    best_fitness: float | None = None
    best_roi: float | None = None
    progress_pct: float = 0.0
    checkpoint_dir: str | None = None
    started_at: datetime | None = None
    error: str | None = None
    checkpoints: list[dict] = None

    def __post_init__(self):
        if self.checkpoints is None:
            self.checkpoints = []

    def is_running(self) -> bool:
        return self.status == "running"

    def is_completed(self) -> bool:
        return self.status == "completed"

    def is_failed(self) -> bool:
        return self.status == "failed"


@dataclass
class StartTrainingRequest:
    """Request to start training job (sent to Worker)."""

    symbol: str
    generations: int
    population_size: int
    training_capital: float
    checkpoint_interval: int
    strategy_type: str = "neat_swing"
    csv_path: str | None = None


@dataclass
class StartTrainingResponse:
    """Response from starting training job."""

    job_id: str
    status: str
    started_at: datetime
