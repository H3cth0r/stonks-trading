"""Risk Dashboard - Drawdown monitoring and kill switch.

All imports at module level per CLEAN architecture - no lazy imports.
"""

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Risk Dashboard", page_icon="⚠️")

st.title("⚠️ Risk Dashboard")

# Risk Summary
st.header("Risk Summary")
portfolio_data = fetch_sync("/api/v1/portfolio")

if portfolio_data:
    col1, col2, col3 = st.columns(3)

    with col1:
        # Current drawdown calculation (placeholder)
        current_drawdown = portfolio_data.get("current_drawdown", 0)
        st.metric(
            "Current Drawdown",
            f"{current_drawdown:.2%}",
            delta=None,
        )

    with col2:
        max_drawdown = portfolio_data.get("max_drawdown", 0)
        st.metric("Max Drawdown", f"{max_drawdown:.2%}")

    with col3:
        daily_var = portfolio_data.get("daily_var", 0)
        st.metric("Daily VaR (95%)", f"${daily_var:,.2f}")

    # Risk limits
    st.subheader("Risk Limits")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        daily_loss_limit = st.number_input(
            "Daily Loss Limit ($)",
            min_value=0,
            value=1000,
            step=100,
        )
    with col2:
        max_position_size = st.number_input(
            "Max Position Size ($)",
            min_value=0,
            value=10000,
            step=1000,
        )
    with col3:
        max_drawdown_limit = st.slider(
            "Max Drawdown Limit (%)",
            min_value=1,
            max_value=50,
            value=10,
        )
    with col4:
        max_trades_per_day = st.number_input(
            "Max Trades/Day",
            min_value=1,
            value=20,
        )

    if st.button("Update Risk Limits"):
        st.success("Risk limits updated (simulation)")

else:
    st.info("No portfolio data available for risk metrics")

# Daily P&L (placeholder)
st.header("Daily P&L")
st.info("Daily P&L tracking requires historical daily summary data. Implementation pending.")

# Risk Events
st.header("Risk Events")
events_data = fetch_sync("/api/v1/risk/events", {"limit": 20})
if events_data and "events" in events_data and events_data["events"]:
    events = events_data["events"]
    st.dataframe(events, use_container_width=True)

    # Event summary
    if events:
        col1, col2, col3 = st.columns(3)
        total_events = len(events)
        warnings = sum(1 for e in events if e.get("severity") == "WARNING")
        critical = sum(1 for e in events if e.get("severity") == "CRITICAL")

        with col1:
            st.metric("Total Events", total_events)
        with col2:
            st.metric("Warnings", warnings)
        with col3:
            st.metric("Critical", critical)
else:
    st.info("No risk events recorded")

# Kill Switch Section
st.markdown("---")
st.header("🚨 Kill Switch")

st.error("WARNING: This will stop all trading immediately!")
st.warning("""
Activating the kill switch will:
- Cancel all open orders
- Close all positions
- Disable all bots
- Send emergency notifications

This action cannot be undone.
""")

# Confirmation for kill switch
with st.expander("Activate Kill Switch"):
    confirmation = st.text_input(
        "Type 'EMERGENCY STOP' to confirm",
        placeholder="EMERGENCY STOP",
    )

    if st.button("ACTIVATE KILL SWITCH", type="primary"):
        if confirmation == "EMERGENCY STOP":
            result = post_sync("/api/v1/risk/kill-switch", {"reason": "Manual activation from dashboard"})
            if result:
                st.error("KILL SWITCH ACTIVATED! All trading has been halted.")
                st.json(result)
            else:
                st.error("Failed to activate kill switch. Contact system administrator immediately!")
        else:
            st.error("Confirmation text does not match. Kill switch NOT activated.")

# Footer with last update
st.sidebar.markdown("---")
st.sidebar.info("Risk data updates every 30 seconds")
