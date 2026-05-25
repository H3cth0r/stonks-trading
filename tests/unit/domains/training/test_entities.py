"""Tests for training domain entities."""

from datetime import datetime

import pytest

from stonks_trading.domains.training.entities import (
    TrainingSession,
    GenomeComparisonResult,
    RetrainingJob,
    CheckpointRetentionPolicy,
)
from stonks_trading.domains.trading.value_objects import BotContext, Symbol


class TestTrainingSession:
    """Tests for TrainingSession."""

    def test_default_session(self) -> None:
        """Test default training session creation."""
        session = TrainingSession(
            run_id=1,
            symbol="BTC_USD",
            status="running",
            started_at=datetime.utcnow(),
        )

        assert session.run_id == 1
        assert session.symbol == "BTC_USD"
        assert session.status == "running"
        assert session.current_generation == 0
        assert session.best_fitness_so_far == 0.0
        assert session.bot_type == "neat_swing"
        assert session.bot_instance_id == "default"

    def test_session_with_progress(self) -> None:
        """Test session with progress."""
        session = TrainingSession(
            run_id=1,
            symbol="BTC_USD",
            status="completed",
            started_at=datetime.utcnow(),
            current_generation=30,
            best_fitness_so_far=75.0,
            bot_type="neat_swing",
            bot_instance_id="test-001",
        )

        assert session.status == "completed"
        assert session.current_generation == 30
        assert session.best_fitness_so_far == 75.0


class TestGenomeComparisonResult:
    """Tests for GenomeComparisonResult."""

    def test_comparison_improved(self) -> None:
        """Test improved genome comparison."""
        result = GenomeComparisonResult(
            symbol="BTC_USD",
            new_genome_id=2,
            prev_genome_id=1,
            new_roi=15.0,
            prev_roi=10.0,
            improved=True,
            improvement_pct=5.0,
            reason="Significant improvement",
        )

        assert result.improved is True
        assert result.improvement_pct == 5.0

    def test_comparison_not_improved(self) -> None:
        """Test non-improved genome comparison."""
        result = GenomeComparisonResult(
            symbol="BTC_USD",
            new_genome_id=2,
            prev_genome_id=1,
            new_roi=8.0,
            prev_roi=10.0,
            improved=False,
            improvement_pct=-2.0,
            reason="No significant improvement",
        )

        assert result.improved is False
        assert result.improvement_pct == -2.0


class TestRetrainingJob:
    """Tests for RetrainingJob."""

    def test_default_job(self) -> None:
        """Test default retraining job."""
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        job = RetrainingJob(
            symbol="BTC_USD",
            bot_context=bot_context,
        )

        assert job.symbol == "BTC_USD"
        assert job.status == "pending"
        assert job.started_at is None
        assert job.finished_at is None
        assert job.result is None
        assert job.error_message is None

    def test_job_with_timing(self) -> None:
        """Test job with timing information."""
        now = datetime.utcnow()
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        job = RetrainingJob(
            symbol="BTC_USD",
            bot_context=bot_context,
            status="completed",
            scheduled_at=now,
            started_at=now,
            finished_at=now,
        )

        assert job.status == "completed"
        assert job.scheduled_at == now
        assert job.started_at == now
        assert job.finished_at == now


class TestCheckpointRetentionPolicy:
    """Tests for CheckpointRetentionPolicy."""

    def test_default_policy(self) -> None:
        """Test default retention policy."""
        policy = CheckpointRetentionPolicy()

        assert policy.keep_every_nth == 5
        assert policy.max_checkpoints == 20

    def test_custom_policy(self) -> None:
        """Test custom retention policy."""
        policy = CheckpointRetentionPolicy(
            keep_every_nth=10,
            max_checkpoints=50,
        )

        assert policy.keep_every_nth == 10
        assert policy.max_checkpoints == 50
