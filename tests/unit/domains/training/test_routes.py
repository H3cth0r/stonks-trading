"""Tests for training domain routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stonks_trading.domains.training.routes import router


class TestTrainingRoutes:
    """Tests for training routes."""

    def test_routes_exist(self) -> None:
        """Test that routes are registered."""
        routes = [str(r.path) for r in router.routes if hasattr(r, 'path')]

        # Check that we have training-related routes
        has_runs_route = any("/training" in r for r in routes)
        assert has_runs_route, "No training routes found"

    def test_router_initialized(self) -> None:
        """Test that router is properly initialized."""
        assert router is not None
        assert len(router.routes) > 0


class TestTrainingSchedulerRoutes:
    """Tests for training scheduler routes."""

    def test_scheduler_routes_registered(self) -> None:
        """Test scheduler routes are properly registered."""
        route_paths = [str(r.path) for r in router.routes if hasattr(r, 'path')]

        # Check for scheduler-specific routes
        scheduler_paths_found = [
            path for path in route_paths
            if "scheduler" in path
        ]

        assert len(scheduler_paths_found) > 0, "No scheduler routes found"

    def test_routes_have_methods(self) -> None:
        """Test that routes have HTTP methods defined."""
        for r in router.routes:
            if hasattr(r, 'methods'):
                assert len(r.methods) > 0, f"Route {r.path} has no methods"
