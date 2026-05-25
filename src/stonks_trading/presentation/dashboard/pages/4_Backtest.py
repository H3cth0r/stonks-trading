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
from stonks_trading.domains.backtesting.use_cases import (
    CompareBacktestResultsUseCase,
    RunBacktestUseCase,
)
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
            line={"color": "blue"},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            y=buy_hold_curve,
            name="Buy & Hold",
            line={"color": "gray", "dash": "dash"},
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
                    marker={"color": color, "symbol": symbol, "size": 10},
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
            line={"color": "red"},
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


async def run_comparison_backtest(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Run both backtest and dry_run modes and compare results.

    Args:
        symbol: Trading symbol
        start_date: Start date for backtest
        end_date: End date for backtest

    Returns:
        Tuple of (backtest_result, dry_run_result, comparison)
    """
    # Run backtest mode (no slippage)
    backtest_result = await run_backtest(symbol, start_date, end_date, "backtest")
    if not backtest_result:
        return None, None, None

    # Run dry_run mode (with slippage)
    dry_run_result = await run_backtest(symbol, start_date, end_date, "dry_run")
    if not dry_run_result:
        return backtest_result, None, None

    # Compare results
    try:
        # Convert dicts to BacktestResult entities for comparison
        from stonks_trading.domains.backtesting.entities import BacktestResult

        backtest_entity = BacktestResult(
            backtest_id=backtest_result.get("backtest_id", ""),
            genome_id=backtest_result.get("genome_id", 0),
            symbol=backtest_result.get("symbol", ""),
            start_date=backtest_result.get("start_date", datetime.utcnow()),
            end_date=backtest_result.get("end_date", datetime.utcnow()),
            mode=backtest_result.get("mode", "backtest"),
            initial_capital=backtest_result.get("initial_capital", 10000.0),
            final_equity=backtest_result.get("final_equity", 10000.0),
            total_return_pct=backtest_result.get("total_return_pct", 0.0),
            annualized_return_pct=backtest_result.get("annualized_return_pct", 0.0),
            max_drawdown_pct=backtest_result.get("max_drawdown_pct", 0.0),
            sharpe_ratio=backtest_result.get("sharpe_ratio", 0.0),
            sortino_ratio=backtest_result.get("sortino_ratio", 0.0),
            total_trades=backtest_result.get("total_trades", 0),
            win_rate_pct=backtest_result.get("win_rate_pct", 0.0),
            avg_win=backtest_result.get("avg_win", 0.0),
            avg_loss=backtest_result.get("avg_loss", 0.0),
            profit_factor=backtest_result.get("profit_factor", 0.0),
            total_fees=backtest_result.get("total_fees", 0.0),
            buy_hold_return_pct=backtest_result.get("buy_hold_return_pct", 0.0),
            alpha=backtest_result.get("alpha", 0.0),
            beta=backtest_result.get("beta", 0.0),
            equity_curve=backtest_result.get("equity_curve", []),
            trades=backtest_result.get("trades", []),
            created_at=datetime.utcnow(),
        )

        dry_run_entity = BacktestResult(
            backtest_id=dry_run_result.get("backtest_id", ""),
            genome_id=dry_run_result.get("genome_id", 0),
            symbol=dry_run_result.get("symbol", ""),
            start_date=dry_run_result.get("start_date", datetime.utcnow()),
            end_date=dry_run_result.get("end_date", datetime.utcnow()),
            mode=dry_run_result.get("mode", "dry_run"),
            initial_capital=dry_run_result.get("initial_capital", 10000.0),
            final_equity=dry_run_result.get("final_equity", 10000.0),
            total_return_pct=dry_run_result.get("total_return_pct", 0.0),
            annualized_return_pct=dry_run_result.get("annualized_return_pct", 0.0),
            max_drawdown_pct=dry_run_result.get("max_drawdown_pct", 0.0),
            sharpe_ratio=dry_run_result.get("sharpe_ratio", 0.0),
            sortino_ratio=dry_run_result.get("sortino_ratio", 0.0),
            total_trades=dry_run_result.get("total_trades", 0),
            win_rate_pct=dry_run_result.get("win_rate_pct", 0.0),
            avg_win=dry_run_result.get("avg_win", 0.0),
            avg_loss=dry_run_result.get("avg_loss", 0.0),
            profit_factor=dry_run_result.get("profit_factor", 0.0),
            total_fees=dry_run_result.get("total_fees", 0.0),
            buy_hold_return_pct=dry_run_result.get("buy_hold_return_pct", 0.0),
            alpha=dry_run_result.get("alpha", 0.0),
            beta=dry_run_result.get("beta", 0.0),
            equity_curve=dry_run_result.get("equity_curve", []),
            trades=dry_run_result.get("trades", []),
            created_at=datetime.utcnow(),
        )

        compare_use_case = CompareBacktestResultsUseCase()
        comparison = await compare_use_case.execute(backtest_entity, dry_run_entity)

        return backtest_result, dry_run_result, comparison

    except Exception as e:
        st.error(f"Comparison failed: {e}")
        return backtest_result, dry_run_result, None


def display_comparison_metrics(
    backtest: dict[str, Any],
    dry_run: dict[str, Any],
    comparison: dict[str, Any],
) -> None:
    """Display comparison metrics between backtest and dry_run.

    Args:
        backtest: Backtest result dict
        dry_run: Dry run result dict
        comparison: Comparison result dict
    """
    st.subheader("📊 Backtest vs Dry-Run Comparison")

    # Verification status
    verification_passed = comparison.get("verification_passed", False)
    dry_run_worse = comparison.get("dry_run_worse", False)

    if verification_passed:
        st.success("✅ Verification PASSED: Dry-run produces worse results as expected")
    elif dry_run_worse:
        st.warning("⚠️ Partial: Dry-run is worse but difference may be insignificant")
    else:
        st.error("❌ Verification FAILED: Dry-run produced better results than backtest")

    # Metrics comparison table
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Backtest** (No Slippage)")
        st.metric("ROI", f"{comparison.get('backtest_roi', 0):.2f}%")
        st.metric("Max DD", f"{comparison.get('backtest_max_dd', 0):.2f}%")

    with col2:
        st.markdown("**Dry Run** (With Slippage)")
        st.metric("ROI", f"{comparison.get('dry_run_roi', 0):.2f}%")
        st.metric("Max DD", f"{comparison.get('dry_run_max_dd', 0):.2f}%")

    with col3:
        st.markdown("**Difference**")
        roi_diff = comparison.get("roi_difference_pct", 0)
        dd_diff = comparison.get("dd_difference_pct", 0)
        st.metric("ROI Diff", f"{roi_diff:+.2f}%", delta_color="inverse")
        st.metric("Max DD Diff", f"{dd_diff:+.2f}%", delta_color="inverse")

    # Detailed metrics
    st.markdown("---")
    cols = st.columns(4)
    metrics = [
        ("Total Trades", "total_trades"),
        ("Win Rate", "win_rate_pct"),
        ("Sharpe Ratio", "sharpe_ratio"),
        ("Total Fees", "total_fees"),
    ]

    for i, (label, key) in enumerate(metrics):
        with cols[i % 4]:
            bt_val = backtest.get(key, 0)
            dr_val = dry_run.get(key, 0)
            diff = dr_val - bt_val
            st.metric(
                label,
                f"BT: {bt_val:.2f}",
                f"DR: {dr_val:.2f} ({diff:+.2f})",
            )


def plot_comparison_chart(
    backtest: dict[str, Any],
    dry_run: dict[str, Any],
) -> go.Figure:
    """Create comparison chart of backtest vs dry_run equity curves.

    Args:
        backtest: Backtest result dict
        dry_run: Dry run result dict

    Returns:
        Plotly figure
    """
    bt_curve = backtest.get("equity_curve", [])
    dr_curve = dry_run.get("equity_curve", [])

    if not bt_curve or not dr_curve:
        return go.Figure()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Equity Curves Comparison", "Difference (Backtest - Dry Run)"),
    )

    # Equity curves
    fig.add_trace(
        go.Scatter(
            y=bt_curve,
            name="Backtest (No Slippage)",
            line={"color": "blue"},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            y=dr_curve,
            name="Dry Run (With Slippage)",
            line={"color": "orange"},
        ),
        row=1,
        col=1,
    )

    # Difference
    min_len = min(len(bt_curve), len(dr_curve))
    difference = [bt_curve[i] - dr_curve[i] for i in range(min_len)]

    fig.add_trace(
        go.Scatter(
            y=difference,
            name="Difference",
            fill="tozeroy",
            fillcolor="rgba(0, 255, 0, 0.2)",
            line={"color": "green"},
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"Backtest vs Dry-Run: {backtest.get('symbol', '')}",
        template="plotly_white",
        height=700,
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

    # Mode selection with comparison option
    mode = st.sidebar.selectbox(
        "Mode",
        options=["backtest", "dry_run", "compare"],
        help="Backtest = instant fills, Dry Run = with slippage, Compare = both",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Mode Differences**")
    st.sidebar.markdown(
        "- **Backtest**: Simulates instant fills at close price\n"
        "- **Dry Run**: Adds slippage to simulate real-world execution\n"
        "- **Compare**: Runs both modes and compares results"
    )

    if st.sidebar.button("🚀 Run Backtest", type="primary"):
        if start_date >= end_date:
            st.error("Start date must be before end date")
            return

        if mode == "compare":
            with st.spinner("Running comparison (this may take a while)..."):
                import asyncio

                bt_result, dr_result, comparison = asyncio.run(
                    run_comparison_backtest(
                        symbol=symbol,
                        start_date=datetime.combine(start_date, datetime.min.time()),
                        end_date=datetime.combine(end_date, datetime.min.time()),
                    )
                )

            if bt_result and dr_result and comparison:
                st.success("✅ Comparison completed!")

                # Display comparison
                display_comparison_metrics(bt_result, dr_result, comparison)

                # Comparison chart
                st.subheader("Equity Curve Comparison")
                fig = plot_comparison_chart(bt_result, dr_result)
                st.plotly_chart(fig, use_container_width=True)

                # Individual results tabs
                bt_tab, dr_tab = st.tabs(["Backtest Details", "Dry Run Details"])

                with bt_tab:
                    st.markdown("### Backtest Mode (No Slippage)")
                    display_metrics(bt_result)
                    st.plotly_chart(plot_equity_curve(bt_result), use_container_width=True)

                with dr_tab:
                    st.markdown("### Dry Run Mode (With Slippage)")
                    display_metrics(dr_result)
                    st.plotly_chart(plot_equity_curve(dr_result), use_container_width=True)

            elif bt_result:
                st.warning("Dry run failed, showing backtest only")
                display_metrics(bt_result)
                st.plotly_chart(plot_equity_curve(bt_result), use_container_width=True)

        else:
            # Single mode run
            with st.spinner(f"Running {mode} backtest..."):
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
