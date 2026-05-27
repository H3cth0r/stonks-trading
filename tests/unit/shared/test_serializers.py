"""Unit tests for serializers module."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from stonks_trading.shared.serializers import (
    BaseResponse,
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
)


class TestBaseResponse:
    """Tests for BaseResponse."""

    def test_creation_with_defaults(self):
        """BaseResponse can be created with defaults."""
        response = BaseResponse()
        assert response.success is True
        assert response.timestamp is not None
        assert response.message is None

    def test_creation_with_values(self):
        """BaseResponse can be created with custom values."""
        response = BaseResponse(success=False, message="Test message")
        assert response.success is False
        assert response.message == "Test message"

    def test_timestamp_auto_set(self):
        """timestamp is automatically set."""
        before = datetime.utcnow()
        response = BaseResponse()
        after = datetime.utcnow()
        assert before <= response.timestamp <= after


class TestErrorResponse:
    """Tests for ErrorResponse."""

    def test_creation_with_defaults(self):
        """ErrorResponse has sensible defaults."""
        response = ErrorResponse()
        assert response.success is False
        assert response.error_code == "UNKNOWN_ERROR"
        assert response.details is None

    def test_creation_with_values(self):
        """ErrorResponse can be created with custom values."""
        response = ErrorResponse(
            message="Error occurred",
            error_code="VALIDATION_ERROR",
            details={"field": "value"},
        )
        assert response.success is False
        assert response.error_code == "VALIDATION_ERROR"
        assert response.details == {"field": "value"}


class TestPaginatedResponse:
    """Tests for PaginatedResponse."""

    def test_creation_with_defaults(self):
        """PaginatedResponse has sensible defaults."""
        response = PaginatedResponse()
        assert response.data == []
        assert response.total == 0
        assert response.page == 1
        assert response.page_size == 100
        assert response.total_pages == 0

    def test_creation_with_values(self):
        """PaginatedResponse can be created with custom values."""
        response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            total=100,
            page=2,
            page_size=50,
            total_pages=2,
        )
        assert len(response.data) == 2
        assert response.total == 100
        assert response.page == 2
        assert response.page_size == 50
        assert response.total_pages == 2


class TestHealthResponse:
    """Tests for HealthResponse."""

    def test_creation_with_defaults(self):
        """HealthResponse has sensible defaults."""
        response = HealthResponse()
        assert response.success is True
        assert response.status == "healthy"
        assert response.version == "0.1.0"
        assert response.uptime_seconds == 0.0

    def test_creation_with_values(self):
        """HealthResponse can be created with custom values."""
        response = HealthResponse(
            status="unhealthy",
            version="1.0.0",
            uptime_seconds=3600.0,
            message="Running",
        )
        assert response.status == "unhealthy"
        assert response.version == "1.0.0"
        assert response.uptime_seconds == 3600.0
