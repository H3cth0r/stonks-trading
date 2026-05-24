"""Dashboard utilities - API client for FastAPI backend.

All imports at module level per CLEAN architecture - no lazy imports.
"""

import asyncio
import os
from typing import Any, cast

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


class APIClient:
    """Async HTTP client for FastAPI backend.

    Provides async GET/POST methods with automatic error handling.
    Must be closed after use to prevent connection leaks.
    """

    def __init__(self, base_url: str = API_BASE) -> None:
        """Initialize API client with base URL.

        Args:
            base_url: Base URL for API requests (default: http://localhost:8000)
        """
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET request to API.

        Args:
            endpoint: API endpoint path (e.g., "/api/v1/bots")
            params: Optional query parameters

        Returns:
            JSON response as dictionary

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses
        """
        response = await self.client.get(endpoint, params=params)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def post(self, endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST request to API.

        Args:
            endpoint: API endpoint path
            data: JSON payload

        Returns:
            JSON response as dictionary

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses
        """
        response = await self.client.post(endpoint, json=data)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def close(self) -> None:
        """Close HTTP client and release connections."""
        await self.client.aclose()


@st.cache_resource
def get_api_client() -> APIClient:
    """Get cached API client instance.

    Uses Streamlit's cache_resource to avoid recreating
    the client on every rerun.

    Returns:
        Configured APIClient instance
    """
    return APIClient()


def fetch_sync(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Synchronous fetch for Streamlit.

    Runs async HTTP request in asyncio event loop.
    Handles errors and returns empty dict on failure.

    Args:
        endpoint: API endpoint path
        params: Optional query parameters

    Returns:
        JSON response or empty dict on error
    """
    client = get_api_client()
    try:
        return asyncio.run(client.get(endpoint, params))
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}


def post_sync(endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Synchronous POST for Streamlit.

    Runs async HTTP request in asyncio event loop.
    Handles errors and returns empty dict on failure.

    Args:
        endpoint: API endpoint path
        data: JSON payload

    Returns:
        JSON response or empty dict on error
    """
    client = get_api_client()
    try:
        return asyncio.run(client.post(endpoint, data))
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}
