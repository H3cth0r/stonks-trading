"""Tests for training scheduler integration."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.training.scheduler_integration import (
    ScheduledJobConfig,
    TrainingScheduler,
    BotSchedulerLifecycle,
)
from stonks_trading.domains.trading.value_objects import BotContext


class TestScheduledJobConfig:
    """Tests for ScheduledJobConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        config = ScheduledJobConfig(
            bot_context=bot_context,
            symbols=["BTC_USD"],
        )

        assert config.hour == 0  # Midnight UTC
        assert config.minute == 0
        assert config.generations == 30
        assert config.population_size == 150
        assert config.improvement_threshold == 0.5

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        config = ScheduledJobConfig(
            bot_context=bot_context,
            symbols=["BTC_USD", "ETH_USD"],
            hour=6,
            minute=30,
            generations=50,
            population_size=200,
            improvement_threshold=1.0,
        )

        assert config.hour == 6
        assert config.minute == 30
        assert config.generations == 50
        assert config.population_size == 200
        assert config.improvement_threshold == 1.0


class TestTrainingScheduler:
    """Tests for TrainingScheduler."""

    def test_initialization(self) -> None:
        """Test scheduler initialization."""
        scheduler = TrainingScheduler()

        assert scheduler._running is False
        assert scheduler._jobs == {}

    def test_generate_job_id(self) -> None:
        """Test job ID generation."""
        scheduler = TrainingScheduler()
        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")

        job_id = scheduler._generate_job_id(bot_context)

        assert "neat_swing" in job_id
        assert "test-001" in job_id

    def test_remove_job_not_found(self) -> None:
        """Test removing non-existent job."""
        scheduler = TrainingScheduler()

        result = scheduler.remove_job("non_existent_job")

        assert result is False


class TestBotSchedulerLifecycle:
    """Tests for BotSchedulerLifecycle."""

    def test_initialization(self) -> None:
        """Test lifecycle manager initialization."""
        training_scheduler = TrainingScheduler()
        lifecycle = BotSchedulerLifecycle(training_scheduler)

        assert lifecycle.scheduler == training_scheduler
        assert lifecycle._registered_configs == {}

    def test_bot_key_generation(self) -> None:
        """Test bot key generation."""
        training_scheduler = TrainingScheduler()
        lifecycle = BotSchedulerLifecycle(training_scheduler)

        bot_context = BotContext(bot_type="neat_swing", instance_id="test-001")
        key = lifecycle._bot_key(bot_context)

        assert key == "neat_swing_test-001"
