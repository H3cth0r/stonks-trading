"""pytest configuration for domain trading tests.

Sets up an in-memory SQLite database for repository and use-case tests
so they can run in CI without a PostgreSQL service.
"""

import contextlib
from collections.abc import AsyncGenerator

import pytest
from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError


@pytest.fixture(scope="function", autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Initialize Tortoise with in-memory SQLite for each test."""
    with contextlib.suppress(ConfigurationError):
        await Tortoise.close_connections()
    await Tortoise._reset_apps()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["stonks_trading.shared.postgres_models"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
