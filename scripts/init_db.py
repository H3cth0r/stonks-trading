#!/usr/bin/env python3
"""Initialize database with Aerich migrations."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tortoise import Tortoise

from stonks_trading.shared.database import TORTOISE_ORM


async def init() -> int:
    """Initialize database connection and create schemas."""
    print("Initializing database connection...")
    await Tortoise.init(config=TORTOISE_ORM)
    print("Generating database schemas...")
    await Tortoise.generate_schemas()
    print("Database initialized successfully!")
    await Tortoise.close_connections()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(init()))
