"""HTTP Client for Bot Worker API.

Used by API container to delegate bot operations to Worker container.
"""

from typing import Any

import httpx

from stonks_trading.domains.botcontrol.dtos import (
    StartBotRequest,
    StartBotResponse,
    StopBotResponse,
)

WORKER_BASE_URL = "http://bot-worker:8001"


class WorkerHTTPClient:
    """HTTP client for communicating with Bot Worker service."""

    def __init__(self, base_url: str = WORKER_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def start_bot(
        self,
        bot_type: str,
        instance_id: str,
        symbols: list[str],
        mode: str,
        config_path: str,
    ) -> StartBotResponse:
        """Call Worker to start a bot subprocess."""
        request = StartBotRequest(
            symbols=symbols,
            mode=mode,
            config_path=config_path,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/bots/{bot_type}/{instance_id}/start",
                json=request.model_dump(),
                timeout=30.0,
            )
            response.raise_for_status()
            return StartBotResponse(**response.json())

    async def stop_bot(
        self,
        bot_type: str,
        instance_id: str,
        graceful: bool = True,
    ) -> StopBotResponse:
        """Call Worker to stop a bot subprocess."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/bots/{bot_type}/{instance_id}/stop",
                params={"graceful": graceful},
                timeout=30.0,
            )
            response.raise_for_status()
            return StopBotResponse(**response.json())

    async def health_check(self) -> dict[str, Any]:
        """Check Worker health."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            response.raise_for_status()
            return response.json()
