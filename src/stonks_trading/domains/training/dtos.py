"""Training domain DTOs.

Pydantic models for API request/response validation.
All responses inherit from BaseResponse.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from stonks_trading.shared.serializers import BaseResponse


class TrainingRunRequest(BaseModel):
    """Request to start a training run."""

    symbol: str = Field(..., min_length=1, max_length=20)
    generations: int = Field(default=30, ge=1, le=100)
    population_size: int = Field(default=150, ge=10, le=500)
    bot_type: str = Field(default="neat_swing", min_length=1, max_length=50)
    bot_instance_id: str = Field(default="default", min_length=1, max_length=100)


class TrainingRunResponse(BaseResponse):
    """Training run response."""

    id: int
    symbol: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    best_fitness: float | None = None
    best_roi_validation: float | None = None
    generations: int
    pop_size: int
    git_sha: str | None = None


class TrainingRunListResponse(BaseResponse):
    """List of training runs."""

    runs: list[TrainingRunResponse] = Field(default_factory=list)
    total: int = 0


class GenomeComparisonResponse(BaseResponse):
    """Genome comparison response."""

    improved: bool
    new_roi: float
    prev_roi: float
    improvement_pct: float
    new_genome_id: int
    prev_genome_id: int | None = None
    symbol: str
    reason: str


class RetrainingJobRequest(BaseModel):
    """Request to schedule a retraining job."""

    symbol: str = Field(..., min_length=1, max_length=20)
    bot_type: str = Field(..., min_length=1, max_length=50)
    bot_instance_id: str = Field(..., min_length=1, max_length=100)
    scheduled_at: datetime | None = None


class RetrainingJobResponse(BaseResponse):
    """Retraining job response."""

    symbol: str
    bot_type: str
    bot_instance_id: str
    status: str
    result: GenomeComparisonResponse | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class RetrainingSummaryResponse(BaseResponse):
    """Summary of daily retraining run."""

    runs_completed: int
    genomes_activated: int
    genomes_rejected: int
    details: list[dict[str, Any]] = Field(default_factory=list)


class GenerationMetricResponse(BaseResponse):
    """Generation metric response."""

    run_id: int
    generation: int
    best_fitness: float
    mean_fitness: float = 0.0
    worst_fitness: float = 0.0
    num_species: int = 0
    num_genomes: int = 0
    best_roi_validation: float | None = None
    stagnation_count: int | None = None
    num_trades_best: int | None = None
    max_drawdown_best: float | None = None


class GenerationMetricListResponse(BaseResponse):
    """List of generation metrics."""

    metrics: list[GenerationMetricResponse] = Field(default_factory=list)
    total: int = 0


class TrainingProgressResponse(BaseResponse):
    """Training progress response."""

    run_id: int
    symbol: str
    status: str
    current_generation: int = 0
    best_fitness_so_far: float = 0.0
    started_at: datetime


class CheckpointRetentionPolicyRequest(BaseModel):
    """Request to set checkpoint retention policy."""

    keep_every_nth: int = Field(default=5, ge=1, le=50)
    max_checkpoints: int = Field(default=20, ge=1, le=100)
    retain_best: bool = True
    retain_final: bool = True


class CheckpointCleanupResponse(BaseResponse):
    """Response from checkpoint cleanup."""

    run_id: int
    deleted_count: int
    retained_count: int
    retained_checkpoints: list[dict[str, Any]] = Field(default_factory=list)


class SchedulerJobRequest(BaseModel):
    """Request to schedule a daily retraining job."""

    bot_type: str = Field(..., min_length=1, max_length=50)
    bot_instance_id: str = Field(..., min_length=1, max_length=100)
    symbols: list[str] = Field(default_factory=list)
    hour: int = Field(default=0, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class SchedulerJobResponse(BaseResponse):
    """Scheduled job response."""

    job_id: str
    bot_type: str
    instance_id: str
    symbols: list[str]
    schedule: str
    status: str


class SchedulerJobListResponse(BaseResponse):
    """List of scheduled jobs."""

    jobs: list[SchedulerJobResponse] = Field(default_factory=list)
    total: int = 0


class TriggerRetrainingRequest(BaseModel):
    """Request to trigger immediate retraining."""

    bot_type: str = Field(..., min_length=1, max_length=50)
    bot_instance_id: str = Field(..., min_length=1, max_length=100)
    symbols: list[str] = Field(default_factory=list)


class TriggerRetrainingResponse(BaseResponse):
    """Immediate retraining response."""

    job_id: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    completed_at: datetime
