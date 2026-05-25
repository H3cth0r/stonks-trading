"""Tests for training domain services."""

import pickle
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from stonks_trading.domains.training.services import (
    CheckpointManager,
    GenomeEvaluator,
    GenomeSerializer,
    TrainingDataProvider,
    TrainingExecutor,
)


class TestTrainingExecutor:
    """Tests for TrainingExecutor service."""

    def test_initialization(self) -> None:
        """Test executor initializes with correct defaults."""
        executor = TrainingExecutor()

        assert executor.generations == 30
        assert executor.population_size == 150
        assert executor.initial_capital == 10000.0
        assert executor.fee_rate == 0.001
        assert executor.decision_threshold == 0.6
        assert executor.min_trade_interval == 15

    def test_initialization_with_custom_params(self) -> None:
        """Test executor initializes with custom parameters."""
        executor = TrainingExecutor(
            generations=50,
            population_size=200,
            initial_capital=5000.0,
            fee_rate=0.002,
            decision_threshold=0.7,
            min_trade_interval=20,
        )

        assert executor.generations == 50
        assert executor.population_size == 200
        assert executor.initial_capital == 5000.0
        assert executor.fee_rate == 0.002
        assert executor.decision_threshold == 0.7
        assert executor.min_trade_interval == 20

    def test_get_config(self) -> None:
        """Test config generation."""
        executor = TrainingExecutor()
        config = executor.get_config()

        assert config is not None
        assert config.pop_size == 150


class TestGenomeEvaluator:
    """Tests for GenomeEvaluator service."""

    def test_initialization(self) -> None:
        """Test evaluator initializes correctly."""
        evaluator = GenomeEvaluator()

        assert evaluator.initial_capital == 10000.0
        assert evaluator.fee_rate == 0.001
        assert evaluator.decision_threshold == 0.6

    def test_calculate_improvement(self) -> None:
        """Test improvement calculation."""
        evaluator = GenomeEvaluator()

        # New ROI better than previous
        improvement = evaluator.calculate_improvement(new_roi=15.0, prev_roi=10.0)
        assert improvement == 5.0

        # New ROI worse than previous
        improvement = evaluator.calculate_improvement(new_roi=8.0, prev_roi=10.0)
        assert improvement == -2.0

        # Equal ROI
        improvement = evaluator.calculate_improvement(new_roi=10.0, prev_roi=10.0)
        assert improvement == 0.0


class TestGenomeSerializer:
    """Tests for GenomeSerializer service."""

    def test_serialize_deserialize_roundtrip(self) -> None:
        """Test serialize then deserialize returns original data."""
        # Create a mock genome-like object
        original_genome = {"id": 1, "fitness": 100.0, "nodes": [1, 2, 3]}
        original_config = {"pop_size": 150}

        # Serialize
        data = GenomeSerializer.serialize(original_genome, original_config)
        assert isinstance(data, bytes)

        # Deserialize
        genome, config = GenomeSerializer.deserialize(data)

        assert genome == original_genome
        assert config == original_config

    def test_serialize_returns_bytes(self) -> None:
        """Test serialize returns bytes."""
        genome = {"test": "data"}
        config = {"param": 1}

        result = GenomeSerializer.serialize(genome, config)

        assert isinstance(result, bytes)
        assert len(result) > 0


class TestCheckpointManager:
    """Tests for CheckpointManager service."""

    def test_initialization(self) -> None:
        """Test manager initializes with correct defaults."""
        manager = CheckpointManager()

        assert manager.keep_every_nth == 5
        assert manager.max_checkpoints == 20

    def test_initialization_with_custom_params(self) -> None:
        """Test manager initializes with custom parameters."""
        manager = CheckpointManager(keep_every_nth=10, max_checkpoints=50)

        assert manager.keep_every_nth == 10
        assert manager.max_checkpoints == 50

    def test_should_retain_checkpoint_best(self) -> None:
        """Test that best fitness checkpoint is always retained."""
        manager = CheckpointManager()

        # Best fitness
        result = manager.should_retain_checkpoint(
            generation=10, fitness=100.0, best_fitness=100.0
        )
        assert result is True

    def test_should_retain_checkpoint_every_nth(self) -> None:
        """Test that every Nth checkpoint is retained."""
        manager = CheckpointManager(keep_every_nth=5)

        # Every 5th generation
        result = manager.should_retain_checkpoint(
            generation=5, fitness=90.0, best_fitness=100.0
        )
        assert result is True

        result = manager.should_retain_checkpoint(
            generation=10, fitness=90.0, best_fitness=100.0
        )
        assert result is True

    def test_should_retain_checkpoint_skip_others(self) -> None:
        """Test that non-Nth checkpoints are skipped."""
        manager = CheckpointManager(keep_every_nth=5)

        # Not every 5th and not best
        result = manager.should_retain_checkpoint(
            generation=3, fitness=90.0, best_fitness=100.0
        )
        assert result is False

    def test_apply_retention_policy(self) -> None:
        """Test retention policy application."""
        manager = CheckpointManager(max_checkpoints=10, keep_every_nth=5)

        checkpoints = [
            {"generation": i, "fitness": 100.0 - i}
            for i in range(20)
        ]

        result = manager.apply_retention_policy(checkpoints)

        # Should have filtered some out
        assert len(result) <= manager.max_checkpoints


class TestTrainingDataProvider:
    """Tests for TrainingDataProvider service."""

    def test_initialization(self) -> None:
        """Test provider initializes correctly."""
        provider = TrainingDataProvider(db_path="test.db")

        assert provider._db_client is not None

    def test_column_mapping(self) -> None:
        """Test column mapping is correct."""
        provider = TrainingDataProvider()

        expected = {
            "timestamp": "Datetime",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        assert provider.COLUMN_MAPPING == expected

    def test_required_features(self) -> None:
        """Test required features are defined."""
        provider = TrainingDataProvider()

        expected = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]
        assert provider.REQUIRED_FEATURES == expected
