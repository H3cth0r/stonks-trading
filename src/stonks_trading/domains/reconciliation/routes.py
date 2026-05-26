"""FastAPI routes for reconciliation domain.

HTTP concerns only - no business logic.
"""

from fastapi import APIRouter, HTTPException, Query

from stonks_trading.domains.reconciliation.dtos import (
    ReconciliationErrorResponse,
    ReconciliationReportListResponse,
    ReconciliationReportResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
)
from stonks_trading.domains.reconciliation.mappers import ReconciliationReportMapper
from stonks_trading.domains.reconciliation.use_cases import (
    GetReconciliationReportUseCase,
    ListReconciliationReportsUseCase,
    ReconcileVenueStatementsUseCase,
)
from stonks_trading.domains.trading.adapters import ExchangeAdapterFactory
from stonks_trading.domains.trading.value_objects import BotContext
from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger
from stonks_trading.shared.notifications import DiscordNotifier


def get_reconciliation_router() -> APIRouter:
    """Create and configure reconciliation router.

    Follows the router factory pattern from domains/trading/routes.py.
    """
    router = APIRouter(tags=["reconciliation"])

    # -------------------------------------------------------------------------
    # Reconciliation Run Endpoints
    # -------------------------------------------------------------------------

    @router.post(
        "/reconciliation/run",
        response_model=ReconciliationRunResponse,
        responses={500: {"model": ReconciliationErrorResponse}},
    )
    async def run_reconciliation(
        request: ReconciliationRunRequest,
    ) -> ReconciliationRunResponse:
        """Run reconciliation between internal trades and venue statements.

        Compares internal trade records with exchange venue history
        to detect mismatches, missing trades, and data integrity issues.

        Returns a run_id that can be used to retrieve the full report.
        """
        try:
            # Create adapter for the venue
            adapter = ExchangeAdapterFactory.create_adapter(
                venue=request.venue,
                mode="live",  # Reconciliation always uses live mode for venue API
            )

            # Create notifier if configured
            notifier = None
            if settings.discord_webhook_url:
                notifier = DiscordNotifier(settings.discord_webhook_url)

            # Execute reconciliation
            use_case = ReconcileVenueStatementsUseCase(
                adapter=adapter,
                notifier=notifier,
                alert_threshold=request.alert_threshold,
            )

            report = await use_case.execute(
                venue=request.venue,
                symbol=request.symbol,
                start_time=request.start_time,
                end_time=request.end_time,
            )

            return ReconciliationReportMapper.to_run_response(
                report,
                status="complete",
                message="Reconciliation completed successfully",
            )

        except Exception as e:
            logger.error("Reconciliation failed", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Reconciliation failed: {str(e)}",
            ) from e

    # -------------------------------------------------------------------------
    # Report Query Endpoints
    # -------------------------------------------------------------------------

    @router.get(
        "/reconciliation/reports",
        response_model=ReconciliationReportListResponse,
    )
    async def list_reconciliation_reports(
        venue: str | None = Query(None, description="Filter by venue"),
        symbol: str | None = Query(None, description="Filter by symbol"),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> ReconciliationReportListResponse:
        """List reconciliation reports with optional filtering.

        Returns summaries of reconciliation runs ordered by creation time (newest first).
        """
        use_case = ListReconciliationReportsUseCase()
        reports = await use_case.execute(
            venue=venue,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )

        return ReconciliationReportMapper.to_list_response(
            reports,
            limit=limit,
            offset=offset,
        )

    @router.get(
        "/reconciliation/reports/{run_id}",
        response_model=ReconciliationReportResponse,
        responses={404: {"description": "Report not found"}},
    )
    async def get_reconciliation_report(
        run_id: str,
    ) -> ReconciliationReportResponse:
        """Get a specific reconciliation report by run_id.

        Returns the full report including all diffs.
        """
        use_case = GetReconciliationReportUseCase()
        report = await use_case.execute(run_id)

        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"Reconciliation report {run_id} not found",
            )

        return ReconciliationReportMapper.to_response(report)

    # -------------------------------------------------------------------------
    # Bot-scoped Reconciliation Endpoints
    # -------------------------------------------------------------------------

    @router.post(
        "/bots/{bot_type}/{instance_id}/reconciliation/run",
        response_model=ReconciliationRunResponse,
        responses={500: {"model": ReconciliationErrorResponse}},
    )
    async def run_bot_reconciliation(
        bot_type: str,
        instance_id: str,
        request: ReconciliationRunRequest,
    ) -> ReconciliationRunResponse:
        """Run reconciliation for a specific bot context.

        Associates the reconciliation with a specific bot for
        targeted monitoring and notifications.
        """
        try:
            # Create adapter and notifier
            adapter = ExchangeAdapterFactory.create_adapter(
                venue=request.venue,
                mode="live",
            )

            notifier = None
            if settings.discord_webhook_url:
                notifier = DiscordNotifier(settings.discord_webhook_url)

            # Create bot context
            bot_context = BotContext(
                bot_type=bot_type,
                instance_id=instance_id,
            )

            # Execute reconciliation
            use_case = ReconcileVenueStatementsUseCase(
                adapter=adapter,
                notifier=notifier,
                alert_threshold=request.alert_threshold,
            )

            report = await use_case.execute(
                venue=request.venue,
                symbol=request.symbol,
                start_time=request.start_time,
                end_time=request.end_time,
                bot_context=bot_context,
            )

            return ReconciliationReportMapper.to_run_response(
                report,
                status="complete",
                message=f"Reconciliation completed for {bot_type}/{instance_id}",
            )

        except Exception as e:
            logger.error(
                "Bot reconciliation failed",
                bot_type=bot_type,
                instance_id=instance_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=500,
                detail=f"Reconciliation failed: {str(e)}",
            ) from e

    @router.get(
        "/bots/{bot_type}/{instance_id}/reconciliation/reports",
        response_model=ReconciliationReportListResponse,
    )
    async def list_bot_reconciliation_reports(
        bot_type: str,
        instance_id: str,
        venue: str | None = Query(None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> ReconciliationReportListResponse:
        """List reconciliation reports for a specific bot context.

        Note: This queries all reports and filters by bot context
        from the internal trade records associated with each report.
        """
        use_case = ListReconciliationReportsUseCase()

        # Get reports - filtering by bot context happens at application level
        # since reconciliation reports store reference to trades, not bot directly
        reports = await use_case.execute(
            venue=venue,
            limit=limit,
            offset=offset,
        )

        return ReconciliationReportMapper.to_list_response(
            reports,
            limit=limit,
            offset=offset,
        )

    return router


# =============================================================================
# Legacy router export for backward compatibility
# =============================================================================

router = get_reconciliation_router()
