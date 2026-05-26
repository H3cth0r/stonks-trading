"""Health monitoring domain.

Provides health checks, heartbeat tracking, and system monitoring
for the trading platform.

Usage:
    from stonks_trading.domains.health.entities import BotHealth, SystemHealth
    from stonks_trading.domains.health.use_cases import GetSystemHealthUseCase
    from stonks_trading.domains.health.routes import get_health_router
"""

from stonks_trading.domains.health.entities import (
    BotHealth,
    BotHeartbeat,
    HealthStatus,
    SystemHealth,
)

__all__ = [
    "BotHealth",
    "BotHeartbeat",
    "HealthStatus",
    "SystemHealth",
]
