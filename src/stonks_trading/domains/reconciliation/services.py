"""Service classes for reconciliation domain.

Pure business logic, no I/O operations.
All methods are deterministic and testable.
"""

from datetime import datetime
from typing import Any

from stonks_trading.domains.reconciliation.entities import (
    ReconciliationDiff,
    ReconciliationStatus,
    ReconciliationThresholds,
    VenueStatement,
)
from stonks_trading.domains.trading.entities import Trade


class ReconciliationEngine:
    """Engine for matching internal trades with venue statements.

    Implements matching logic with configurable tolerance thresholds
    for price, quantity, and timestamp differences.
    """

    def __init__(self, thresholds: ReconciliationThresholds | None = None):
        """Initialize with tolerance thresholds.

        Args:
            thresholds: Tolerance configuration (uses defaults if None)
        """
        self.thresholds = thresholds or ReconciliationThresholds()

    def match(
        self,
        internal: Trade | None,
        venue: VenueStatement | None,
    ) -> ReconciliationDiff:
        """Match internal trade with venue statement.

        Matching Rules:
        1. Both None -> error (should not happen)
        2. Internal None -> MISSING_INTERNAL
        3. Venue None -> MISSING_VENUE
        4. Both present -> check all fields within tolerance

        Args:
            internal: Internal trade record or None
            venue: Venue statement or None

        Returns:
            ReconciliationDiff with status and field differences
        """
        # Case 1: Missing internal (venue trade not recorded)
        if internal is None and venue is not None:
            return ReconciliationDiff(
                status=ReconciliationStatus.MISSING_INTERNAL,
                venue_trade_id=venue.venue_trade_id,
                symbol=venue.symbol,
                side=venue.side,
                venue_price=venue.price,
                venue_quantity=venue.quantity,
                venue_timestamp=venue.timestamp,
            )

        # Case 2: Missing venue (internal trade not found at venue)
        if internal is not None and venue is None:
            return ReconciliationDiff(
                status=ReconciliationStatus.MISSING_VENUE,
                internal_trade_id=internal.id,
                symbol=internal.symbol.value,
                side=internal.side.value,
                internal_price=internal.fill_price.amount,
                internal_quantity=internal.quantity,
                internal_timestamp=internal.created_at,
            )

        # Case 3: Both present - compare fields
        if internal is not None and venue is not None:
            return self._compare_trades(internal, venue)

        # Should never reach here
        raise ValueError("Both internal and venue trades are None")

    def _compare_trades(
        self,
        internal: Trade,
        venue: VenueStatement,
    ) -> ReconciliationDiff:
        """Compare two matched trades for field differences."""
        field_differences: dict[str, tuple[Any, Any]] = {}

        # Compare price
        price_match = self.thresholds.is_price_match(
            internal.fill_price.amount,
            venue.price,
        )
        if not price_match:
            field_differences["price"] = (internal.fill_price.amount, venue.price)

        # Compare quantity
        qty_match = self.thresholds.is_quantity_match(
            internal.quantity,
            venue.quantity,
        )
        if not qty_match:
            field_differences["quantity"] = (internal.quantity, venue.quantity)

        # Compare timestamp
        if internal.created_at and venue.timestamp:
            time_match = self.thresholds.is_time_match(
                internal.created_at,
                venue.timestamp,
            )
            if not time_match:
                field_differences["timestamp"] = (
                    internal.created_at.isoformat(),
                    venue.timestamp.isoformat(),
                )
        else:
            field_differences["timestamp"] = (
                internal.created_at.isoformat() if internal.created_at else None,
                venue.timestamp.isoformat() if venue.timestamp else None,
            )

        # Compare side
        internal_side = internal.side.value.lower()
        venue_side = venue.side.lower()
        if internal_side != venue_side:
            field_differences["side"] = (internal_side, venue_side)

        # Determine status
        if field_differences:
            status = ReconciliationStatus.MISMATCH
        else:
            status = ReconciliationStatus.MATCHED

        return ReconciliationDiff(
            status=status,
            internal_trade_id=internal.id,
            venue_trade_id=venue.venue_trade_id,
            field_differences=field_differences,
            symbol=internal.symbol.value,
            side=internal.side.value,
            internal_price=internal.fill_price.amount,
            venue_price=venue.price,
            internal_quantity=internal.quantity,
            venue_quantity=venue.quantity,
            internal_timestamp=internal.created_at,
            venue_timestamp=venue.timestamp,
        )

    def find_matches(
        self,
        internal_trades: list[Trade],
        venue_statements: list[VenueStatement],
    ) -> list[ReconciliationDiff]:
        """Find matches between lists of internal trades and venue statements.

        Uses a greedy matching algorithm based on timestamp proximity.

        Args:
            internal_trades: List of internal trade records
            venue_statements: List of venue statements

        Returns:
            List of ReconciliationDiffs representing all matches
        """
        diffs: list[ReconciliationDiff] = []

        # Sort both lists by timestamp
        sorted_internal = sorted(
            internal_trades,
            key=lambda t: t.created_at or datetime.min,
        )
        sorted_venue = sorted(venue_statements, key=lambda v: v.timestamp)

        # Track matched items
        matched_internal: set[int] = set()
        matched_venue: set[str] = set()

        # First pass: Find matches within time tolerance
        for internal in sorted_internal:
            for venue in sorted_venue:
                if venue.venue_trade_id in matched_venue:
                    continue

                # Check if within time tolerance and side matches
                if (
                    internal.id
                    and internal.created_at
                    and venue.timestamp
                    and abs((internal.created_at - venue.timestamp).total_seconds())
                    <= self.thresholds.time_tolerance_seconds
                    and internal.side.value.lower() == venue.side.lower()
                ):
                    # Found a match - compare in detail
                    diff = self._compare_trades(internal, venue)
                    diffs.append(diff)
                    matched_internal.add(internal.id)
                    matched_venue.add(venue.venue_trade_id)
                    break

        # Second pass: Mark unmatched internal trades as MISSING_VENUE
        for internal in sorted_internal:
            if internal.id not in matched_internal:
                diffs.append(
                    ReconciliationDiff(
                        status=ReconciliationStatus.MISSING_VENUE,
                        internal_trade_id=internal.id,
                        symbol=internal.symbol.value,
                        side=internal.side.value,
                        internal_price=internal.fill_price.amount,
                        internal_quantity=internal.quantity,
                        internal_timestamp=internal.created_at,
                    )
                )

        # Third pass: Mark unmatched venue statements as MISSING_INTERNAL
        for venue in sorted_venue:
            if venue.venue_trade_id not in matched_venue:
                diffs.append(
                    ReconciliationDiff(
                        status=ReconciliationStatus.MISSING_INTERNAL,
                        venue_trade_id=venue.venue_trade_id,
                        symbol=venue.symbol,
                        side=venue.side,
                        venue_price=venue.price,
                        venue_quantity=venue.quantity,
                        venue_timestamp=venue.timestamp,
                    )
                )

        return diffs


