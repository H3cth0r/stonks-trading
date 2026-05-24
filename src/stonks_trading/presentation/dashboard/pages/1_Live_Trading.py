"""Live Trading - Real-time equity curves and positions.

All imports at module level per CLEAN architecture - no lazy imports.
"""

from time import sleep

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(page_title="Live Trading", page_icon="📊")

st.title("📊 Live Trading")

# Bot selector
bots_data = fetch_sync("/api/v1/bots")
bot_options = []
if bots_data and "bots" in bots_data and bots_data["bots"]:
    bot_options = [f"{b['bot_type']}/{b['instance_id']}" for b in bots_data["bots"]]

selected_bot = st.selectbox("Select Bot", bot_options if bot_options else ["No bots available"])
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 10, 300, 30)

if selected_bot and selected_bot != "No bots available":
    bot_type, instance_id = selected_bot.split("/", 1)

    # Bot Status Row
    col1, col2, col3, col4 = st.columns(4)
    status_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/status")

    with col1:
        status = status_data.get("status", "Unknown") if status_data else "Unknown"
        st.metric("Status", status)
    with col2:
        mode = status_data.get("mode", "Unknown") if status_data else "Unknown"
        st.metric("Mode", mode)
    with col3:
        last_seen = status_data.get("last_seen", "Never") if status_data else "Never"
        st.metric("Last Seen", last_seen)
    with col4:
        uptime = status_data.get("uptime_seconds", 0) if status_data else 0
        uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m" if uptime > 0 else "N/A"
        st.metric("Uptime", uptime_str)

    # Portfolio
    st.header("Portfolio")
    portfolio_data = fetch_sync("/api/v1/portfolio")
    if portfolio_data:
        col1, col2, col3 = st.columns(3)
        with col1:
            total_value = portfolio_data.get("total_value", 0)
            st.metric("Total Value", f"${total_value:,.2f}")
        with col2:
            cash = portfolio_data.get("cash", 0)
            st.metric("Cash", f"${cash:,.2f}")
        with col3:
            pnl = portfolio_data.get("unrealized_pnl", 0)
            st.metric("Unrealized P&L", f"${pnl:,.2f}")

        # Portfolio breakdown
        if "positions" in portfolio_data and portfolio_data["positions"]:
            st.subheader("Portfolio Breakdown")
            st.dataframe(portfolio_data["positions"], use_container_width=True)
    else:
        st.info("No portfolio data available")

    # Positions
    st.header("Positions")
    positions_data = fetch_sync("/api/v1/positions")
    if positions_data and "positions" in positions_data and positions_data["positions"]:
        positions = positions_data["positions"]
        st.dataframe(positions, use_container_width=True)

        # Position summary metrics
        long_positions = sum(1 for p in positions if p.get("side") == "LONG")
        short_positions = sum(1 for p in positions if p.get("side") == "SHORT")
        total_exposure = sum(p.get("market_value", 0) for p in positions)

        cols = st.columns(3)
        with cols[0]:
            st.metric("Long Positions", long_positions)
        with cols[1]:
            st.metric("Short Positions", short_positions)
        with cols[2]:
            st.metric("Total Exposure", f"${total_exposure:,.2f}")
    else:
        st.info("No open positions")

    # Recent Trades for selected bot
    st.header("Recent Trades")
    trades_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/trades", {"limit": 20})
    if trades_data and "trades" in trades_data and trades_data["trades"]:
        trades = trades_data["trades"]
        st.dataframe(trades, use_container_width=True)

        # Trade summary
        if trades:
            buy_trades = [t for t in trades if t.get("side") == "BUY"]
            sell_trades = [t for t in trades if t.get("side") == "SELL"]

            cols = st.columns(2)
            with cols[0]:
                st.metric("Buy Trades", len(buy_trades))
            with cols[1]:
                st.metric("Sell Trades", len(sell_trades))
    else:
        st.info("No recent trades")

    # Equity Curve (placeholder - would need historical data endpoint)
    st.header("Equity Curve")
    st.info("Equity curve visualization requires historical equity data endpoint (coming soon)")

else:
    st.warning("No bots available. Please register a bot first.")

# Auto-refresh logic
if auto_refresh:
    sleep(refresh_interval)
    st.rerun()
