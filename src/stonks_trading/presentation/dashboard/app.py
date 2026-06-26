"""Streamlit dashboard entry point.

Pages:
    0. Operations Hub - Bot fleet overview
    1. Live Trading - Real-time equity and positions
    2. Training Progress - Fitness charts
    3. Model Registry - Genome management
    4. Backtest - Run/view backtests
    5. Trade Log - Filterable history
    6. Risk Dashboard - Drawdown and kill switch

All imports at module level per CLEAN architecture - no lazy imports.
"""

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(
    page_title="Stonks Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Stonks Trading Dashboard")

st.sidebar.title("Navigation")
st.sidebar.info("Select a page from the sidebar to view different aspects of the trading system.")

st.markdown("""
## Welcome to the Stonks Trading Dashboard

This dashboard provides real-time monitoring of:

- **Portfolio Overview** - Master portfolio view with real-time metrics
- **Live Trading** - Real-time equity curves, positions, and trades
- **Strategy Management** - NEAT training runs and fitness evolution
- **Performance Analytics** - Historical backtest and live performance
- **Trade Explorer** - Complete trade history with filters
- **Risk Monitor** - Drawdown monitoring and kill switch
- **Data Explorer** - Market data backfill and visualization

### Quick Stats
""")

# Fetch and display quick stats
col1, col2, col3, col4 = st.columns(4)

# Fetch bots count
bots_data = fetch_sync("/api/v1/bots")
bots_count = len(bots_data.get("bots", [])) if bots_data else 0

# Fetch positions count
positions_data = fetch_sync("/api/v1/positions")
positions_count = len(positions_data.get("positions", [])) if positions_data else 0

# Fetch recent trades count (last 24h would need time filter)
trades_data = fetch_sync("/api/v1/trades", {"limit": 100})
trades_count = len(trades_data.get("trades", [])) if trades_data else 0

# Fetch portfolio value
portfolio_data = fetch_sync("/api/v1/portfolio")
portfolio_value = portfolio_data.get("total_value", 0.0) if portfolio_data else 0.0

with col1:
    st.metric("Active Bots", bots_count)
with col2:
    st.metric("Open Positions", positions_count)
with col3:
    st.metric("Recent Trades", trades_count)
with col4:
    st.metric("Portfolio Value", f"${portfolio_value:,.2f}")

st.info("👈 Select a page from the sidebar to get started!")

# Display connection status
st.sidebar.markdown("---")
st.sidebar.subheader("Connection Status")
health = fetch_sync("/health")
if health and health.get("api_healthy") is True:
    api_status = health.get("status", "unknown")
    if api_status == "healthy":
        st.sidebar.success("✅ API Connected")
    else:
        st.sidebar.warning(f"⚠️ API {api_status.title()}")
else:
    st.sidebar.error("❌ API Disconnected")
