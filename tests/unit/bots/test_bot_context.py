"""Tests for BotContext value object."""

import pytest
from stonks_trading.bots import BotContext


class TestBotContext:
    """Test suite for BotContext value object."""

    def test_create_basic(self) -> None:
        """Should create with required fields."""
        context = BotContext(bot_type="neat_swing", instance_id="test-1")

        assert context.bot_type == "neat_swing"
        assert context.instance_id == "test-1"

    def test_frozen_immutable(self) -> None:
        """Should be immutable after creation."""
        context = BotContext(bot_type="neat_swing", instance_id="test-1")

        with pytest.raises(Exception):
            context.bot_type = "other"

        with pytest.raises(Exception):
            context.instance_id = "other"

    def test_string_representation(self) -> None:
        """Should format as type/instance_id."""
        context = BotContext(bot_type="neat_swing", instance_id="test-1")

        assert str(context) == "neat_swing/test-1"

    def test_to_dict(self) -> None:
        """Should serialize to dictionary."""
        context = BotContext(bot_type="neat_swing", instance_id="test-1")

        data = context.to_dict()

        assert data == {"bot_type": "neat_swing", "bot_instance_id": "test-1"}

    def test_equality_same_values(self) -> None:
        """Should be equal with same values."""
        c1 = BotContext(bot_type="neat_swing", instance_id="test-1")
        c2 = BotContext(bot_type="neat_swing", instance_id="test-1")

        assert c1 == c2
        assert hash(c1) == hash(c2)

    def test_inequality_different_type(self) -> None:
        """Should not be equal with different bot_type."""
        c1 = BotContext(bot_type="neat_swing", instance_id="test-1")
        c2 = BotContext(bot_type="mean_reversion", instance_id="test-1")

        assert c1 != c2

    def test_inequality_different_instance(self) -> None:
        """Should not be equal with different instance_id."""
        c1 = BotContext(bot_type="neat_swing", instance_id="test-1")
        c2 = BotContext(bot_type="neat_swing", instance_id="test-2")

        assert c1 != c2

    def test_validation_min_length(self) -> None:
        """Should reject empty bot_type."""
        with pytest.raises(Exception):
            BotContext(bot_type="", instance_id="test-1")

    def test_validation_max_length(self) -> None:
        """Should reject overly long bot_type."""
        with pytest.raises(Exception):
            BotContext(bot_type="x" * 51, instance_id="test-1")

    def test_validation_instance_max_length(self) -> None:
        """Should reject overly long instance_id."""
        with pytest.raises(Exception):
            BotContext(bot_type="neat_swing", instance_id="x" * 101)
