"""Training domain for NEAT genome retraining and management.

This domain handles:
- Daily retraining pipeline orchestration
- Genome validation and comparison
- Hot-swap activation when improved
- Checkpoint retention management
- Discord notifications for training results

Architecture: CLEAN with standalone repository functions.
"""

from stonks_trading.domains.training.entities import (
    GenomeComparisonResult,
    RetrainingJob,
    TrainingSession,
)
from stonks_trading.domains.training.use_cases import DailyRetrainingUseCase, TrainGenomeUseCase

__all__ = [
    "GenomeComparisonResult",
    "RetrainingJob",
    "TrainingSession",
    "DailyRetrainingUseCase",
    "TrainGenomeUseCase",
]
