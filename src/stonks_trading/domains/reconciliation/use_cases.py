"""Use cases for reconciliation domain.

Orchestration layer - coordinates repositories, services, and adapters.
No business logic here - pure coordination.
"""

import uuid
from datetime import datetime
from typing import Any

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationReport,
    ReconciliationThresholds,
    VenueStatement,
)
from stonks_trading.domains.reconciliation.repositories import (
    get_reconciliation_report,
    list_reconciliation_diffs_by_report,
    list_reconciliation_reports,
    list_unreconciled_trades,
    save_reconciliation_diffs,
    save_reconciliation_report,
)
from stonks_trading.domains.reconciliation.services import (
    ReconciliationEngine,
    ReconciliationSummaryCalculator,
)
from stonks_trading.domains.trading.adapters import IExchangeAdapter
from stonks_trading.domains.trading.value_objects import BotContext, Symbol
from stonks_trading.shared.logger import logger
from stonks_trading.shared.notifications import DiscordNotifier


class ReconcileVenueStatementsUseCase:
    """Reconcile internal trade records with exchange venue history.

    Business Logic:
    1. Fetch internal trades for symbol/time range from repository
    2. Fetch venue statements via adapter get_my_trades()
    3. Normalize venue data to VenueStatement entities
    4. Match trades using ReconciliationEngine
    5. Categorize as MATCHED, MISMATCH, MISSING_INTERNAL, MISSING_VENUE
    6. Save report and diffs to repository
    7. Send Discord alert if mismatch count exceeds threshold
    """

    def __init__(
        self,
        adapter: IExchangeAdapter,
        notifier: DiscordNotifier | None = None,
        thresholds: ReconciliationThresholds | None = None,
        alert_threshold: int = 5,
    ):
        """Initialize use case with dependencies.

        Args:
            adapter: Exchange adapter for fetching venue trades
            notifier: Discord notifier for alerts (optional)
            thresholds: Reconciliation tolerance thresholds
            alert_threshold: Number of mismatches before sending alert
        """
        self.adapter = adapter
        self.notifier = notifier
        self.thresholds = thresholds or ReconciliationThresholds()
        self.alert_threshold = alert_threshold
        self.engine = ReconciliationEngine(self.thresholds)

    async def execute(
        self,
        venue: str,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        bot_context: BotContext | None = None,
    ) -> ReconciliationReport:
        """Execute reconciliation for a symbol and time range.

        Args:
            venue: Exchange venue (e.g., "binance")
            symbol: Trading symbol (e.g., "BTCUSDT", "BTC_USD")
            start_time: Start of reconciliation window
            end_time: End of reconciliation window
            bot_context: Optional bot context for notifications

        Returns:
            ReconciliationReport with results
        """
        run_id = f"recon_{venue}_{symbol}_{uuid.uuid4().hex[:8]}"

        logger.info(
            "Starting reconciliation",
            run_id=run_id,
            venue=venue,
            symbol=symbol,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        # 1. Fetch internal trades
        try:
            internal_trades = await list_unreconciled_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                venue=venue,
            )
            logger.info(
                "Fetched internal trades",
                run_id=run_id,
                count=len(internal_trades),
            )
        except Exception as e:
            logger.error(
                "Failed to fetch internal trades",
                run_id=run_id,
                error=str(e),
            )
            raise

        # 2. Fetch venue statements
        try:
            venue_statements = await self._fetch_venue_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
            logger.info(
                "Fetched venue statements",
                run_id=run_id,
                count=len(venue_statements),
            )
        except Exception as e:
            logger.error(
                "Failed to fetch venue statements",
                run_id=run_id,
                error=str(e),
            )
            # Create report with error
            report = ReconciliationReport(
                run_id=run_id,
                venue=venue,
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                total_internal=len(internal_trades),
                total_venue=0,
            )
            await save_reconciliation_report(report)
            raise

        # 3. Match trades using engine
        diffs = self.engine.find_matches(internal_trades, venue_statements)

        # 4. Calculate summary
        summary = ReconciliationSummaryCalculator.calculate(diffs)

        # 5. Create report
        report = ReconciliationReport(
            run_id=run_id,
            venue=venue,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            total_internal=len(internal_trades),
            total_venue=len(venue_statements),
            matched=summary["matched"],
            mismatches=summary["mismatches"],
            missing_internal=summary["missing_internal"],
            missing_venue=summary["missing_venue"],
            diffs=diffs,
        )

        # 6. Save report and diffs
        await save_reconciliation_report(report)
        await save_reconciliation_diffs(run_id, diffs)

        logger.info(
            "Reconciliation complete",
            run_id=run_id,
            matched=report.matched,
            mismatches=report.mismatches,
            missing_internal=report.missing_internal,
            missing_venue=report.missing_venue,
            is_clean=report.is_clean,
        )

        # 7. Send alert if threshold breached
        if summary["total_issues"] >= self.alert_threshold:
            await self._send_alert(report, bot_context)

        return report

    async def _fetch_venue_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[VenueStatement]:
        """Fetch trades from exchange venue.

        Args:
            symbol: Trading symbol
            start_time: Start time
            end_time: End time

        Returns:
            List of VenueStatement entities
        """
        # Convert to Symbol value object
        symbol_vo = Symbol(value=symbol)

        # Call adapter
        raw_trades = await self.adapter.get_my_trades(
            symbol=symbol_vo,
            start_time=start_time,
            end_time=end_time,
        )

        # Convert to VenueStatement entities
        statements: list[VenueStatement] = []
        for trade in raw_trades:
            if isinstance(trade, VenueStatement):
                statements.append(trade)
            elif isinstance(trade, dict):
                # Parse from dict (Binance format)
                statements.append(self._parse_venue_statement(trade))

        return statements

    def _parse_venue_statement(self, data: dict[str, Any]) -> VenueStatement:
        """Parse venue statement from exchange API response.

        Supports Binance myTrades format:
        {
            "id": 28457,
            "symbol": "BTCUSDT",
            "orderId": 100234,
            "price": "4.00000100",
            "qty": "12.00000000",
            "commission": "10.10000000",
            "commissionAsset": "USDT",
            "time": 1499865549590,
            "isBuyer": true,
            "isMaker": false,
            "isBestMatch": true
        }
        """
        # Parse timestamp (milliseconds to datetime)
        timestamp_ms = data.get("time", 0)
        timestamp = datetime.utcfromtimestamp(timestamp_ms / 1000.0)

        # Parse side
        is_buyer = data.get("isBuyer", True)
        side = "buy" if is_buyer else "sell"

        return VenueStatement(
            venue_trade_id=str(data.get("id", 0)),
            symbol=data.get("symbol", ""),
            side=side,
            price=float(data.get("price", 0)),
            quantity=float(data.get("qty", 0)),
            fee=float(data.get("commission", 0)),
            fee_currency=data.get("commissionAsset", "USDT"),
            timestamp=timestamp,
            venue="binance",
            order_id=str(data.get("orderId")) if data.get("orderId") else None,
            commission=float(data.get("commission", 0)),
            commission_asset=data.get("commissionAsset"),
            is_maker=data.get("isMaker"),
        )

    async def _send_alert(
        self,
        report: ReconciliationReport,
        bot_context: BotContext | None = None,
    ) -> None:
        """Send Discord alert for reconciliation issues."""
        if not self.notifier:
            return

        try:
            # Build context-aware notifier
            notifier = self.notifier
            if bot_context:
                notifier = notifier.with_bot_context(
                    bot_type=bot_context.bot_type,
                    instance_id=bot_context.instance_id,
                )

            await notifier.send_reconciliation_alert(
                report=report,
                threshold=self.alert_threshold,
            )
        except Exception as e:
            logger.error(
                "Failed to send reconciliation alert",
                run_id=report.run_id,
                error=str(e),
            )


class GetReconciliationReportUseCase:
    """Get a reconciliation report by run_id."""

    async def execute(self, run_id: str) -> ReconciliationReport | None:
        """Get report with all diffs.

        Args:
            run_id: Unique run identifier

        Returns:
            ReconciliationReport or None if not found
        """
        report = await get_reconciliation_report(run_id)
        if not report:
            return None

        # Load diffs
        diffs = await list_reconciliation_diffs_by_report(run_id)
        report.diffs = diffs

        return report


class ListReconciliationReportsUseCase:
    """List reconciliation reports with optional filtering."""

    async def execute(
        self,
        venue: str | None = None,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReconciliationReport]:
        """List reports.

        Args:
            venue: Filter by venue
            symbol: Filter by symbol
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of ReconciliationReports
        """
        return await list_reconciliation_reports(
            venue=venue,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )
