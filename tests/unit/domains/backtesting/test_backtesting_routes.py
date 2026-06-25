"""Tests for backtesting domain routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.backtesting.routes import router


class TestBacktestingRoutes:
    """Tests for backtesting routes."""

    def test_routes_exist(self) -> None:
        """Test that routes are registered."""
        routes = [str(r.path) for r in router.routes if hasattr(r, 'path')]

        # Check that we have backtest routes
        has_backtest_route = any("/backtest" in r for r in routes)
        assert has_backtest_route, "No backtest routes found"

    def test_router_initialized(self) -> None:
        """Test that router is properly initialized."""
        assert router is not None
        assert len(router.routes) > 0

    def test_routes_have_methods(self) -> None:
        """Test that routes have HTTP methods defined."""
        for r in router.routes:
            if hasattr(r, 'methods'):
                assert len(r.methods) > 0, f"Route {r.path} has no methods"
