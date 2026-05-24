"""Tests for dashboard utilities.

All imports at module level per CLEAN architecture - no lazy imports.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stonks_trading.presentation.dashboard.utils import (
    APIClient,
    API_BASE,
    fetch_sync,
    post_sync,
)


class TestAPIClient:
    """Test APIClient class."""

    def test_init_default_base_url(self) -> None:
        """Test APIClient initializes with default base URL."""
        client = APIClient()
        assert client.base_url == API_BASE
        assert client.base_url == "http://localhost:8000"

    def test_init_custom_base_url(self) -> None:
        """Test APIClient initializes with custom base URL."""
        custom_url = "https://api.example.com"
        client = APIClient(base_url=custom_url)
        assert client.base_url == custom_url

    @pytest.mark.asyncio
    async def test_get_success(self) -> None:
        """Test successful GET request."""
        client = APIClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get("/api/v1/test")

        assert result == {"data": "test"}
        client.client.get.assert_called_once_with("/api/v1/test", params=None)

    @pytest.mark.asyncio
    async def test_get_with_params(self) -> None:
        """Test GET request with query parameters."""
        client = APIClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        params = {"limit": 10, "offset": 0}
        result = await client.get("/api/v1/test", params=params)

        assert result == {"data": "test"}
        client.client.get.assert_called_once_with("/api/v1/test", params=params)

    @pytest.mark.asyncio
    async def test_post_success(self) -> None:
        """Test successful POST request."""
        client = APIClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "status": "created"}
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        data = {"name": "test"}
        result = await client.post("/api/v1/test", data=data)

        assert result == {"id": 1, "status": "created"}
        client.client.post.assert_called_once_with("/api/v1/test", json=data)

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test client close method."""
        client = APIClient()
        client.client.aclose = AsyncMock()

        await client.close()

        client.client.aclose.assert_called_once()


class TestFetchSync:
    """Test fetch_sync function."""

    @patch("stonks_trading.presentation.dashboard.utils.st")
    def test_fetch_sync_success(self, mock_st: MagicMock) -> None:
        """Test successful synchronous fetch."""
        with patch.object(
            APIClient, "get", new_callable=lambda: AsyncMock(return_value={"bots": []})
        ):
            result = fetch_sync("/api/v1/bots")

            assert result == {"bots": []}

    @patch("stonks_trading.presentation.dashboard.utils.st")
    def test_fetch_sync_error(self, mock_st: MagicMock) -> None:
        """Test fetch_sync handles errors gracefully."""
        with patch.object(
            APIClient,
            "get",
            new_callable=lambda: AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404 Not Found", request=MagicMock(), response=MagicMock()
                )
            ),
        ):
            result = fetch_sync("/api/v1/invalid")

            assert result == {}
            mock_st.error.assert_called_once()


class TestPostSync:
    """Test post_sync function."""

    @patch("stonks_trading.presentation.dashboard.utils.st")
    def test_post_sync_success(self, mock_st: MagicMock) -> None:
        """Test successful synchronous POST."""
        with patch.object(
            APIClient, "post", new_callable=lambda: AsyncMock(return_value={"id": 1})
        ):
            data = {"name": "test"}
            result = post_sync("/api/v1/test", data=data)

            assert result == {"id": 1}

    @patch("stonks_trading.presentation.dashboard.utils.st")
    def test_post_sync_error(self, mock_st: MagicMock) -> None:
        """Test post_sync handles errors gracefully."""
        with patch.object(
            APIClient, "post", new_callable=lambda: AsyncMock(side_effect=Exception("Connection error"))
        ):
            result = post_sync("/api/v1/test")

            assert result == {}
            mock_st.error.assert_called_once()
