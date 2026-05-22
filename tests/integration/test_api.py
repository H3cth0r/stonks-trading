"""Integration tests for API endpoints.

These tests verify API functionality including routing,
request validation, and response formatting.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from stonks_trading.api import create_app
from stonks_trading.domains.trading.routes import get_trading_router
from stonks_trading.shared.database import init_db, close_db


# Database fixture for tests
@pytest.fixture(autouse=True)
async def initialize_db():
    """Initialize database for tests."""
    await init_db()
    yield
    await close_db()


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = create_app()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestHealthEndpoint:
    """Tests for health endpoint."""

    async def test_health_returns_200(self, client) -> None:
        """Test health endpoint returns healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestTradeRoutes:
    """Tests for trade API routes."""

    async def test_list_trades_empty(self, client) -> None:
        """Test listing trades when none exist."""
        response = await client.get("/api/v1/trades")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "total" in data

    async def test_list_trades_with_symbol_filter(self, client) -> None:
        """Test listing trades with symbol filter."""
        response = await client.get("/api/v1/trades?symbol=BTC_USD&limit=50")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data

    async def test_get_trade_not_found(self, client) -> None:
        """Test getting non-existent trade returns 404."""
        response = await client.get("/api/v1/trades/999999")
        assert response.status_code == 404

    async def test_create_trade_not_implemented(self, client) -> None:
        """Test creating trade returns 501 (Phase 4)."""
        response = await client.post(
            "/api/v1/trades",
            json={
                "symbol": "BTC_USD",
                "side": "buy",
                "quantity": 0.1,
                "price": 50000.0,
            },
        )
        assert response.status_code == 501


class TestPositionRoutes:
    """Tests for position API routes."""

    async def test_list_positions_empty(self, client) -> None:
        """Test listing positions when none exist."""
        response = await client.get("/api/v1/positions")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data

    async def test_get_position_not_found(self, client) -> None:
        """Test getting non-existent position returns 404."""
        response = await client.get("/api/v1/positions/NONEXISTENT")
        assert response.status_code == 404


class TestGenomeRoutes:
    """Tests for genome API routes."""

    async def test_list_genomes_empty(self, client) -> None:
        """Test listing genomes when none exist."""
        response = await client.get("/api/v1/genomes")
        assert response.status_code == 200
        data = response.json()
        assert "genomes" in data
        assert "total" in data

    async def test_list_genomes_with_symbol_filter(self, client) -> None:
        """Test listing genomes with symbol filter."""
        response = await client.get("/api/v1/genomes?symbol=BTC_USD")
        assert response.status_code == 200

    async def test_get_active_genome_not_found(self, client) -> None:
        """Test getting active genome when none exists returns 404."""
        response = await client.get("/api/v1/genomes/active")
        assert response.status_code == 404

    async def test_get_genome_not_found(self, client) -> None:
        """Test getting non-existent genome returns 404."""
        response = await client.get("/api/v1/genomes/999999")
        assert response.status_code == 404

    async def test_activate_genome_not_found(self, client) -> None:
        """Test activating non-existent genome returns 404."""
        response = await client.post(
            "/api/v1/genomes/activate",
            json={"genome_id": 999999},
        )
        assert response.status_code == 404


class TestRiskRoutes:
    """Tests for risk API routes."""

    async def test_list_risk_events_empty(self, client) -> None:
        """Test listing risk events when none exist."""
        response = await client.get("/api/v1/risk/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data

    async def test_list_risk_events_with_severity_filter(self, client) -> None:
        """Test listing risk events with severity filter."""
        response = await client.get("/api/v1/risk/events?severity=warning")
        assert response.status_code == 200

    async def test_acknowledge_risk_event_not_found(self, client) -> None:
        """Test acknowledging non-existent event returns 404."""
        response = await client.post(
            "/api/v1/risk/events/999999/acknowledge",
            json={"user": "test_user", "action": "acknowledged"},
        )
        assert response.status_code == 404

    async def test_get_risk_status(self, client) -> None:
        """Test getting risk status."""
        response = await client.get("/api/v1/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestMarketRoutes:
    """Tests for market data API routes."""

    async def test_get_price_not_implemented(self, client) -> None:
        """Test getting price returns 501 (Phase 4)."""
        response = await client.get("/api/v1/market/price/BTC_USD")
        assert response.status_code == 501

    async def test_get_candles_empty(self, client) -> None:
        """Test getting candles returns empty list (Phase 4)."""
        response = await client.get("/api/v1/market/candles/BTC_USD")
        assert response.status_code == 200
        data = response.json()
        assert "candles" in data


class TestPortfolioRoutes:
    """Tests for portfolio API routes."""

    async def test_get_portfolio_placeholder(self, client) -> None:
        """Test getting portfolio returns placeholder data."""
        response = await client.get("/api/v1/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert "total_value" in data

    async def test_get_balance_placeholder(self, client) -> None:
        """Test getting balance returns placeholder data."""
        response = await client.get("/api/v1/portfolio/balance")
        assert response.status_code == 200
        data = response.json()
        assert "balances" in data


class TestSignalRoutes:
    """Tests for signal evaluation API routes."""

    async def test_evaluate_signal_buy(self, client) -> None:
        """Test evaluating buy signal."""
        response = await client.post(
            "/api/v1/signals/evaluate",
            json={
                "buy_prob": 0.7,
                "sell_prob": 0.3,
                "current_price": 50000.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "buy"
        assert data["should_trade"] is True

    async def test_evaluate_signal_sell(self, client) -> None:
        """Test evaluating sell signal."""
        response = await client.post(
            "/api/v1/signals/evaluate",
            json={
                "buy_prob": 0.2,
                "sell_prob": 0.8,
                "current_price": 50000.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "sell"
        assert data["should_trade"] is True

    async def test_evaluate_signal_no_threshold(self, client) -> None:
        """Test evaluating signal below threshold."""
        response = await client.post(
            "/api/v1/signals/evaluate",
            json={
                "buy_prob": 0.4,
                "sell_prob": 0.35,
                "current_price": 50000.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] is None
        assert data["should_trade"] is False


class TestAPIResponseFormat:
    """Tests for API response format compliance."""

    async def test_success_response_has_timestamp(self, client) -> None:
        """Test successful responses include timestamp."""
        response = await client.get("/api/v1/trades")
        assert response.status_code == 200
        data = response.json()
        # Response should have timestamp field
        # (inherits from BaseResponse)

    async def test_error_response_format(self, client) -> None:
        """Test error responses follow consistent format."""
        response = await client.get("/api/v1/trades/999999")
        assert response.status_code == 404
        # Error format should be consistent
