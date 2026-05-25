"""Mappers for converting between backtesting domain entities and API DTOs.

Mappers are used ONLY by the API layer - not imported by the bot.
They handle conversion between internal domain representation
and external API format.
"""

from stonks_trading.domains.backtesting.dtos import BacktestResultResponse
from stonks_trading.domains.backtesting.entities import BacktestResult


class BacktestResultMapper:
    """Maps between BacktestResult entity and API DTOs."""

    @staticmethod
    def to_response(entity: BacktestResult) -> BacktestResultResponse:
        """Convert domain entity to API response DTO."""
        return BacktestResultResponse(
            backtest_id=entity.backtest_id,
            genome_id=entity.genome_id,
            symbol=entity.symbol,
            mode=entity.mode.value,
            start_date=entity.start_date,
            end_date=entity.end_date,
            initial_capital=entity.initial_capital,
            final_equity=entity.final_equity,
            total_return_pct=entity.total_return_pct,
            annualized_return_pct=entity.annualized_return_pct,
            max_drawdown_pct=entity.max_drawdown_pct,
            sharpe_ratio=entity.sharpe_ratio,
            sortino_ratio=entity.sortino_ratio,
            total_trades=entity.total_trades,
            win_rate_pct=entity.win_rate_pct,
            avg_win=entity.avg_win,
            avg_loss=entity.avg_loss,
            profit_factor=entity.profit_factor,
            total_fees=entity.total_fees,
            buy_hold_return_pct=entity.buy_hold_return_pct,
            alpha=entity.alpha,
            beta=entity.beta,
            created_at=entity.created_at,
        )

    @staticmethod
    def to_response_list(entities: list[BacktestResult]) -> list[BacktestResultResponse]:
        """Convert list of entities to response DTOs."""
        return [BacktestResultMapper.to_response(e) for e in entities]
