"""Unit tests for health domain routes.

Tests HTTP layer - mocks use cases.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stonks_trading.domains.health.routes import get_health_router


@pytest.fixture
def app() -> FastAPI:
    """Create FastAPI app with health router."""
    app = FastAPI()
    app.include_router(get_health_router())
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestHealthReadyEndpoint:
    """Test GET /health/ready endpoint."""

    def test_returns_healthy_status(self, client: TestClient) -> None:
        """Returns simple healthy status for load balancers."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestSystemHealthEndpoint:
    """Test GET /health endpoint."""

    @patch("stonks_trading.domains.health.routes.GetSystemHealthUseCase")
    def test_returns_system_health(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Returns full system health with bots."""
        # Mock use case
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            status=MagicMock(value="healthy"),
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            bots=[],
            checked_at=datetime.utcnow(),
            message=None,
        )

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "bots" in data


class TestListBotHealthEndpoint:
    """Test GET /health/bots endpoint."""

    @patch("stonks_trading.domains.health.routes.GetSystemHealthUseCase")
    def test_returns_bot_health_list(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Returns list of all bot health statuses."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            status=MagicMock(value="healthy"),
            api_healthy=True,
            database_healthy=True,
            duckdb_healthy=True,
            bots=[],
            checked_at=datetime.utcnow(),
        )

        response = client.get("/health/bots")
        assert response.status_code == 200
        data = response.json()
        assert "bots" in data
        assert "total" in data
        assert "healthy_count" in data


class TestRecordHeartbeatEndpoint:
    """Test POST /health/heartbeat endpoint."""

    @patch("stonks_trading.domains.health.routes.RecordHeartbeatUseCase")
    def test_records_heartbeat(self, mock_use_case_class: MagicMock, client: TestClient) -> None:
        """Records heartbeat and returns response."""
        mock_use_case = AsyncMock()
        mock_use_case_class.return_value = mock_use_case
        mock_use_case.execute.return_value = MagicMock(
            id=1,
            bot_type="neat_swing",
            bot_instance_id="test-1",
            timestamp=datetime.utcnow(),
            state_hash="abc123",
            candle_timestamp=datetime.utcnow(),
        )

        request_data = {
            "bot_type": "neat_swing",
            "bot_instance_id": "test-1",
            "state_hash": "abc123",
        }

        response = client.post("/health/heartbeat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["bot_type"] == "neat_swing"
        assert data["bot_instance_id"] == "test-1"
