"""Structured logging configuration with 5 log types.

Log Types:
- ERROR: Application errors requiring immediate attention
- WARNING: Anomalies that don't stop trading but need review
- INFRA: Infrastructure events (DB connections, API calls)
- TRADE: Trade execution events (fills, orders)
- AUDIT: Compliance and tax audit trail

Log Context:
- bot_type: Bot type if available in context
- bot_instance_id: Bot instance ID if available
- log_type: Structured log level (ERROR, WARNING, INFRA, TRADE, AUDIT)
"""

from contextvars import ContextVar
from enum import Enum
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from stonks_trading.shared.config import settings

# Context variables for log enrichment
bot_type_var: ContextVar[str | None] = ContextVar("bot_type", default=None)
bot_instance_id_var: ContextVar[str | None] = ContextVar("bot_instance_id", default=None)


class LogLevel(Enum):
    """Structured log levels for different event types."""

    ERROR = "error"
    WARNING = "warning"
    INFRA = "infra"
    TRADE = "trade"
    AUDIT = "audit"


def add_log_type(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add log_type field based on log level."""
    level = event_dict.get("level", "info").lower()
    log_type_map = {
        "error": LogLevel.ERROR.value,
        "exception": LogLevel.ERROR.value,
        "warning": LogLevel.WARNING.value,
        "warn": LogLevel.WARNING.value,
        "infra": LogLevel.INFRA.value,
        "trade": LogLevel.TRADE.value,
        "audit": LogLevel.AUDIT.value,
    }
    event_dict["log_type"] = log_type_map.get(level, "info")
    return event_dict


def add_bot_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add bot context from ContextVars if available."""
    bot_type = bot_type_var.get()
    bot_instance_id = bot_instance_id_var.get()

    if bot_type:
        event_dict["bot_type"] = bot_type
    if bot_instance_id:
        event_dict["bot_instance_id"] = bot_instance_id

    return event_dict


def configure_logging() -> None:
    """Configure structlog for structured logging."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_log_type,
        add_bot_context,
        structlog.processors.dict_tracebacks,
    ]

    if settings.log_format == "json":
        # JSON format for production
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(__import__("logging"), settings.log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )
    else:
        # Console format for development
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(__import__("logging"), settings.log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )


# Initialize logging on module import
configure_logging()

# Create logger instance
logger = structlog.get_logger()


# Convenience functions for different log types
def log_error(event: str, **kwargs: Any) -> None:
    """Log an error event."""
    logger.error(event, log_type=LogLevel.ERROR.value, **kwargs)


def log_warning(event: str, **kwargs: Any) -> None:
    """Log a warning event."""
    logger.warning(event, log_type=LogLevel.WARNING.value, **kwargs)


def log_infra(event: str, **kwargs: Any) -> None:
    """Log an infrastructure event."""
    logger.info(event, log_type=LogLevel.INFRA.value, **kwargs)


def log_trade(event: str, **kwargs: Any) -> None:
    """Log a trade event."""
    logger.info(event, log_type=LogLevel.TRADE.value, **kwargs)


def log_audit(event: str, **kwargs: Any) -> None:
    """Log an audit event for compliance."""
    logger.info(event, log_type=LogLevel.AUDIT.value, **kwargs)


def set_bot_context(bot_type: str, bot_instance_id: str) -> None:
    """Set bot context for log enrichment.

    Args:
        bot_type: Type of bot (e.g., "neat_swing")
        bot_instance_id: Bot instance ID
    """
    bot_type_var.set(bot_type)
    bot_instance_id_var.set(bot_instance_id)


def clear_bot_context() -> None:
    """Clear bot context from logs."""
    bot_type_var.set(None)
    bot_instance_id_var.set(None)
