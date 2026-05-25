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
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        session = TrainingSession(
            run_id=1,
            bot_context=bot_context,
            symbols=["BTC_USD"],
        )

        assert session.run_id == 1
        assert session.status == "running"
        assert session.generation == 0
        assert session.current_fitness == 0.0
        assert session.best_fitness == 0.0

    def test_session_with_progress(self) -> None:
        """Test session with progress."""
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        session = TrainingSession(
            run_id=1,
            bot_context=bot_context,
            symbols=["BTC_USD", "ETH_USD"],
            status="completed",
            generation=30,
            current_fitness=50.0,
            best_fitness=75.0,
        )

        assert session.status == "completed"
        assert session.generation == 30
        assert session.best_fitness == 75.0


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
        )

        assert result.improved is True
        assert result.improvement_pct == 5.0
        assert result.reason == ""

    def test_comparison_not_improved(self) -> None:
        """Test non-improved genome comparison."""
        result = GenomeComparisonResult(
            symbol="BTC_USD",
            new_genome_id=2,
            prev_genome_id=1,
            new_roi=8.0,
            prev_roi=10.0,
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
            status="pending",
            scheduled_at=datetime.utcnow(),
        )

        assert job.symbol == "BTC_USD"
        assert job.status == "pending"
        assert job.started_at is None
        assert job.completed_at is None

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
            completed_at=now,
        )

        assert job.status == "completed"
        assert job.started_at == now
        assert job.completed_at == now


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
