"""Backtest - Run and view backtest results.

All imports at module level per CLEAN architecture - no lazy imports.
"""

from datetime import datetime, timedelta
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from stonks_trading.domains.backtesting.entities import (
    BacktestConfig,
    BacktestMode,
    RunBacktestRequest,
)
from stonks_trading.domains.backtesting.mappers import BacktestResultMapper
from stonks_trading.domains.backtesting.use_cases import RunBacktestUseCase
from stonks_trading.domains.trading.repositories import get_active_genome
from stonks_trading.domains.trading.value_objects import Symbol

st.set_page_config(page_title="Backtest", page_icon="📉")

st.title("📉 Backtest")

st.markdown("""
Run backtests against historical data and analyze performance metrics.
Compare backtest vs dry-run simulation to verify slippage impact.
""")


async def run_backtest(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    mode: str,
) -> dict[str, Any] | None:
    """Execute backtest and return results.

    Args:
        symbol: Trading symbol
        start_date: Start date for backtest
        end_date: End date for backtest
        mode: "backtest" or "dry_run"

    Returns:
        Backtest result dict or None if failed
    """
    try:
        symbol_vo = Symbol(value=symbol)
        genome = await get_active_genome(symbol_vo)

        if not genome or not genome.genome_data:
            st.error(f"No active genome found for {symbol}")
            return None

        backtest_mode = (
            BacktestMode.DRY_RUN_SIMULATION if mode == "dry_run" else BacktestMode.BACKTEST
        )
        config = BacktestConfig(
            mode=backtest_mode,
            fee_rate=0.001,
            slippage_bps=5 if mode == "dry_run" else 0,
            min_trade_interval=15,
        )

        request = RunBacktestRequest(
            genome_id=genome.id or 0,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            genome_data=genome.genome_data,
            initial_capital=10000.0,
            config=config,
        )

        use_case = RunBacktestUseCase()
        result = await use_case.execute(request)

        return BacktestResultMapper.to_response(result).model_dump()

    except Exception as e:
        st.error(f"Backtest failed: {e}")
        return None


def display_metrics(result: dict[str, Any]) -> None:
    """Display backtest metrics in a grid.

    Args:
        result: Backtest result dictionary
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Return",
            f"{result.get('total_return_pct', 0):.2f}%",
        )
        st.metric(
            "Max Drawdown",
            f"{result.get('max_drawdown_pct', 0):.2f}%",
        )

    with col2:
        st.metric(
            "Sharpe Ratio",
            f"{result.get('sharpe_ratio', 0):.2f}",
        )
        st.metric(
            "Sortino Ratio",
            f"{result.get('sortino_ratio', 0):.2f}",
        )

    with col3:
        st.metric(
            "Total Trades",
            result.get("total_trades", 0),
        )
        st.metric(
            "Win Rate",
            f"{result.get('win_rate_pct', 0):.1f}%",
        )

    with col4:
        st.metric(
            "Profit Factor",
            f"{result.get('profit_factor', 0):.2f}",
        )
        st.metric(
            "Total Fees",
            f"${result.get('total_fees', 0):.2f}",
        )


def plot_equity_curve(result: dict[str, Any]) -> go.Figure:
    """Create equity curve plot.

    Args:
        result: Backtest result dictionary

    Returns:
        Plotly figure
    """
    equity_curve = result.get("equity_curve", [])
    if not equity_curve:
        return go.Figure()

    initial_capital = result.get("initial_capital", 10000.0)
    buy_hold_return = result.get("buy_hold_return_pct", 0)

    buy_hold_curve = [
        initial_capital * (1 + buy_hold_return * i / len(equity_curve))
        for i in range(len(equity_curve))
    ]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Equity Curve", "Drawdown"),
    )

    fig.add_trace(
        go.Scatter(
            y=equity_curve,
            name="Strategy",
            line=dict(color="blue"),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            y=buy_hold_curve,
            name="Buy & Hold",
            line=dict(color="gray", dash="dash"),
        ),
        row=1,
        col=1,
    )

    trades = result.get("trades", [])
    for trade in trades:
        step = trade.get("step", 0)
        if step < len(equity_curve):
            color = "green" if trade.get("type") == "buy" else "red"
            symbol = "triangle-up" if trade.get("type") == "buy" else "triangle-down"
            fig.add_trace(
                go.Scatter(
                    x=[step],
                    y=[equity_curve[step]],
                    mode="markers",
                    marker=dict(color=color, symbol=symbol, size=10),
                    name=f"{trade.get('type', '').title()}",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

    peak = initial_capital
    drawdowns = []
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        drawdown = (peak - eq) / peak * 100 if peak > 0 else 0
        drawdowns.append(drawdown)

    fig.add_trace(
        go.Scatter(
            y=drawdowns,
            name="Drawdown %",
            fill="tozeroy",
            fillcolor="rgba(255, 0, 0, 0.2)",
            line=dict(color="red"),
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"Backtest Results: {result.get('symbol', '')} ({result.get('mode', '')})",
        template="plotly_white",
        height=600,
    )

    return fig


def main() -> None:
    """Main backtest page."""
    st.sidebar.header("Backtest Configuration")

    symbol = st.sidebar.text_input(
        "Symbol",
        value="BTC_USD",
        help="Trading symbol to backtest",
    )

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now() - timedelta(days=90),
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now() - timedelta(days=7),
        )

    mode = st.sidebar.selectbox(
        "Mode",
        options=["backtest", "dry_run"],
        help="Backtest = instant fills, Dry Run = with slippage",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Mode Differences**")
    st.sidebar.markdown(
        "- **Backtest**: Simulates instant fills at close price\n"
        "- **Dry Run**: Adds slippage to simulate real-world execution"
    )

    if st.sidebar.button("🚀 Run Backtest", type="primary"):
        if start_date >= end_date:
            st.error("Start date must be before end date")
            return

        with st.spinner("Running backtest..."):
            import asyncio

            result = asyncio.run(
                run_backtest(
                    symbol=symbol,
                    start_date=datetime.combine(start_date, datetime.min.time()),
                    end_date=datetime.combine(end_date, datetime.min.time()),
                    mode=mode,
                )
            )

        if result:
            st.success(f"Backtest completed! Mode: {mode}")

            display_metrics(result)

            st.subheader("Equity Curve")
            fig = plot_equity_curve(result)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Trade Log"):
                trades = result.get("trades", [])
                if trades:
                    import pandas as pd

                    trades_df = pd.DataFrame(trades)
                    st.dataframe(trades_df, use_container_width=True)
                else:
                    st.info("No trades executed during backtest")

            with st.expander("Raw Results"):
                st.json(result)


if __name__ == "__main__":
    main()
