"""WebSocket handlers for live data streaming.

Server-side WebSocket endpoints that broadcast bot state and equity updates
to connected dashboard clients.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from stonks_trading.shared.live_data.models import BotStateSnapshot
from stonks_trading.shared.logger import logger


class ConnectionManager:
    """Manages active WebSocket connections.

    Provides thread-safe connection tracking and broadcasting.
    """

    def __init__(self) -> None:
        """Initialize connection manager."""
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Register a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            channel: Channel identifier
        """
        await websocket.accept()
        async with self._lock:
            if channel not in self._connections:
                self._connections[channel] = []
            self._connections[channel].append(websocket)
        logger.info(
            f"WebSocket connected: channel={channel}, total={len(self._connections[channel])}"
        )

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection
            channel: Channel identifier
        """
        async with self._lock:
            if channel in self._connections:
                if websocket in self._connections[channel]:
                    self._connections[channel].remove(websocket)
                if not self._connections[channel]:
                    del self._connections[channel]
        logger.info(f"WebSocket disconnected: channel={channel}")

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Broadcast message to all connections in channel.

        Args:
            channel: Channel identifier
            message: Message to broadcast
        """
        async with self._lock:
            connections = list(self._connections.get(channel, []))

        if not connections:
            return

        data = json.dumps(message)
        disconnected = []

        for websocket in connections:
            try:
                await websocket.send_text(data)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if channel in self._connections and ws in self._connections[channel]:
                        self._connections[channel].remove(ws)


# Global connection manager
_manager = ConnectionManager()


class BotStateWebSocket:
    """WebSocket handler for bot state updates.

    Receives state snapshots from bots and broadcasts to dashboard clients.
    """

    def __init__(self, bot_type: str, instance_id: str):
        """Initialize bot state WebSocket handler.

        Args:
            bot_type: Bot type identifier
            instance_id: Bot instance identifier
        """
        self.bot_type = bot_type
        self.instance_id = instance_id
        self._channel = f"bot_state:{bot_type}:{instance_id}"
        self._running = False

    @property
    def channel(self) -> str:
        """Get channel name for this bot.

        Returns:
            Channel name
        """
        return self._channel

    async def start(self) -> None:
        """Start the WebSocket handler."""
        self._running = True
        logger.info(f"BotStateWebSocket started: {self._channel}")

    async def stop(self) -> None:
        """Stop the WebSocket handler."""
        self._running = False
        logger.info(f"BotStateWebSocket stopped: {self._channel}")

    def publish(self, snapshot: BotStateSnapshot) -> None:
        """Publish state snapshot to dashboard.

        Args:
            snapshot: Bot state snapshot
        """
        if not self._running:
            return
        asyncio.create_task(_manager.broadcast(self._channel, snapshot.to_dict()))


class DashboardWebSocket:
    """WebSocket endpoint for dashboard clients.

    Handles incoming WebSocket connections from dashboard and streams
    bot state updates in real-time.
    """

    def __init__(self) -> None:
        """Initialize dashboard WebSocket handler."""
        self._running = False

    async def connect_dashboard(
        self, websocket: WebSocket, bot_type: str, instance_id: str
    ) -> None:
        """Accept dashboard client connection to bot state channel.

        Args:
            websocket: WebSocket connection
            bot_type: Bot type to subscribe to
            instance_id: Bot instance to subscribe to
        """
        channel = f"bot_state:{bot_type}:{instance_id}"
        await _manager.connect(websocket, channel)
        self._running = True

    async def connect_all_bots(self, websocket: WebSocket) -> None:
        """Accept dashboard client connection to all bot states.

        Args:
            websocket: WebSocket connection
        """
        await _manager.connect(websocket, "all_bots")
        self._running = True

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Handle dashboard client disconnection.

        Args:
            websocket: WebSocket connection
            channel: Channel to disconnect from
        """
        await _manager.disconnect(websocket, channel)
        self._running = False


def get_websocket_router() -> APIRouter:
    """Create WebSocket router.

    Returns:
        APIRouter with WebSocket endpoints
    """
    router = APIRouter()

    @router.websocket("/ws/bots/{bot_type}/{instance_id}/state")
    async def websocket_bot_state(
        websocket: WebSocket,
        bot_type: str,
        instance_id: str,
    ) -> None:
        """WebSocket endpoint for bot state updates.

        Dashboard connects to receive real-time state updates for a specific bot.
        """
        dashboard = DashboardWebSocket()
        await dashboard.connect_dashboard(websocket, bot_type, instance_id)

        try:
            while True:
                # Keep connection alive - state is pushed, not pulled
                data = await websocket.receive_text()
                # Handle ping/pong or commands from client
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            await dashboard.disconnect(websocket, f"bot_state:{bot_type}:{instance_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await dashboard.disconnect(websocket, f"bot_state:{bot_type}:{instance_id}")

    @router.websocket("/ws/bots/all/state")
    async def websocket_all_bots_state(websocket: WebSocket) -> None:
        """WebSocket endpoint for all bot state updates.

        Dashboard connects to receive real-time state updates for all bots.
        """
        dashboard = DashboardWebSocket()
        await dashboard.connect_all_bots(websocket)

        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            await dashboard.disconnect(websocket, "all_bots")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await dashboard.disconnect(websocket, "all_bots")

    return router


# Global manager instance for broadcasting
def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager.

    Returns:
        ConnectionManager instance
    """
    return _manager


