"""Unit tests for config module."""

import pytest

from stonks_trading.shared.config import Settings, settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_settings_has_defaults(self):
        """Settings has expected default values."""
        s = Settings()

        assert s.mode == "dry_run"
        assert s.initial_capital == 10000.0
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.live_data_ttl_seconds == 3600

    def test_settings_database_defaults(self):
        """Database settings have expected defaults."""
        s = Settings()

        assert "postgres" in s.database_url

    def test_settings_neat_defaults(self):
        """NEAT settings have expected defaults."""
        s = Settings()

        assert s.generations == 30
        assert s.pop_size == 150
        assert s.decision_threshold == 0.6
        assert s.min_trade_interval == 15

    def test_settings_risk_defaults(self):
        """Risk settings have expected defaults."""
        s = Settings()

        assert s.max_position_pct == 0.95
        assert s.max_drawdown_pct == 0.15
        assert s.max_trades_per_day == 40

    def test_settings_api_defaults(self):
        """API settings have expected defaults."""
        s = Settings()

        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000

    def test_settings_logging_defaults(self):
        """Logging settings have expected defaults."""
        s = Settings()

        assert s.log_level == "INFO"
        assert s.log_format == "console"
        assert s.debug is False


class TestGlobalSettings:
    """Tests for global settings instance."""

    def test_global_settings_exists(self):
        """Global settings instance exists."""
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_global_settings_has_expected_values(self):
        """Global settings has expected values."""
        assert settings.redis_url is not None
        assert settings.initial_capital == 10000.0
