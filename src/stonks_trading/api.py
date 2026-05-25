"""FastAPI application factory — top-level entry point for all domains.

Future domains register their routers here (e.g. domains.portfolio.routes).
"""

from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise

from stonks_trading.domains.backtesting.routes import router as backtest_router
from stonks_trading.domains.trading.routes import get_trading_router
from stonks_trading.domains.training.routes import router as training_router
from stonks_trading.shared.config import settings
from stonks_trading.shared.database import TORTOISE_ORM


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Stonks Trading API",
        description="NEAT-based crypto trading system API",
        version="0.1.0",
    )

    # Health check (inline — no extra file needed)
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "version": "0.1.0"}

    # Domain routers
    app.include_router(get_trading_router(), prefix="/api/v1", tags=["trading"])
    app.include_router(training_router, prefix="/api/v1", tags=["training"])
    app.include_router(backtest_router, prefix="/api/v1", tags=["backtesting"])
    # Future: app.include_router(get_portfolio_router(), prefix="/api/v1", tags=["portfolio"])

    # Register Tortoise ORM
    register_tortoise(
        app,
        config=TORTOISE_ORM,
        generate_schemas=False,  # Use Aerich for migrations
        add_exception_handlers=True,
    )

    return app


app = create_app()


def main() -> None:
    """CLI entry point."""
    import uvicorn

    uvicorn.run(
        "stonks_trading.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