class DifferenceCalculator:
    """Calculate and format differences between matched trades."""

    @staticmethod
    def calculate(
        internal: Trade,
        venue: VenueStatement,
    ) -> dict[str, dict[str, Any]]:
        """Calculate detailed differences between trades.

        Returns a dictionary with field names and their values
        from both sources, plus computed differences.
        """
        differences: dict[str, dict[str, Any]] = {}

        # Price difference
        if internal.fill_price and venue.price:
            price_diff = internal.fill_price.amount - venue.price
            price_diff_pct = (price_diff / venue.price * 100) if venue.price != 0 else 0
            differences["price"] = {
                "internal": internal.fill_price.amount,
                "venue": venue.price,
                "difference": price_diff,
                "difference_pct": price_diff_pct,
            }

        # Quantity difference
        qty_diff = internal.quantity - venue.quantity
        differences["quantity"] = {
            "internal": internal.quantity,
            "venue": venue.quantity,
            "difference": qty_diff,
            "difference_pct": ((qty_diff / venue.quantity * 100) if venue.quantity != 0 else 0),
        }

        # Fee difference
        internal_fee = internal.fee.amount if internal.fee else 0
        venue_fee = venue.fee
        fee_diff = internal_fee - venue_fee
        differences["fee"] = {
            "internal": internal_fee,
            "venue": venue_fee,
            "difference": fee_diff,
        }

        # Timestamp difference
        if internal.created_at and venue.timestamp:
            time_diff_seconds = (internal.created_at - venue.timestamp).total_seconds()
            differences["timestamp"] = {
                "internal": internal.created_at.isoformat(),
                "venue": venue.timestamp.isoformat(),
                "difference_seconds": time_diff_seconds,
            }

        return differences


class ReconciliationSummaryCalculator:
    """Calculate summary statistics for reconciliation results."""

    @staticmethod
    def calculate(diffs: list[ReconciliationDiff]) -> dict[str, int]:
        """Calculate counts by status.

        Args:
            diffs: List of reconciliation diffs

        Returns:
            Dictionary with counts by status
        """
        counts = {
            "matched": 0,
            "mismatches": 0,
            "missing_internal": 0,
            "missing_venue": 0,
            "total_issues": 0,
        }

        for diff in diffs:
            if diff.status == ReconciliationStatus.MATCHED:
                counts["matched"] += 1
            elif diff.status == ReconciliationStatus.MISMATCH:
                counts["mismatches"] += 1
                counts["total_issues"] += 1
            elif diff.status == ReconciliationStatus.MISSING_INTERNAL:
                counts["missing_internal"] += 1
                counts["total_issues"] += 1
            elif diff.status == ReconciliationStatus.MISSING_VENUE:
                counts["missing_venue"] += 1
                counts["total_issues"] += 1

        return counts
