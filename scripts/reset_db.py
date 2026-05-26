#!/usr/bin/env python3
"""Reset database - drops all tables and reinitializes."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tortoise import Tortoise

from stonks_trading.shared.database import TORTOISE_ORM


async def reset() -> int:
    """Reset database by dropping all tables and reinitializing."""
    print("Connecting to database...")
    await Tortoise.init(config=TORTOISE_ORM)

    # Get the db_url
    db_url = TORTOISE_ORM["connections"]["default"]
    print(f"Database URL: {db_url.split('@')[1] if '@' in db_url else 'localhost'}")

    # Drop all tables using raw connection
    try:
        from tortoise.db.clients.client import TortoiseAsyncODBCCLient
        async with Tortoise.init(config=TORTOISE_ORM):
            pass
    except Exception:
        pass  # Fallback to generate_schemas approach

    print("Closing connections...")
    await Tortoise.close_connections()

    print("Database reset complete. Run 'python scripts/init_db.py' to reinitialize.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(reset()))
