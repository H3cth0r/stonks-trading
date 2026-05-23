"""Unit tests for bot registry routes.

Tests the bot registry endpoints for listing and registering bots.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from stonks_trading.api import create_app
from stonks_trading.domains.trading.entities import BotInstance
from stonks_trading.domains.trading.enums import TradingMode


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = create_app()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def mock_bot_instance():
    """Return a mock bot instance."""
    return BotInstance(
        bot_type="neat_swing",
        instance_id="test-instance-1",
        symbols=["BTC_USD", "ETH_USD"],
        mode=TradingMode.DRY_RUN,
        id=1,
        status="running",
        config={"threshold": 0.6},
    )


class TestListBotsEndpoint:
    """Tests for listing all bots."""

    async def test_list_bots_empty(self, client) -> None:
        """Test listing bots when none registered."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceRepository.list_all") as mock_list:
            mock_list.return_value = []
            response = await client.get("/api/v1/bots")
            assert response.status_code == 200
            data = response.json()
            assert "bots" in data
            assert "total" in data
            assert data["total"] == 0

    async def test_list_bots_returns_registered_bots(self, client, mock_bot_instance) -> None:
        """Test listing bots returns registered instances."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceRepository.list_all") as mock_list:
            mock_list.return_value = [mock_bot_instance]
            response = await client.get("/api/v1/bots")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["bots"][0]["bot_type"] == "neat_swing"
            assert data["bots"][0]["instance_id"] == "test-instance-1"


class TestListBotInstancesEndpoint:
    """Tests for listing instances of a specific bot type."""

    async def test_list_bot_instances_empty(self, client) -> None:
        """Test listing instances when none of type exist."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceRepository.list_by_type") as mock_list:
            mock_list.return_value = []
            response = await client.get("/api/v1/bots/neat_swing")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0

    async def test_list_bot_instances_returns_instances(self, client, mock_bot_instance) -> None:
        """Test listing instances of a bot type."""
        with patch("stonks_trading.domains.trading.repositories.BotInstanceRepository.list_by_type") as mock_list:
            mock_list.return_value = [mock_bot_instance]
            response = await client.get("/api/v1/bots/neat_swing")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["bots"][0]["instance_id"] == "test-instance-1"


class TestRegisterBotEndpoint:
    """Tests for bot registration."""

    async def test_register_bot_success(self, client) -> None:
        """Test registering a new bot instance."""
        mock_instance = BotInstance(
            bot_type="neat_swing",
            instance_id="new-bot-1",
            symbols=["BTC_USD"],
            mode=TradingMode.DRY_RUN,
            id=2,
            status="stopped",
        )
        with patch("stonks_trading.domains.trading.repositories.BotInstanceRepository.register") as mock_register:
            mock_register.return_value = mock_instance
            response = await client.post(
                "/api/v1/bots",
                json={
                    "bot_type": "neat_swing",
                    "instance_id": "new-bot-1",
                    "symbols": ["BTC_USD"],
                    "mode": "dry_run",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["bot_type"] == "neat_swing"
            assert data["instance_id"] == "new-bot-1"
            assert data["status"] == "stopped"

    async def test_register_bot_validates_request(self, client) -> None:
        """Test registering bot with invalid request returns 422."""
        response = await client.post(
            "/api/v1/bots",
            json={
                "bot_type": "",  # Invalid: empty string
                "instance_id": "test",
                "symbols": [],
            },
        )
        assert response.status_code == 422  # Validation error