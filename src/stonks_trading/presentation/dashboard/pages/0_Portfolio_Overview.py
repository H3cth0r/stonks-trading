"""Portfolio Overview - Master portfolio view with real-time metrics.

Phase 10H: Replaces Operations Hub with focused portfolio analytics.
"""

from time import sleep

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(page_title="Portfolio Overview", page_icon="💼", layout="wide")

st.title("💼 Portfolio Overview")

# Auto-refresh control
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 10, 300, 30)

# Portfolio Summary Cards
st.header("Portfolio Summary")
summary_cols = st.columns(4)

portfolio_data = fetch_sync("/api/v1/portfolio")
if portfolio_data:
    with summary_cols[0]:
        total_value = portfolio_data.get("total_value", 0)
        st.metric("Total Value", f"${total_value:,.2f}")
    with summary_cols[1]:
        cash = portfolio_data.get("cash_value", 0)
        st.metric("Cash", f"${cash:,.2f}")
    with summary_cols[2]:
        positions_value = portfolio_data.get("positions_value", 0)
        st.metric("Positions", f"${positions_value:,.2f}")
    with summary_cols[3]:
        pnl = portfolio_data.get("unrealized_pnl", 0)
        delta_pct = f"{pnl / total_value * 100:.2f}%" if total_value > 0 else None
        st.metric("Unrealized P&L", f"${pnl:,.2f}", delta=delta_pct)
else:
    st.info("No portfolio data available")

# Capital Pools Section
st.header("Capital Allocation")
capital_data = fetch_sync("/api/v1/capital/pools")
if capital_data and capital_data.get("pools"):
    pools = capital_data["pools"]
    pools_df = pd.DataFrame(pools)
    st.dataframe(pools_df, use_container_width=True)

    # Visual representation
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Capital by Pool")
        if "pool_id" in pools_df.columns and "total_amount" in pools_df.columns:
            st.bar_chart(pools_df.set_index("pool_id")["total_amount"])
        else:
            st.info("Pool data format not supported for chart")
    with col2:
        st.subheader("Pool Summary")
        if "total_amount" in pools_df.columns:
            total_capital = pools_df["total_amount"].sum()
            st.metric("Total Capital", f"${total_capital:,.2f}")
else:
    st.info("No capital pools configured")

# Positions with Live Chart
st.header("Positions")
positions_data = fetch_sync("/api/v1/positions")
if positions_data and positions_data.get("positions"):
    positions = positions_data["positions"]

    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(positions, use_container_width=True)
    with col2:
        if positions:
            sides = [p.get("side", "UNKNOWN") for p in positions]
            long_count = sides.count("LONG")
            short_count = sides.count("SHORT")
            st.metric("Long Positions", long_count)
            st.metric("Short Positions", short_count)
else:
    st.info("No open positions")

# Recent Activity
st.header("Recent Activity")
activity_data = fetch_sync("/api/v1/trades", {"limit": 20})
if activity_data and activity_data.get("trades"):
    trades = activity_data["trades"]
    st.dataframe(trades, use_container_width=True)
else:
    st.info("No recent activity")

# Auto-refresh
if auto_refresh:
    sleep(refresh_interval)
    st.rerun()
