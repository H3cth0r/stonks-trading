"""Analytics Hub - Performance, Risk, and Capital management.

Phase 10C: Consolidates Performance Analytics and Risk Monitor.
"""

from datetime import datetime, timedelta
from time import sleep
from typing import Any

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Analytics Hub", page_icon="📈", layout="wide")

st.title("📈 Analytics Hub")

# Tabs: Performance | Risk + Capital
tab_performance, tab_capital = st.tabs(["Performance", "Risk + Capital"])

# =============================================================================
# PERFORMANCE TAB (includes Backtest + Live + Compare from old page 3)
# =============================================================================
with tab_performance:
    st.header("Performance Overview")

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.utcnow() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", value=datetime.utcnow())

    # Symbol selector
    symbols_data = fetch_sync("/api/v1/instruments")
    if symbols_data and symbols_data.get("instruments"):
        symbol_options = [i["symbol"] for i in symbols_data["instruments"]]
    else:
        symbol_options = ["BTC_USD", "ETH_USD"]
    symbol = st.selectbox("Symbol", symbol_options, index=0)

    # Sub-tabs: Backtest | Live | Compare
    sub_tab_backtest, sub_tab_live, sub_tab_compare = st.tabs(
        ["Backtest Results", "Live Performance", "Compare"]
    )

    with sub_tab_backtest:
        st.header("Backtest Results")

        # Run new backtest
        with st.expander("Run New Backtest"):
            col1, col2, col3 = st.columns(3)
            with col1:
                backtest_model = st.number_input(
                    "Model ID", min_value=1, value=1, key="backtest_model"
                )
                backtest_strategy = st.selectbox(
                    "Strategy", ["neat_swing"], key="backtest_strategy"
                )
            with col2:
                initial_capital = st.number_input(
                    "Initial Capital", min_value=1000, value=10000, key="backtest_capital"
                )
            with col3:
                fee_rate = st.slider(
                    "Fee Rate", min_value=0.0, max_value=0.01, value=0.001, key="backtest_fee"
                )

            if st.button("Run Backtest", key="run_backtest_btn"):
                with st.spinner("Running backtest..."):
                    result = post_sync(
                        "/api/v1/backtest",
                        {
                            "strategy_type": backtest_strategy,
                            "model_id": backtest_model,
                            "symbol": symbol.upper(),
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "initial_capital": initial_capital,
                            "fee_rate": fee_rate,
                            "slippage_bps": 0,
                            "mode": "backtest",
                        },
                    )
                    if result:
                        st.success("Backtest completed!")
                        st.json(result)
                    else:
                        st.error("Backtest failed")

        # List existing backtests
        st.subheader("Historical Backtests")
        backtests_data = fetch_sync("/api/v1/backtest", {"symbol": symbol.upper(), "limit": 50})
        if backtests_data and backtests_data.get("results"):
            st.dataframe(pd.DataFrame(backtests_data["results"]), use_container_width=True)
        else:
            st.info("No backtest results")

    with sub_tab_live:
        st.header("Live Trading Performance")

        trades_data = fetch_sync("/api/v1/trades", {"symbol": symbol.upper(), "limit": 100})

        if trades_data and trades_data.get("trades"):
            trades = trades_data["trades"]
            df = pd.DataFrame(trades)

            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Trades", len(trades))
            with col2:
                buy_trades = len([t for t in trades if t.get("side") == "BUY"])
                st.metric("Buy Trades", buy_trades)
            with col3:
                sell_trades = len([t for t in trades if t.get("side") == "SELL"])
                st.metric("Sell Trades", sell_trades)
            with col4:
                total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in trades)
                st.metric("Total P&L", f"${total_pnl:,.2f}")

            st.dataframe(df, use_container_width=True)
        else:
            st.info("No live trades for selected period")

    with sub_tab_compare:
        st.header("Backtest vs Live Comparison")
        st.info("Comparison analysis coming soon...")

# =============================================================================
# RISK + CAPITAL TAB (combines old Risk Monitor tabs)
# =============================================================================
with tab_capital:
    # Sub-tabs: Risk Events | Capital Allocation | Risk Limits
    sub_tab_events, sub_tab_capital_alloc, sub_tab_limits = st.tabs(
        ["Risk Events", "Capital Allocation", "Risk Limits"]
    )

    with sub_tab_events:
        st.header("Risk Events")

        # Risk summary cards
        risk_data = fetch_sync("/api/v1/risk/status")
        if risk_data:
            summary_cols = st.columns(4)
            with summary_cols[0]:
                drawdown = risk_data.get("drawdown", 0)
                st.metric("Current Drawdown", f"{drawdown:.2%}")
            with summary_cols[1]:
                daily_trades = risk_data.get("daily_trades", 0)
                st.metric("Daily Trades", daily_trades)
            with summary_cols[2]:
                max_dd = risk_data.get("max_drawdown", 0)
                st.metric("Max Drawdown", f"{max_dd:.2%}")
            with summary_cols[3]:
                status = risk_data.get("status", "unknown")
                st.metric("Risk Status", status)
        else:
            st.info("No risk data available")

        # Filters
        col1, col2 = st.columns(2)
        with col1:
            severity_filter = st.selectbox(
                "Severity", ["All", "low", "medium", "high", "critical"], key="severity_filter"
            )
        with col2:
            show_acknowledged = st.checkbox(
                "Show Acknowledged", value=False, key="show_acknowledged"
            )

        params: dict[str, Any] = {"limit": 100}
        if severity_filter != "All":
            params["severity"] = severity_filter.lower()
        if not show_acknowledged:
            params["acknowledged"] = "false"

        events_data = fetch_sync("/api/v1/risk/events", params)
        if events_data and events_data.get("events"):
            events = events_data["events"]
            st.dataframe(pd.DataFrame(events), use_container_width=True)

            # Acknowledge event
            st.subheader("Acknowledge Event")
            col1, col2 = st.columns(2)
            with col1:
                event_id = st.number_input("Event ID", min_value=1, step=1, key="ack_event_id")
            with col2:
                action = st.text_input(
                    "Action Taken", value="Investigated and resolved", key="ack_action"
                )

            if st.button("Acknowledge", key="ack_btn"):
                result = post_sync(
                    f"/api/v1/risk/events/{event_id}/acknowledge",
                    {"user": "dashboard_user", "action": action},
                )
                if result:
                    st.success("Event acknowledged!")
                else:
                    st.error("Failed to acknowledge")
        else:
            st.info("No risk events")

    with sub_tab_capital_alloc:
        st.header("Binance Balance")

        balance_data = fetch_sync("/api/v1/balances/usdt")
        if balance_data and "balance" in balance_data:
            usdt_balance = balance_data["balance"]
            st.metric("Available USDT", f"${usdt_balance:,.2f}")
            st.info("Capital is managed directly in Binance for live trading.")
        else:
            st.error("Unable to fetch Binance balance. Check API configuration.")

    with sub_tab_limits:
        st.header("Risk Limits")
        st.info("Risk limit configuration coming soon...")

        # Display current limits from config
        st.subheader("Current Limits")
        limits_cols = st.columns(3)
        with limits_cols[0]:
            st.metric("Max Position %", "95%")
        with limits_cols[1]:
            st.metric("Max Drawdown %", "15%")
        with limits_cols[2]:
            st.metric("Max Trades/Day", "40")

# Auto-refresh
if st.sidebar.checkbox("Auto-refresh", value=True):
    sleep(30)
    st.rerun()
