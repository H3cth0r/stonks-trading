"""Prometheus metrics for observability.

Defines counters, gauges, and histograms for bot monitoring,
trading activity, and system health.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Bot activity metrics
BOT_TRADES_TOTAL = Counter(
    "bot_trades_total",
    "Total number of trades executed by bot",
    ["bot_type", "bot_instance_id", "symbol", "side"],
)

BOT_HEARTBEAT_TOTAL = Counter(
    "bot_heartbeat_total",
    "Total number of heartbeats received from bot",
    ["bot_type", "bot_instance_id"],
)

# Bot state gauges (current values)
BOT_EQUITY_USD = Gauge(
    "bot_equity_usd",
    "Current bot equity in USD",
    ["bot_type", "bot_instance_id"],
)

BOT_POSITION_QUANTITY = Gauge(
    "bot_position_quantity",
    "Current position quantity for symbol",
    ["bot_type", "bot_instance_id", "symbol"],
)

BOT_DRAWDOWN_PCT = Gauge(
    "bot_drawdown_pct",
    "Current portfolio drawdown percentage",
    ["bot_type", "bot_instance_id"],
)

BOT_UPTIME_SECONDS = Gauge(
    "bot_uptime_seconds",
    "Bot uptime in seconds",
    ["bot_type", "bot_instance_id"],
)

# System health metrics
DB_CONNECTION_HEALTH = Gauge(
    "db_connection_health",
    "Database connection health (1=healthy, 0=unhealthy)",
    ["db_type"],
)

API_REQUESTS_TOTAL = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

# Trading metrics
TRADE_LATENCY_MS = Histogram(
    "trade_latency_ms",
    "Trade execution latency in milliseconds",
    ["bot_type", "bot_instance_id", "venue"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
)

ORDER_BOOK_DEPTH = Gauge(
    "order_book_depth",
    "Current order book depth",
    ["symbol", "side"],
)

SPREAD_BPS = Gauge(
    "spread_bps",
    "Current bid-ask spread in basis points",
    ["symbol"],
)

# Reconciliation metrics
RECONCILIATION_RUNS_TOTAL = Counter(
    "reconciliation_runs_total",
    "Total reconciliation runs",
    ["venue", "symbol", "status"],
)

RECONCILIATION_ISSUES_TOTAL = Counter(
    "reconciliation_issues_total",
    "Total reconciliation issues found",
    ["venue", "issue_type"],
)


class MetricsExporter:
    """Exporter for Prometheus metrics."""

    @staticmethod
    def get_metrics() -> tuple[str, str]:
        """Get current metrics in Prometheus text format.

        Returns:
            Tuple of (metrics_data, content_type)
        """
        return generate_latest().decode("utf-8"), CONTENT_TYPE_LATEST

    @staticmethod
    def increment_bot_trades(
        bot_type: str,
        bot_instance_id: str,
        symbol: str,
        side: str,
    ) -> None:
        """Increment bot trades counter.

        Args:
            bot_type: Type of bot (e.g., "neat_swing")
            bot_instance_id: Bot instance ID
            symbol: Trading symbol
            side: Trade side (buy/sell)
        """
        BOT_TRADES_TOTAL.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
            symbol=symbol,
            side=side.lower(),
        ).inc()

    @staticmethod
    def increment_bot_heartbeat(
        bot_type: str,
        bot_instance_id: str,
    ) -> None:
        """Increment bot heartbeat counter.

        Args:
            bot_type: Type of bot
            bot_instance_id: Bot instance ID
        """
        BOT_HEARTBEAT_TOTAL.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
        ).inc()

    @staticmethod
    def set_bot_equity(
        bot_type: str,
        bot_instance_id: str,
        equity_usd: float,
    ) -> None:
        """Set bot equity gauge.

        Args:
            bot_type: Type of bot
            bot_instance_id: Bot instance ID
            equity_usd: Current equity in USD
        """
        BOT_EQUITY_USD.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
        ).set(equity_usd)

    @staticmethod
    def set_bot_position(
        bot_type: str,
        bot_instance_id: str,
        symbol: str,
        quantity: float,
    ) -> None:
        """Set bot position quantity gauge.

        Args:
            bot_type: Type of bot
            bot_instance_id: Bot instance ID
            symbol: Trading symbol
            quantity: Position quantity
        """
        BOT_POSITION_QUANTITY.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
            symbol=symbol,
        ).set(quantity)

    @staticmethod
    def set_bot_drawdown(
        bot_type: str,
        bot_instance_id: str,
        drawdown_pct: float,
    ) -> None:
        """Set bot drawdown percentage gauge.

        Args:
            bot_type: Type of bot
            bot_instance_id: Bot instance ID
            drawdown_pct: Current drawdown percentage (0-100)
        """
        BOT_DRAWDOWN_PCT.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
        ).set(drawdown_pct)

    @staticmethod
    def set_db_health(db_type: str, healthy: bool) -> None:
        """Set database health gauge.

        Args:
            db_type: Database type (postgres, duckdb)
            healthy: True if healthy, False otherwise
        """
        DB_CONNECTION_HEALTH.labels(db_type=db_type).set(1 if healthy else 0)

    @staticmethod
    def observe_trade_latency(
        bot_type: str,
        bot_instance_id: str,
        venue: str,
        latency_ms: float,
    ) -> None:
        """Observe trade execution latency.

        Args:
            bot_type: Type of bot
            bot_instance_id: Bot instance ID
            venue: Exchange venue
            latency_ms: Latency in milliseconds
        """
        TRADE_LATENCY_MS.labels(
            bot_type=bot_type,
            bot_instance_id=bot_instance_id,
            venue=venue,
        ).observe(latency_ms)
