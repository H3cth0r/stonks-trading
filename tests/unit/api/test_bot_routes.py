"""Unit tests for bot routes.

Tests the bot-scoped endpoints that require BotContext validation.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from stonks_trading.api import create_app


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = create_app()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestBotContextDependency:
    """Tests for get_bot_context dependency."""

    async def test_bot_not_found_returns_404(self, client) -> None:
        """Test that non-existent bot returns 404."""
        with patch(
            "stonks_trading.domains.trading.repositories.get_bot_instance"
        ) as mock_get:
            mock_get.return_value = None
            response = await client.get("/api/v1/bots/neat_swing/non-existent-instance/state")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    async def test_bot_exists_returns_context(self, client) -> None:
        """Test that existing bot returns valid state response."""
        mock_instance = MagicMock()
        mock_instance.status = "running"
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch(
                "stonks_trading.domains.trading.repositories.load_bot_state"
            ) as mock_load,
        ):
            mock_get.return_value = mock_instance
            mock_load.return_value = {"positions": {}, "trades_today": 0}
            response = await client.get("/api/v1/bots/neat_swing/test-instance/state")
            assert response.status_code == 200
            data = response.json()
            assert data["bot_type"] == "neat_swing"
            assert data["instance_id"] == "test-instance"
            assert data["status"] == "running"


class TestBotScopedRoutes:
    """Tests for bot-scoped endpoints."""

    async def test_list_bot_trades_empty(self, client) -> None:
        """Test listing trades for a bot when none exist."""
        mock_instance = MagicMock()
        mock_instance.status = "running"
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch("stonks_trading.domains.trading.repositories.list_trades_by_bot") as mock_list,
        ):
            mock_get.return_value = mock_instance
            mock_list.return_value = []
            response = await client.get("/api/v1/bots/neat_swing/test-bot/trades")
            assert response.status_code == 200
            data = response.json()
            assert "trades" in data
            assert "total" in data
            assert data["total"] == 0

    async def test_list_bot_trades_with_symbol_filter(self, client) -> None:
        """Test listing trades for a bot with symbol filter."""
        mock_instance = MagicMock()
        mock_instance.status = "running"
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch("stonks_trading.domains.trading.repositories.list_trades_by_bot") as mock_list,
        ):
            mock_get.return_value = mock_instance
            mock_list.return_value = []
            response = await client.get(
                "/api/v1/bots/neat_swing/test-bot/trades?symbol=BTC_USD&limit=50"
            )
            assert response.status_code == 200

    async def test_list_bot_positions_empty(self, client) -> None:
        """Test listing positions for a bot when none exist."""
        mock_instance = MagicMock()
        mock_instance.status = "running"
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch("stonks_trading.domains.trading.repositories.list_positions_by_bot") as mock_list,
        ):
            mock_get.return_value = mock_instance
            mock_list.return_value = []
            response = await client.get("/api/v1/bots/neat_swing/test-bot/positions")
            assert response.status_code == 200
            data = response.json()
            assert "positions" in data


class TestBotStateEndpoint:
    """Tests for bot state endpoint."""

    async def test_get_bot_state_returns_state(self, client) -> None:
        """Test getting bot state returns persisted state data."""
        mock_instance = MagicMock()
        mock_instance.status = "running"
        mock_state = {"positions": {"BTC_USD": {"qty": 0.5}}, "trades_today": 3}
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch(
                "stonks_trading.domains.trading.repositories.load_bot_state"
            ) as mock_load,
        ):
            mock_get.return_value = mock_instance
            mock_load.return_value = mock_state
            response = await client.get("/api/v1/bots/neat_swing/my-bot/state")
            assert response.status_code == 200
            data = response.json()
            assert data["bot_type"] == "neat_swing"
            assert data["instance_id"] == "my-bot"
            assert data["state"] == mock_state

    async def test_get_bot_state_no_state_returns_empty_dict(self, client) -> None:
        """Test getting bot state when no state exists returns empty dict."""
        mock_instance = MagicMock()
        mock_instance.status = "stopped"
        with (
            patch(
                "stonks_trading.domains.trading.repositories.get_bot_instance"
            ) as mock_get,
            patch(
                "stonks_trading.domains.trading.repositories.load_bot_state"
            ) as mock_load,
        ):
            mock_get.return_value = mock_instance
            mock_load.return_value = None
            response = await client.get("/api/v1/bots/neat_swing/new-bot/state")
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == {}
