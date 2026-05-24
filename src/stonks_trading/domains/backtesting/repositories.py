"""Backtesting domain repositories - PURE DATA ACCESS ONLY.

Standalone async functions following trading domain pattern.
NO business logic - only DuckDB queries.

Repository rules (per architecture.md lines 42-48):
- Single file with standalone async functions
- NO classes, NO ABC, NO inheritance
- Pure data access - no business logic
- Use DuckDB for backtest results storage
"""

from typing import Any

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

    # Serialize equity curve and trades to JSON strings
    equity_json = _serialize_equity_curve(result.equity_curve)
    trades_json = _serialize_trades(result.trades)

    # Insert into DuckDB
    query = """
    INSERT INTO backtest_results (
        backtest_id, genome_id, symbol, mode, start_date, end_date,
        initial_capital, final_equity, total_return_pct, annualized_return_pct,
        max_drawdown_pct, sharpe_ratio, sortino_ratio, total_trades,
        win_rate_pct, avg_win, avg_loss, profit_factor, total_fees,
        buy_hold_return_pct, alpha, beta, equity_curve, trades,
        created_at, completed_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    await client.execute(
        query,
        [
            result.backtest_id,
            result.genome_id,
            result.symbol,
            result.mode.value,
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


async def get_backtest_result(backtest_id: str) -> BacktestResult | None:
    """Get backtest result by ID.

    Args:
        backtest_id: Backtest result ID

    Returns:
        BacktestResult or None if not found
    """
    client = DuckDBClient()

    query = """
    SELECT * FROM backtest_results WHERE backtest_id = ?
    """

    row = await client.fetchone(query, [backtest_id])

    if not row:
        return None

    return _row_to_backtest_result(row)


async def list_backtest_results(
    symbol: str | None = None,
    genome_id: int | None = None,
    mode: BacktestMode | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BacktestResult]:
    """List backtest results with filters.

    Args:
        symbol: Filter by symbol
        genome_id: Filter by genome ID
        mode: Filter by backtest mode
        limit: Maximum results
        offset: Results to skip

    Returns:
        List of BacktestResult entities
    """
    client = DuckDBClient()

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
        params.append(mode.value)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
    SELECT * FROM backtest_results
    WHERE {where_clause}
    ORDER BY created_at DESC
    LIMIT ? OFFSET ?
    """

    params.extend([limit, offset])

    rows = await client.fetchall(query, params)

    return [_row_to_backtest_result(row) for row in rows]


async def delete_backtest_result(backtest_id: str) -> bool:
    """Delete a backtest result.

    Args:
        backtest_id: Backtest result ID to delete

    Returns:
        True if deleted, False if not found
    """
    client = DuckDBClient()

    query = "DELETE FROM backtest_results WHERE backtest_id = ?"
    result = await client.execute(query, [backtest_id])

    return result.rowcount > 0 if result.rowcount is not None else False


# =============================================================================
# Helper Functions
# =============================================================================


def _serialize_equity_curve(equity_curve: list[dict[str, Any]]) -> str:
    """Serialize equity curve to JSON string."""
    import json

    return json.dumps(equity_curve)


def _serialize_trades(trades: list[dict[str, Any]]) -> str:
    """Serialize trades to JSON string."""
    import json

    return json.dumps(trades)


def _deserialize_equity_curve(json_str: str | None) -> list[dict[str, Any]]:
    """Deserialize equity curve from JSON string."""
    import json

    if not json_str:
        return []
    return json.loads(json_str)


def _deserialize_trades(json_str: str | None) -> list[dict[str, Any]]:
    """Deserialize trades from JSON string."""
    import json

    if not json_str:
        return []
    return json.loads(json_str)


def _row_to_backtest_result(row: Any) -> BacktestResult:
    """Convert database row to BacktestResult entity.

    Pure transformation - no logic.
    """
    return BacktestResult(
        backtest_id=row["backtest_id"],
        genome_id=row["genome_id"],
        symbol=row["symbol"],
        mode=BacktestMode(row["mode"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
        initial_capital=row["initial_capital"],
        final_equity=row["final_equity"],
        total_return_pct=row["total_return_pct"],
        annualized_return_pct=row["annualized_return_pct"],
        max_drawdown_pct=row["max_drawdown_pct"],
        sharpe_ratio=row["sharpe_ratio"],
        sortino_ratio=row["sortino_ratio"],
        total_trades=row["total_trades"],
        win_rate_pct=row["win_rate_pct"],
        avg_win=row["avg_win"],
        avg_loss=row["avg_loss"],
        profit_factor=row["profit_factor"],
        total_fees=row["total_fees"],
        buy_hold_return_pct=row["buy_hold_return_pct"],
        alpha=row["alpha"],
        beta=row["beta"],
        equity_curve=_deserialize_equity_curve(row.get("equity_curve")),
        trades=_deserialize_trades(row.get("trades")),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )
