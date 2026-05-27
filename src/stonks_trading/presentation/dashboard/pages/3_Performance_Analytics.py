"""Performance Analytics - Backtest and live trading performance analysis.

Phase 10H: Merges Backtest + Live performance with enhanced analytics.
"""

from datetime import datetime, timedelta
from time import sleep

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Performance Analytics", page_icon="📈", layout="wide")

st.title("📈 Performance Analytics")

# Date range selector
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
with col2:
    end_date = st.date_input("End Date", value=datetime.now())

symbol = st.text_input("Symbol", value="BTC_USD")

# Tabs for Backtest vs Live
tab_backtest, tab_live, tab_compare = st.tabs(["Backtest Results", "Live Performance", "Compare"])

with tab_backtest:
    st.header("Backtest Results")

    # Run new backtest
    with st.expander("Run New Backtest"):
        col1, col2, col3 = st.columns(3)
        with col1:
            backtest_model = st.number_input("Model ID", min_value=1, value=1, key="backtest_model")
            backtest_strategy = st.selectbox("Strategy", ["neat_swing"], key="backtest_strategy")
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

with tab_live:
    st.header("Live Trading Performance")

    # Get trades for the period
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

with tab_compare:
    st.header("Backtest vs Live Comparison")
    st.info("Comparison analysis coming soon...")

# Auto-refresh
if st.sidebar.checkbox("Auto-refresh", value=True):
    sleep(30)
    st.rerun()
