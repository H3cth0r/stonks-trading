"""Mappers for reconciliation domain.

Converts between entities and DTOs.
Pure transformation - no business logic.
"""

from stonks_trading.domains.reconciliation.dtos import (
    ReconciliationDiffResponse,
    ReconciliationReportListResponse,
    ReconciliationReportResponse,
    ReconciliationReportSummary,
    ReconciliationRunResponse,
)
from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationReport,
)


class ReconciliationDiffMapper:
    """Map between ReconciliationDiff entity and DTOs."""

    @staticmethod
    def to_response(entity: ReconciliationDiff) -> ReconciliationDiffResponse:
        """Convert ReconciliationDiff entity to response DTO."""
        return ReconciliationDiffResponse(
            status=entity.status.value,
            internal_trade_id=entity.internal_trade_id,
            venue_trade_id=entity.venue_trade_id,
            field_differences=entity.field_differences,
            symbol=entity.symbol,
            side=entity.side,
            internal_price=entity.internal_price,
            venue_price=entity.venue_price,
            internal_quantity=entity.internal_quantity,
            venue_quantity=entity.venue_quantity,
            internal_timestamp=entity.internal_timestamp,
            venue_timestamp=entity.venue_timestamp,
        )

    @staticmethod
    def to_list_response(entities: list[ReconciliationDiff]) -> list[ReconciliationDiffResponse]:
        """Convert list of ReconciliationDiff entities to response DTOs."""
        return [ReconciliationDiffMapper.to_response(e) for e in entities]


class ReconciliationReportMapper:
    """Map between ReconciliationReport entity and DTOs."""

    @staticmethod
    def to_response(entity: ReconciliationReport) -> ReconciliationReportResponse:
        """Convert ReconciliationReport entity to full response DTO."""
        diffs = ReconciliationDiffMapper.to_list_response(entity.diffs) if entity.diffs else []

        return ReconciliationReportResponse(
            run_id=entity.run_id,
            venue=entity.venue,
            symbol=entity.symbol,
            start_time=entity.start_time,
            end_time=entity.end_time,
            total_internal=entity.total_internal,
            total_venue=entity.total_venue,
            matched=entity.matched,
            mismatches=entity.mismatches,
            missing_internal=entity.missing_internal,
            missing_venue=entity.missing_venue,
            total_issues=entity.total_issues,
            match_rate=entity.match_rate,
            is_clean=entity.is_clean,
            created_at=entity.created_at,
            diffs=diffs,
        )

    @staticmethod
    def to_summary(entity: ReconciliationReport) -> ReconciliationReportSummary:
        """Convert ReconciliationReport entity to summary DTO (no diffs)."""
        return ReconciliationReportSummary(
            run_id=entity.run_id,
            venue=entity.venue,
            symbol=entity.symbol,
            start_time=entity.start_time,
            end_time=entity.end_time,
            total_internal=entity.total_internal,
            total_venue=entity.total_venue,
            matched=entity.matched,
            mismatches=entity.mismatches,
            missing_internal=entity.missing_internal,
            missing_venue=entity.missing_venue,
            is_clean=entity.is_clean,
            created_at=entity.created_at,
        )

    @staticmethod
    def to_list_response(
        entities: list[ReconciliationReport],
        limit: int = 100,
        offset: int = 0,
    ) -> ReconciliationReportListResponse:
        """Convert list of ReconciliationReport entities to list response."""
        reports = [ReconciliationReportMapper.to_summary(e) for e in entities]

        return ReconciliationReportListResponse(
            reports=reports,
            total=len(reports),
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def to_run_response(
        entity: ReconciliationReport,
        status: str = "complete",
        message: str | None = None,
    ) -> ReconciliationRunResponse:
        """Convert ReconciliationReport to run response DTO."""
        return ReconciliationRunResponse(
            run_id=entity.run_id,
            venue=entity.venue,
            symbol=entity.symbol,
            start_time=entity.start_time,
            end_time=entity.end_time,
            status=status,
            total_internal=entity.total_internal,
            total_venue=entity.total_venue,
            matched=entity.matched,
            mismatches=entity.mismatches,
            missing_internal=entity.missing_internal,
            missing_venue=entity.missing_venue,
            is_clean=entity.is_clean,
            created_at=entity.created_at,
            message=message,
        )
