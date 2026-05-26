"""Bot Control Domain - Process lifecycle management for trading bots.

This domain provides API-driven control over bot processes including:
- Starting bot instances via API
- Stopping bots gracefully
- Querying bot status
- Listing running bots
- Restarting bots

Follows CLEAN architecture with clear separation between
domain, service, and API layers.
"""

from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus
from stonks_trading.domains.botcontrol.use_cases import (
    GetBotStatusUseCase,
    ListRunningBotsUseCase,
    RestartBotUseCase,
    StartBotUseCase,
    StopBotUseCase,
)

__all__ = [
    # Entities
    "BotProcess",
    "BotStatus",
    "ProcessStatus",
    # Use Cases
    "StartBotUseCase",
    "StopBotUseCase",
    "GetBotStatusUseCase",
    "ListRunningBotsUseCase",
    "RestartBotUseCase",
]
