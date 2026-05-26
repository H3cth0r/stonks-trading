"""Pydantic settings for application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgres://user:pass@localhost/stonks_trading"

    # Redis (Phase 10A - live visualization infrastructure)
    redis_url: str = "redis://localhost:6379/0"
    live_data_ttl_seconds: int = 3600
    equity_history_max_points: int = 10000

    # Trading
    mode: str = "dry_run"  # "backtest", "dry_run", "live"
    symbols: str = "BTCUSDT,ETHUSDT,XRPUSDT"
    initial_capital: float = 10000.0

    # NEAT Configuration (MUST match NEAT/main.py defaults)
    transaction_fee: float = 0.001  # Default fee rate (0.1%)
    generations: int = 30
    pop_size: int = 150
    episode_steps: int = 20160
    decision_threshold: float = 0.6
    min_trade_interval: int = 15  # minutes

    # Reward Weights (Srivastava et al. adapted)
    w_return: float = 1.0
    w_risk: float = 0.5
    w_diff: float = 3.0
    w_treynor: float = 1.0

    # Risk Management
    max_position_pct: float = 0.95
    max_drawdown_pct: float = 0.15
    max_trades_per_day: int = 40

    # Notifications
    discord_webhook_url: str = ""

    # Exchange API (Binance)
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_base_url: str = "https://api.binance.com"

    # Exchange API (Bitso)
    bitso_api_key: str = ""
    bitso_api_secret: str = ""

    # Storage (Tigris S3)
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "stonks-trading-data"

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"  # "json" or "console"

    # Development
    debug: bool = False


# Global settings instance
settings = Settings()
