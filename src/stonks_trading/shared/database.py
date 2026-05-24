"""Database connection management for Tortoise ORM.

Provides database configuration and connection handling.
"""

from tortoise import Tortoise

from stonks_trading.shared.config import settings

# Tortoise ORM expects "postgres://" not "postgresql://"
_DATABASE_URL = settings.database_url
if _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = "postgres://" + _DATABASE_URL.removeprefix("postgresql://")

TORTOISE_ORM = {
    "connections": {
        "default": _DATABASE_URL,
    },
    "apps": {
        "models": {
            "models": [
                "stonks_trading.shared.postgres_models",
                "aerich.models",
            ],
            "default_connection": "default",
        },
    },
}


async def init_db() -> None:
    """Initialize database connection."""
    await Tortoise.init(config=TORTOISE_ORM)


async def close_db() -> None:
    """Close database connection."""
    await Tortoise.close_connections()


async def generate_schemas() -> None:
    """Generate database schemas (for development only)."""
    await Tortoise.generate_schemas()
