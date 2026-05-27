"""FastAPI application factory — top-level entry point for all domains.

Future domains register their routers here (e.g. domains.portfolio.routes).
"""

from contextlib import asynccontextmanager

import uvicorn
from aerich import Command
from fastapi import FastAPI
from fastapi.responses import Response
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from stonks_trading.domains.backtesting.routes import router as backtest_router
from stonks_trading.domains.botcontrol.routes import get_botcontrol_router
from stonks_trading.domains.capital.routes import get_capital_router
from stonks_trading.domains.health.routes import get_health_router
from stonks_trading.domains.reconciliation.routes import get_reconciliation_router
from stonks_trading.domains.trading.routes import get_trading_router
from stonks_trading.domains.training.routes import router as training_router
from stonks_trading.shared.config import settings
from stonks_trading.shared.database import TORTOISE_ORM
from stonks_trading.shared.logger import logger
from stonks_trading.shared.metrics import MetricsExporter
from stonks_trading.shared.websocket_api import get_websocket_router


async def init_database() -> None:
    """Initialize database with migrations on startup.

    This function:
    1. Checks database connectivity
    2. Runs Aerich migrations if migration table exists
    3. Generates schemas for fresh databases (development mode)
    """
    try:
        # Initialize Tortoise connection
        await Tortoise.init(config=TORTOISE_ORM)

        # Check database connection
        conn = Tortoise.get_connection("default")
        await conn.execute_query("SELECT 1")
        logger.info("Database connection established")

        # Check if Aerich migration table exists - try/catch to handle fresh DB
        try:
            query_result = await conn.execute_query(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'aerich')"
            )
            # ExecuteQueryResult: (rows, description) where rows is list of tuples
            rows, _ = query_result if isinstance(query_result, tuple) else (query_result, None)
            if rows and len(rows) > 0:
                aerich_exists = (
                    bool(rows[0][0]) if isinstance(rows[0], (list, tuple)) else bool(rows[0])
                )
            else:
                aerich_exists = False
        except Exception as e:
            logger.warning(f"Could not check aerich table: {e}")
            aerich_exists = False

        if aerich_exists:
            # Run pending migrations using Aerich
            logger.info("Running database migrations...")
            command = Command(tortoise_config=TORTOISE_ORM, app="models")
            await command.init()
            await command.upgrade(run_in_transaction=True)
            logger.info("Database migrations completed")
        else:
            # Fresh database - generate schemas (development only)
            logger.warning(
                "No migration history found. Generating schemas from models. "
                "For production, use 'aerich init' and 'aerich migrate' first."
            )
            await Tortoise.generate_schemas()
            logger.info("Database schemas generated")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        await Tortoise.close_connections()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles startup database initialization and shutdown cleanup.
    """
    logger.info("Starting up API server...")
    await init_database()
    yield
    logger.info("Shutting down API server...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Stonks Trading API",
        description="NEAT-based crypto trading system API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Health monitoring router (Phase 9A)
    # Includes /health, /health/ready, /health/bots, /health/heartbeat
    app.include_router(get_health_router())

    # Metrics endpoint (Phase 9D)
    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        data, content_type = MetricsExporter.get_metrics()
        return Response(content=data, media_type=content_type)

    # Domain routers
    app.include_router(get_trading_router(), prefix="/api/v1", tags=["trading"])
    app.include_router(training_router, prefix="/api/v1", tags=["training"])
    app.include_router(backtest_router, prefix="/api/v1", tags=["backtesting"])
    # Reconciliation router (Phase 9C)
    app.include_router(
        get_reconciliation_router(),
        prefix="/api/v1",
        tags=["reconciliation"],
    )
    # Bot Control router (Phase 9F)
    app.include_router(
        get_botcontrol_router(),
        prefix="/api/v1",
        tags=["bot-control"],
    )
    # Capital Management router (Phase 10F)
    app.include_router(
        get_capital_router(),
        prefix="/api/v1",
        tags=["capital"],
    )
    # WebSocket router (Phase 10E)
    app.include_router(get_websocket_router(), tags=["websocket"])

    # Register Tortoise ORM
    # generate_schemas=False because we handle initialization in lifespan
    register_tortoise(
        app,
        config=TORTOISE_ORM,
        generate_schemas=False,
        add_exception_handlers=True,
    )

    return app


app = create_app()


def main() -> None:
    """CLI entry point."""
    uvicorn.run(
        "stonks_trading.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
