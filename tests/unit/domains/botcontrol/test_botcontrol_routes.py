"""Unit tests for bot control domain routes.

Tests HTTP layer - mocks use cases.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stonks_trading.domains.botcontrol.routes import get_botcontrol_router


@pytest.fixture
def app() -> FastAPI:
    """Create FastAPI app with botcontrol router."""
    app = FastAPI()
    app.include_router(get_botcontrol_router(), prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestStartBotEndpoint:
    """Test POST /bots/{type}/{id}/start endpoint."""

    @patch("stonks_trading.domains.botcontrol.routes.StartBotUseCase")
    def test_start_bot_success(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Successfully start a bot."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=MagicMock(value="starting"),
            pid=12345,
            started_at=datetime.utcnow(),
        )

        response = client.post(
            "/api/v1/bots/neat_swing/test-bot-1/start",
            json={"symbols": ["BTC_USD"], "mode": "dry_run"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["bot_type"] == "neat_swing"
        assert data["status"] == "starting"
        assert data["pid"] == 12345

    @patch("stonks_trading.domains.botcontrol.routes.StartBotUseCase")
    def test_start_bot_not_registered(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return 404 if bot not registered."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.side_effect = ValueError(
            "Bot neat_swing/test-bot-1 not registered"
        )

        response = client.post(
            "/api/v1/bots/neat_swing/test-bot-1/start",
            json={"symbols": ["BTC_USD"], "mode": "dry_run"},
        )

        assert response.status_code == 404

    @patch("stonks_trading.domains.botcontrol.routes.StartBotUseCase")
    def test_start_bot_already_running(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return 409 if bot already running."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.side_effect = RuntimeError(
            "Bot neat_swing/test-bot-1 is already running"
        )

        response = client.post(
            "/api/v1/bots/neat_swing/test-bot-1/start",
            json={"symbols": ["BTC_USD"], "mode": "dry_run"},
        )

        assert response.status_code == 409


class TestStopBotEndpoint:
    """Test POST /bots/{type}/{id}/stop endpoint."""

    @patch("stonks_trading.domains.botcontrol.routes.StopBotUseCase")
    def test_stop_bot_success(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Successfully stop a bot."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=MagicMock(value="stopped"),
            stopped_at=datetime.utcnow(),
            pid=12345,
            uptime_seconds=3600,
            error_message=None,
        )

        response = client.post("/api/v1/bots/neat_swing/test-bot-1/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["bot_type"] == "neat_swing"

    @patch("stonks_trading.domains.botcontrol.routes.StopBotUseCase")
    def test_stop_bot_not_found(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return 404 if bot process not found."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.side_effect = ValueError(
            "Bot neat_swing/test-bot-1 process not found"
        )

        response = client.post("/api/v1/bots/neat_swing/test-bot-1/stop")

        assert response.status_code == 404


class TestGetBotStatusEndpoint:
    """Test GET /bots/{type}/{id}/status endpoint."""

    @patch("stonks_trading.domains.botcontrol.routes.GetBotStatusUseCase")
    def test_get_status_success(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Successfully get bot status."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            status=MagicMock(value="running"),
            mode="dry_run",
            uptime_seconds=3600,
            current_equity=10500.50,
            position_count=1,
            pid=12345,
            message=None,
            last_seen=datetime.utcnow(),
        )

        response = client.get("/api/v1/bots/neat_swing/test-bot-1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["mode"] == "dry_run"
        assert data["uptime_seconds"] == 3600
        assert data["current_equity"] == 10500.50
        assert data["pid"] == 12345

    @patch("stonks_trading.domains.botcontrol.routes.GetBotStatusUseCase")
    def test_get_status_not_found(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return 404 if bot not found."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = None

        response = client.get("/api/v1/bots/neat_swing/test-bot-1/status")

        assert response.status_code == 404


class TestListRunningBotsEndpoint:
    """Test GET /bots/running endpoint."""

    @patch("stonks_trading.domains.botcontrol.routes.ListRunningBotsUseCase")
    def test_list_running_bots(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """List all running bots."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = [
            MagicMock(
                bot_type="neat_swing",
                bot_instance_id="test-bot-1",
                status=MagicMock(value="running"),
                mode="dry_run",
                uptime_seconds=3600,
                current_equity=None,
                position_count=0,
                pid=12345,
                message=None,
                last_seen=datetime.utcnow(),
            ),
            MagicMock(
                bot_type="neat_swing",
                bot_instance_id="test-bot-2",
                status=MagicMock(value="running"),
                mode="live",
                uptime_seconds=7200,
                current_equity=None,
                position_count=0,
                pid=12346,
                message=None,
                last_seen=datetime.utcnow(),
            ),
        ]

        response = client.get("/api/v1/bots/running")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["bots"]) == 2

    @patch("stonks_trading.domains.botcontrol.routes.ListRunningBotsUseCase")
    def test_list_running_bots_empty(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return empty list when no bots running."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = []

        response = client.get("/api/v1/bots/running")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["bots"] == []


class TestRestartBotEndpoint:
    """Test POST /bots/{type}/{id}/restart endpoint."""

    @patch("stonks_trading.domains.botcontrol.routes.RestartBotUseCase")
    def test_restart_bot_success(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Successfully restart a bot."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            bot_type="neat_swing",
            bot_instance_id="test-bot-1",
            mode="dry_run",
            pid=12346,
            status=MagicMock(value="starting"),
            started_at=datetime.utcnow(),
        )

        response = client.post("/api/v1/bots/neat_swing/test-bot-1/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "starting"
        assert "restarted" in data["message"].lower()

    @patch("stonks_trading.domains.botcontrol.routes.RestartBotUseCase")
    def test_restart_bot_not_found(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Return 404 if bot not found."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.side_effect = ValueError(
            "Bot neat_swing/test-bot-1 not found"
        )

        response = client.post("/api/v1/bots/neat_swing/test-bot-1/restart")

        assert response.status_code == 404
