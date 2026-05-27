"""Unit tests for metrics module."""

import pytest

from stonks_trading.shared.metrics import MetricsExporter


class TestMetricsExporter:
    """Tests for MetricsExporter."""

    def test_get_metrics_returns_tuple(self):
        """get_metrics returns (data, content_type) tuple."""
        data, content_type = MetricsExporter.get_metrics()

        assert isinstance(data, str)
        assert isinstance(content_type, str)
        assert "text" in content_type or "openmetrics" in content_type

    def test_increment_bot_trades(self):
        """increment_bot_trades increments counter."""
        # Should not raise
        MetricsExporter.increment_bot_trades(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            symbol="BTC_USD",
            side="buy",
        )

    def test_increment_bot_heartbeat(self):
        """increment_bot_heartbeat increments counter."""
        MetricsExporter.increment_bot_heartbeat(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
        )

    def test_set_bot_equity(self):
        """set_bot_equity sets gauge."""
        MetricsExporter.set_bot_equity(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            equity_usd=15000.0,
        )

    def test_set_bot_position(self):
        """set_bot_position sets gauge."""
        MetricsExporter.set_bot_position(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            symbol="BTC_USD",
            quantity=0.5,
        )

    def test_set_bot_drawdown(self):
        """set_bot_drawdown sets gauge."""
        MetricsExporter.set_bot_drawdown(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            drawdown_pct=5.5,
        )

    def test_set_db_health_healthy(self):
        """set_db_health sets gauge to 1 when healthy."""
        MetricsExporter.set_db_health(db_type="duckdb", healthy=True)

    def test_set_db_health_unhealthy(self):
        """set_db_health sets gauge to 0 when unhealthy."""
        MetricsExporter.set_db_health(db_type="postgres", healthy=False)

    def test_observe_trade_latency(self):
        """observe_trade_latency observes histogram."""
        MetricsExporter.observe_trade_latency(
            bot_type="neat_swing",
            bot_instance_id="bot_1",
            venue="binance",
            latency_ms=150.5,
        )