class RateLimitedBroadcaster:
    """Rate-limited WebSocket broadcaster to prevent overwhelming clients.

    Phase 10H: Added rate limiting to prevent flooding clients with updates.
    """

    def __init__(self, max_messages_per_second: float = 10.0):
        """Initialize broadcaster.

        Args:
            max_messages_per_second: Maximum broadcast rate per channel
        """
        self.max_rate = max_messages_per_second
        self._last_broadcast: dict[str, float] = {}

    def should_broadcast(self, channel: str) -> bool:
        """Check if broadcast should proceed based on rate limit.

        Args:
            channel: Channel identifier

        Returns:
            True if broadcast should proceed, False if rate limited
        """
        import time

        now = time.time()
        last = self._last_broadcast.get(channel, 0)
        if now - last >= 1.0 / self.max_rate:
            self._last_broadcast[channel] = now
            return True
        return False

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Broadcast message if rate limit allows.

        Args:
            channel: Channel identifier
            message: Message to broadcast
        """
        if self.should_broadcast(channel):
            await _manager.broadcast(channel, message)


# Global rate-limited broadcaster
_rate_limited_broadcaster: RateLimitedBroadcaster | None = None


def get_rate_limited_broadcaster() -> RateLimitedBroadcaster:
    """Get the global rate-limited broadcaster.

    Returns:
        RateLimitedBroadcaster instance
    """
    global _rate_limited_broadcaster
    if _rate_limited_broadcaster is None:
        _rate_limited_broadcaster = RateLimitedBroadcaster()
    return _rate_limited_broadcaster


def broadcast_bot_state(bot_type: str, instance_id: str, snapshot: BotStateSnapshot) -> None:
    """Broadcast bot state to all subscribed dashboard clients.

    Args:
        bot_type: Bot type identifier
        instance_id: Bot instance identifier
        snapshot: Bot state snapshot
    """
    channel = f"bot_state:{bot_type}:{instance_id}"
    asyncio.create_task(_manager.broadcast(channel, snapshot.to_dict()))


# =============================================================================
# Training WebSocket (Phase 3)
# =============================================================================


class TrainingWebSocket:
    """WebSocket handler for training job updates.

    Broadcasts real-time training progress to dashboard clients.
    """

    def __init__(self) -> None:
        """Initialize training WebSocket handler."""
        self._running = False

    async def connect_training(self, websocket: WebSocket, job_id: str) -> None:
        """Accept dashboard client connection to training job channel.

        Args:
            websocket: WebSocket connection
            job_id: Training job ID to subscribe to
        """
        channel = f"training:{job_id}"
        await _manager.connect(websocket, channel)
        self._running = True
        logger.info(f"Training WebSocket connected: job_id={job_id}")

    async def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        """Handle dashboard client disconnection from training channel.

        Args:
            websocket: WebSocket connection
            job_id: Training job ID
        """
        channel = f"training:{job_id}"
        await _manager.disconnect(websocket, channel)
        self._running = False
        logger.info(f"Training WebSocket disconnected: job_id={job_id}")


def broadcast_training_progress(
    job_id: str,
    generation: int,
    total_generations: int,
    best_fitness: float,
    progress_pct: float,
    status: str,
    checkpoints: list[dict[str, Any]] | None = None,
) -> None:
    """Broadcast training progress to all subscribed dashboard clients.

    Args:
        job_id: Training job ID
        generation: Current generation
        total_generations: Total generations to run
        best_fitness: Best fitness score so far
        progress_pct: Progress percentage (0-100)
        status: Job status (running, completed, failed)
        checkpoints: Optional list of checkpoint data
    """
    channel = f"training:{job_id}"
    message = {
        "type": "training_progress",
        "job_id": job_id,
        "generation": generation,
        "total_generations": total_generations,
        "best_fitness": best_fitness,
        "progress_pct": progress_pct,
        "status": status,
        "checkpoints": checkpoints or [],
        "timestamp": asyncio.get_event_loop().time(),
    }
    asyncio.create_task(_manager.broadcast(channel, message))


def get_websocket_router_with_training() -> APIRouter:
    """Create WebSocket router with training endpoint.

    Returns:
        APIRouter with WebSocket endpoints including training
    """
    router = get_websocket_router()

    @router.websocket("/ws/training/{job_id}")
    async def websocket_training_progress(
        websocket: WebSocket,
        job_id: str,
    ) -> None:
        """WebSocket endpoint for real-time training updates.

        Dashboard connects to receive live training progress updates.
        Messages include: generation, fitness, progress_pct, checkpoints.
        """
        training_ws = TrainingWebSocket()
        await training_ws.connect_training(websocket, job_id)

        try:
            while True:
                # Keep connection alive and handle client commands
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                elif data == "status":
                    # Client requesting current status
                    await websocket.send_text(json.dumps({"type": "status_ack", "job_id": job_id}))
        except WebSocketDisconnect:
            await training_ws.disconnect(websocket, job_id)
        except Exception as e:
            logger.error(f"Training WebSocket error: {e}")
            await training_ws.disconnect(websocket, job_id)

    return router
