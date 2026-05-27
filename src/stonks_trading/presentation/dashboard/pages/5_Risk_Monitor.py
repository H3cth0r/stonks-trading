"""Risk Monitor - Risk management and capital allocation dashboard.

Phase 10H: New page combining risk events and capital management.
"""

from time import sleep
from typing import Any

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Risk Monitor", page_icon="⚠️", layout="wide")

st.title("⚠️ Risk Monitor")

# Risk Summary Cards
st.header("Risk Summary")
summary_cols = st.columns(4)

risk_data = fetch_sync("/api/v1/risk/status")
if risk_data:
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

# Tabs
tab_events, tab_capital, tab_limits = st.tabs(["Risk Events", "Capital Allocation", "Risk Limits"])

with tab_events:
    st.header("Risk Events")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        severity_filter = st.selectbox(
            "Severity", ["All", "low", "medium", "high", "critical"], key="severity_filter"
        )
    with col2:
        show_acknowledged = st.checkbox("Show Acknowledged", value=False, key="show_acknowledged")

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

with tab_capital:
    st.header("Capital Allocation")

    pools_data = fetch_sync("/api/v1/capital/pools")
    if pools_data and pools_data.get("pools"):
        pools = pools_data["pools"]

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Capital Pools")
            st.dataframe(pd.DataFrame(pools), use_container_width=True)

        with col2:
            st.subheader("Visual Breakdown")
            pools_df = pd.DataFrame(pools)
            if "pool_id" in pools_df.columns and "total_amount" in pools_df.columns:
                st.bar_chart(pools_df.set_index("pool_id")["total_amount"])

        # Allocation
        st.subheader("Allocate Capital to Bot")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            alloc_bot_type = st.text_input("Bot Type", value="neat_swing", key="alloc_bot_type")
        with col2:
            alloc_instance = st.text_input("Instance ID", value="default", key="alloc_instance")
        with col3:
            alloc_amount = st.number_input(
                "Amount", min_value=0.0, value=10000.0, key="alloc_amount"
            )
        with col4:
            alloc_currency = st.text_input("Currency", value="USD", key="alloc_currency")

        if st.button("Allocate", key="allocate_btn"):
            result = post_sync(
                f"/api/v1/bots/{alloc_bot_type}/{alloc_instance}/allocate",
                {"amount": alloc_amount, "currency": alloc_currency},
            )
            if result:
                st.success("Capital allocated!")
            else:
                st.error("Allocation failed")
    else:
        st.info("No capital pools configured")

with tab_limits:
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
