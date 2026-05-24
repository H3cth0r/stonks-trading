"""Operations Hub - Bot fleet overview and command center.

All imports at module level per CLEAN architecture - no lazy imports.
"""

from time import sleep

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(page_title="Operations Hub", page_icon="🎛️")

st.title("🎛️ Operations Hub")

# Auto-refresh control
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 10, 300, 30)

# Bot Fleet Overview
st.header("Bot Fleet")
bots_data = fetch_sync("/api/v1/bots")
if bots_data and "bots" in bots_data and bots_data["bots"]:
    bots_df = bots_data["bots"]
    st.dataframe(bots_df, use_container_width=True)

    # Bot status summary
    col1, col2, col3, col4 = st.columns(4)
    total_bots = len(bots_df)
    active_bots = sum(1 for b in bots_df if b.get("status") == "active")
    idle_bots = sum(1 for b in bots_df if b.get("status") == "idle")
    error_bots = sum(1 for b in bots_df if b.get("status") == "error")

    with col1:
        st.metric("Total Bots", total_bots)
    with col2:
        st.metric("Active", active_bots)
    with col3:
        st.metric("Idle", idle_bots)
    with col4:
        st.metric("Errors", error_bots)
else:
    st.info("No bots registered")

# Activity Timeline
st.header("Activity Timeline")
activity_data = fetch_sync("/api/v1/activity", {"limit": 50})
if activity_data and "activities" in activity_data and activity_data["activities"]:
    activities = activity_data["activities"]
    st.dataframe(activities, use_container_width=True)

    # Activity type breakdown
    if activities:
        type_counts: dict[str, int] = {}
        for activity in activities:
            activity_type = activity.get("type", "unknown")
            type_counts[activity_type] = type_counts.get(activity_type, 0) + 1

        if type_counts:
            st.subheader("Activity Types")
            cols = st.columns(min(len(type_counts), 4))
            for i, (act_type, count) in enumerate(type_counts.items()):
                with cols[i % 4]:
                    st.metric(act_type.replace("_", " ").title(), count)
else:
    st.info("No activity recorded")

# Balances
st.header("Balances")
balances_data = fetch_sync("/api/v1/balances")
if balances_data and "balances" in balances_data and balances_data["balances"]:
    balances = balances_data["balances"]
    st.dataframe(balances, use_container_width=True)

    # Total portfolio value calculation
    total_value = sum(b.get("total_usd_value", 0) for b in balances)
    st.metric("Total Portfolio Value (USD)", f"${total_value:,.2f}")
else:
    st.info("No balance data available")

# Live Prices
st.header("Live Prices")
prices_data = fetch_sync("/api/v1/market/prices")
if prices_data and "prices" in prices_data and prices_data["prices"]:
    prices = prices_data["prices"]
    st.dataframe(prices, use_container_width=True)
else:
    st.info("No market data available")

# Auto-refresh logic
if auto_refresh:
    sleep(refresh_interval)
    st.rerun()
