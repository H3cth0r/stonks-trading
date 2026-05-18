"""Domain enumerations for trading domain.

All enums used across the domain are defined here for consistency.
"""

from enum import Enum


class Side(str, Enum):
    """Trade side enumeration."""

    BUY = "buy"
    SELL = "sell"


class TradingMode(str, Enum):
    """Trading mode enumeration."""

    BACKTEST = "backtest"
    DRY_RUN = "dry_run"
    LIVE = "live"


class OrderType(str, Enum):
    """Order type enumeration."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status enumeration."""

    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    """Risk level enumeration."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class EventType(str, Enum):
    """Risk event type enumeration."""

    DRAWDOWN_BREACH = "drawdown_breach"
    DRAWDOWN_WARNING = "drawdown_warning"
    TRADE_LIMIT = "trade_limit"
    KILL_SWITCH = "kill_switch"
