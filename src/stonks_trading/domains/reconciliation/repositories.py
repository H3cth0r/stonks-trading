"""Repository functions for reconciliation domain.

Standalone functions (no classes, no ABC, no inheritance).
All data access only - no business logic.
"""

from datetime import datetime

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationReport,
    ReconciliationStatus,
)
from stonks_trading.domains.trading.entities import Trade
from stonks_trading.domains.trading.enums import Side, TradingMode
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.postgres_models import (
    ReconciliationDiffModel,
    ReconciliationReportModel,
    TradeModel,
)

# =============================================================================
# Reconciliation Report Repository Functions
# =============================================================================


async def save_reconciliation_report(report: ReconciliationReport) -> ReconciliationReport:
    """Persist reconciliation report to database."""
    model = await ReconciliationReportModel.create(
        run_id=report.run_id,
        venue=report.venue,
        symbol=report.symbol,
        start_time=report.start_time,
        end_time=report.end_time,
        total_internal=report.total_internal,
        total_venue=report.total_venue,
        matched=report.matched,
        mismatches=report.mismatches,
        missing_internal=report.missing_internal,
        missing_venue=report.missing_venue,
    )
    report.created_at = model.created_at
    return report


async def get_reconciliation_report(run_id: str) -> ReconciliationReport | None:
    """Retrieve reconciliation report by run_id."""
    model = await ReconciliationReportModel.get_or_none(run_id=run_id)
    if not model:
        return None
    return await _model_to_report(model)


async def list_reconciliation_reports(
    venue: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ReconciliationReport]:
    """List reconciliation reports with optional filtering."""
    query = ReconciliationReportModel.all()

    if venue:
        query = query.filter(venue=venue)
    if symbol:
        query = query.filter(symbol=symbol)

    models = await query.order_by("-created_at").offset(offset).limit(limit)
    return [await _model_to_report(m) for m in models]


async def _model_to_report(model: ReconciliationReportModel) -> ReconciliationReport:
    """Convert ReconciliationReportModel to ReconciliationReport entity."""
    # Load diffs if they exist
    diffs = []
    if hasattr(model, "diffs"):
        diff_models = await model.diffs.all()
        diffs = [_model_to_diff(d) for d in diff_models]

    return ReconciliationReport(
        run_id=model.run_id,
        venue=model.venue,
        symbol=model.symbol,
        start_time=model.start_time,
        end_time=model.end_time,
        total_internal=model.total_internal,
        total_venue=model.total_venue,
        matched=model.matched,
        mismatches=model.mismatches,
        missing_internal=model.missing_internal,
        missing_venue=model.missing_venue,
        created_at=model.created_at,
        diffs=diffs,
    )


# =============================================================================
# Reconciliation Diff Repository Functions
# =============================================================================


async def save_reconciliation_diff(
    report_run_id: str,
    diff: ReconciliationDiff,
) -> ReconciliationDiff:
    """Persist a single reconciliation diff."""
    # First get the report model
    report_model = await ReconciliationReportModel.get_or_none(run_id=report_run_id)
    if not report_model:
        raise ValueError(f"Report {report_run_id} not found")

    await ReconciliationDiffModel.create(
        report=report_model,
        status=diff.status.value,
        internal_trade_id=diff.internal_trade_id,
        venue_trade_id=diff.venue_trade_id,
        field_differences=diff.field_differences,
        symbol=diff.symbol,
        side=diff.side,
        internal_price=diff.internal_price,
        venue_price=diff.venue_price,
        internal_quantity=diff.internal_quantity,
        venue_quantity=diff.venue_quantity,
        internal_timestamp=diff.internal_timestamp,
        venue_timestamp=diff.venue_timestamp,
    )
    return diff


async def save_reconciliation_diffs(
    report_run_id: str,
    diffs: list[ReconciliationDiff],
) -> None:
    """Persist multiple reconciliation diffs for a report."""
    for diff in diffs:
        await save_reconciliation_diff(report_run_id, diff)


async def list_reconciliation_diffs_by_report(
    report_run_id: str,
) -> list[ReconciliationDiff]:
    """List all diffs for a specific reconciliation report."""
    report_model = await ReconciliationReportModel.get_or_none(run_id=report_run_id)
    if not report_model:
        return []

    diff_models = await ReconciliationDiffModel.filter(report=report_model).order_by("-created_at")
    return [_model_to_diff(m) for m in diff_models]


def _model_to_diff(model: ReconciliationDiffModel) -> ReconciliationDiff:
    """Convert ReconciliationDiffModel to ReconciliationDiff entity."""
    return ReconciliationDiff(
        status=ReconciliationStatus(model.status),
        internal_trade_id=model.internal_trade_id,
        venue_trade_id=model.venue_trade_id,
        field_differences=model.field_differences or {},
        symbol=model.symbol,
        side=model.side,
        internal_price=model.internal_price,
        venue_price=model.venue_price,
        internal_quantity=model.internal_quantity,
        venue_quantity=model.venue_quantity,
        internal_timestamp=model.internal_timestamp,
        venue_timestamp=model.venue_timestamp,
    )


# =============================================================================
# Trade Repository Functions (Reconciliation-specific)
# =============================================================================


async def list_unreconciled_trades(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    venue: str = "binance",
) -> list[Trade]:
    """List internal trades that should be reconciled against venue.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        start_time: Start of time range
        end_time: End of time range
        venue: Exchange venue (affects symbol format)

    Returns:
        List of Trade entities within the time range
    """
    query = TradeModel.filter(
        symbol=symbol,
        created_at__gte=start_time,
        created_at__lte=end_time,
    ).order_by("created_at")

    models = await query
    return [_trade_model_to_entity(m) for m in models]


def _trade_model_to_entity(model: TradeModel) -> Trade:
    """Convert TradeModel to Trade entity."""
    return Trade(
        id=model.id,
        symbol=Symbol(value=model.symbol),
        side=Side(model.side.value),
        fill_price=Money(amount=model.fill_price, currency=model.fee_currency),
        quantity=model.quantity,
        fee=Money(amount=model.fee, currency=model.fee_currency),
        fee_currency=model.fee_currency,
        realized_pnl=Money(amount=model.realized_pnl, currency=model.fee_currency)
        if model.realized_pnl
        else None,
        order_id=model.order_id,
        created_at=model.created_at,
        mode=TradingMode(model.mode.value),
        bot_type=model.bot_type,
        bot_instance_id=model.bot_instance_id,
        intended_price=Money(amount=model.intended_price, currency=model.fee_currency)
        if model.intended_price
        else None,
        slippage_bps=model.slippage_bps,
        quote_quantity=model.quote_quantity,
        fee_rate=model.fee_rate,
        genome_id=model.genome_id,
        entry_price=Money(amount=model.entry_price, currency=model.fee_currency)
        if model.entry_price
        else None,
        latency_ms=model.latency_ms,
        exchange=model.exchange,
        strategy=model.strategy,
    )
