"""Backtesting domain repositories - PURE DATA ACCESS ONLY.

Standalone async functions following trading domain pattern.
NO business logic - only DuckDB queries.

Repository rules (per architecture.md lines 42-48):
- Single file with standalone async functions
- NO classes, NO ABC, NO inheritance
- Pure data access - no business logic
- Use DuckDB for backtest results storage
"""

import json
from typing import Any

import duckdb

from stonks_trading.domains.backtesting.entities import BacktestMode, BacktestResult
from stonks_trading.shared.storage.duckdb_client import DuckDBClient


async def save_backtest_result(result: BacktestResult) -> str:
    """Save backtest result to DuckDB.

    Args:
        result: BacktestResult entity to save

    Returns:
        backtest_id of saved result
    """
    client = DuckDBClient()
    client.connect()

    try:
        # Serialize equity curve and trades to JSON strings
        equity_json = _serialize_equity_curve(result.equity_curve)
        trades_json = _serialize_trades(result.trades)

        # Create table if not exists
        client._conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                backtest_id TEXT PRIMARY KEY,
                genome_id INTEGER,
                symbol TEXT,
                mode TEXT,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                initial_capital DOUBLE,
                final_equity DOUBLE,
                total_return_pct DOUBLE,
                annualized_return_pct DOUBLE,
                max_drawdown_pct DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                total_trades INTEGER,
                win_rate_pct DOUBLE,
                avg_win DOUBLE,
                avg_loss DOUBLE,
                profit_factor DOUBLE,
                total_fees DOUBLE,
                buy_hold_return_pct DOUBLE,
                alpha DOUBLE,
                beta DOUBLE,
                equity_curve TEXT,
                trades TEXT,
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Insert into DuckDB
        query = """
        INSERT OR REPLACE INTO backtest_results (
            backtest_id, genome_id, symbol, mode, start_date, end_date,
            initial_capital, final_equity, total_return_pct, annualized_return_pct,
            max_drawdown_pct, sharpe_ratio, sortino_ratio, total_trades,
            win_rate_pct, avg_win, avg_loss, profit_factor, total_fees,
            buy_hold_return_pct, alpha, beta, equity_curve, trades,
            created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        client._conn.execute(
            query,
            [
                result.backtest_id,
                result.genome_id,
                result.symbol,
                result.mode.value if hasattr(result.mode, "value") else str(result.mode),
                result.start_date,
                result.end_date,
                result.initial_capital,
                result.final_equity,
                result.total_return_pct,
                result.annualized_return_pct,
                result.max_drawdown_pct,
                result.sharpe_ratio,
                result.sortino_ratio,
                result.total_trades,
                result.win_rate_pct,
                result.avg_win,
                result.avg_loss,
                result.profit_factor,
                result.total_fees,
                result.buy_hold_return_pct,
                result.alpha,
                result.beta,
                equity_json,
                trades_json,
                result.created_at,
                result.completed_at,
            ],
        )

        return result.backtest_id
    finally:
        client.close()


async def get_backtest_result(backtest_id: str) -> BacktestResult | None:
    """Get backtest result by ID.

    Args:
        backtest_id: Backtest result ID

    Returns:
        BacktestResult or None if not found
    """
    client = DuckDBClient()
    client.connect()

    try:
        result = client._conn.execute(
            "SELECT * FROM backtest_results WHERE backtest_id = ?",
            [backtest_id],
        )
        row = result.fetchone()

        if not row:
            return None

        # Convert to dict
        columns = [desc[0] for desc in result.description]
        row_dict = dict(zip(columns, row, strict=False))

        return _row_to_backtest_result(row_dict)
    finally:
        client.close()


async def list_backtest_results(
    symbol: str | None = None,
    model_id: int | None = None,
    mode: BacktestMode | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BacktestResult]:
    """List backtest results with filters.

    Args:
        symbol: Filter by symbol
        model_id: Filter by model ID (Phase 10H: renamed from genome_id)
        mode: Filter by backtest mode
        limit: Maximum results
        offset: Results to skip

    Returns:
        List of BacktestResult entities
    """
    # Phase 10H: Accept model_id but use genome_id internally for DB compatibility
    genome_id = model_id
    client = DuckDBClient()
    client.connect()

    try:
        # Check if table exists
        try:
            client._conn.execute("SELECT 1 FROM backtest_results LIMIT 1")
        except duckdb.CatalogException:
            # Table doesn't exist yet, return empty list
            return []

        conditions = []
        params: list[Any] = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if genome_id is not None:
            conditions.append("genome_id = ?")
            params.append(genome_id)
        if mode:
            conditions.append("mode = ?")
            params.append(mode.value if hasattr(mode, "value") else str(mode))

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
        SELECT * FROM backtest_results
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        result = client._conn.execute(query, params)
        rows = result.fetchall()

        if not rows:
            return []

        columns = [desc[0] for desc in result.description]
        return [_row_to_backtest_result(dict(zip(columns, row, strict=False))) for row in rows]
    finally:
        client.close()


async def delete_backtest_result(backtest_id: str) -> bool:
    """Delete a backtest result.

    Args:
        backtest_id: Backtest result ID to delete

    Returns:
        True if deleted, False if not found
    """
    client = DuckDBClient()
    client.connect()

    try:
        result = client._conn.execute(
            "DELETE FROM backtest_results WHERE backtest_id = ?",
            [backtest_id],
        )

        return result.rowcount > 0 if result.rowcount is not None else False
    finally:
        client.close()


# =============================================================================
# Helper Functions
# =============================================================================


def _serialize_equity_curve(equity_curve: list[dict[str, Any]]) -> str:
    """Serialize equity curve to JSON string."""
    return json.dumps(equity_curve)


def _serialize_trades(trades: list[dict[str, Any]]) -> str:
    """Serialize trades to JSON string."""
    return json.dumps(trades)


def _deserialize_equity_curve(json_str: str | None) -> list[dict[str, Any]]:
    """Deserialize equity curve from JSON string."""
    if not json_str:
        return []
    return json.loads(json_str)


def _deserialize_trades(json_str: str | None) -> list[dict[str, Any]]:
    """Deserialize trades from JSON string."""
    if not json_str:
        return []
    return json.loads(json_str)


def _row_to_backtest_result(row: dict[str, Any]) -> BacktestResult:
    """Convert database row to BacktestResult entity.

    Pure transformation - no logic.
    """
    mode_value = row.get("mode", "backtest")
    mode = BacktestMode(mode_value) if isinstance(mode_value, str) else mode_value

    return BacktestResult(
        backtest_id=row.get("backtest_id", ""),
        model_id=row.get("model_id") or row.get("genome_id", 0),  # Phase 10H: supports both
        symbol=row.get("symbol", ""),
        mode=mode,
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
        initial_capital=row.get("initial_capital", 0.0),
        final_equity=row.get("final_equity", 0.0),
        total_return_pct=row.get("total_return_pct", 0.0),
        annualized_return_pct=row.get("annualized_return_pct", 0.0),
        max_drawdown_pct=row.get("max_drawdown_pct", 0.0),
        sharpe_ratio=row.get("sharpe_ratio", 0.0),
        sortino_ratio=row.get("sortino_ratio", 0.0),
        total_trades=row.get("total_trades", 0),
        win_rate_pct=row.get("win_rate_pct", 0.0),
        avg_win=row.get("avg_win", 0.0),
        avg_loss=row.get("avg_loss", 0.0),
        profit_factor=row.get("profit_factor", 0.0),
        total_fees=row.get("total_fees", 0.0),
        buy_hold_return_pct=row.get("buy_hold_return_pct", 0.0),
        alpha=row.get("alpha", 0.0),
        beta=row.get("beta", 0.0),
        equity_curve=_deserialize_equity_curve(row.get("equity_curve")),
        trades=_deserialize_trades(row.get("trades")),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )
