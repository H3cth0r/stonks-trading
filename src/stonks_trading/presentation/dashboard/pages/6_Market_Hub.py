"""Market Hub - Market Data, Trade History, and Backfill Management.

Phase 10C: Consolidates Data Explorer and Trade Explorer.
"""

import csv
import io
import json
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Market Hub", page_icon="📊", layout="wide")

st.title("📊 Market Hub")

# Tabs: Market Data | Trade History
tab_market, tab_trades = st.tabs(["Market Data", "Trade History"])

# =============================================================================
# MARKET DATA TAB (from old Data Explorer page 6)
# =============================================================================
with tab_market:
    # Sidebar: Period Filter
    st.sidebar.header("Time Range")
    period = st.sidebar.selectbox(
        "Period",
        options=["1H", "1D", "1W", "1M", "YTD", "1Y", "MAX"],
        index=1,
    )

    # Backfill Days Configuration
    st.sidebar.header("Backfill Options")
    backfill_days = st.sidebar.number_input(
        "Days to backfill",
        min_value=1,
        max_value=730,
        value=7,
        help="Number of days of historical data to download (max 730 = 2 years)",
    )

    # Check for job_id in query params
    query_params = st.query_params
    if "job_id" in query_params and "backfill_job_id" not in st.session_state:
        st.session_state.backfill_job_id = query_params["job_id"]

    def get_period_filter(period: str) -> tuple[datetime, datetime | None]:
        """Convert period string to start/end datetimes."""
        now = datetime.utcnow()
        if period == "1H":
            return now - timedelta(hours=1), None
        elif period == "1D":
            return now - timedelta(days=1), None
        elif period == "1W":
            return now - timedelta(weeks=1), None
        elif period == "1M":
            return now - timedelta(days=30), None
        elif period == "YTD":
            return datetime(datetime.utcnow().year, 1, 1), None
        elif period == "1Y":
            return now - timedelta(days=365), None
        else:  # MAX
            return datetime(1970, 1, 1), None

    # Instrument Selection
    st.header("Instrument Selection")

    instruments_data = fetch_sync("/api/v1/instruments")
    if instruments_data and instruments_data.get("instruments"):
        instruments = instruments_data["instruments"]
        symbol_options = [i["symbol"] for i in instruments]
    else:
        symbol_options = ["BTC_USD", "ETH_USD"]

    symbol_options = symbol_options + ["+ Register New Symbol"]

    col1, col2 = st.columns([3, 1])

    with col1:
        # Default to BTC_USD if in list, otherwise first item
        default_idx = 0
        if "BTC_USD" in symbol_options:
            default_idx = symbol_options.index("BTC_USD")
        selected_symbol = st.selectbox(
            "Symbol",
            options=symbol_options,
            index=default_idx,
            help="Select a registered instrument",
        )

    if selected_symbol == "+ Register New Symbol":
        with st.expander("Register New Instrument"):
            new_symbol = (
                st.text_input(
                    "New Symbol (e.g., SOL_USD)",
                    value="",
                    help="Enter symbol in format: SYMBOL_USD",
                )
                .strip()
                .upper()
            )
            auto_backfill = st.checkbox("Auto-backfill 2 years", value=True)
            if st.button("Register"):
                if new_symbol:
                    response = post_sync(
                        "/api/v1/instruments",
                        {"symbol": new_symbol, "auto_backfill": auto_backfill},
                    )
                    if response:
                        st.success(f"Registered {new_symbol}")
                        st.rerun()
                    else:
                        st.error("Failed to register instrument")

        if not selected_symbol or selected_symbol == "+ Register New Symbol":
            selected_symbol = "BTC_USD"

    ticker = selected_symbol

    with col2:
        st.markdown("###")
        backfill_btn = st.button("Start Backfill", type="primary")

    # Backfill Progress
    if "backfill_job_id" in st.session_state:
        job_id = st.session_state.backfill_job_id
        status = fetch_sync(f"/api/v1/backfill/jobs/{job_id}")

        if status:
            if status.get("status") == "running":
                progress = status.get("progress", 0)
                st.progress(progress)
                st.text(f"Downloading... {progress * 100:.0f}%")
                st.query_params["job_id"] = job_id
            elif status.get("status") == "completed":
                st.success(f"Downloaded {status.get('candles_downloaded', 0):,} candles")
                st.query_params["job_id"] = job_id
            elif status.get("status") == "failed":
                st.error(f"Backfill failed: {status.get('error', 'Unknown error')}")
                st.query_params["job_id"] = job_id

    # Backfill Button Handler
    if backfill_btn and ticker:
        response = post_sync(
            "/api/v1/backfill/massive",
            {"symbol": ticker, "days": backfill_days},
        )
        if response and "job_id" in response:
            st.session_state.backfill_job_id = response["job_id"]
            st.query_params["job_id"] = response["job_id"]
            st.rerun()

    # Price Chart
    st.markdown("### Price Chart")

    start_dt, _ = get_period_filter(period)

    candles_data = fetch_sync(
        f"/api/v1/market/candles/{ticker}",
        {"start": start_dt.isoformat()} if start_dt else None,
    )

    if candles_data and candles_data.get("candles"):
        df = pd.DataFrame(candles_data["candles"])
        chart_df = df[["timestamp", "close"]].copy()
        chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
        chart_df["close"] = pd.to_numeric(chart_df["close"], errors="coerce")
        chart_df = chart_df.dropna(subset=["close"])
        chart_df = chart_df.reset_index(drop=True)

        fig = px.line(chart_df, x="timestamp", y="close", title=f"{ticker} Price")
        fig.update_layout(yaxis_title="Price (USD)", xaxis_title="Time")
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available. Click 'Start Backfill' to download data.")

    # OHLCV Table
    st.markdown("### OHLCV Data")

    if candles_data and candles_data.get("candles"):
        df = pd.DataFrame(candles_data["candles"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(
            df[["timestamp", "open", "high", "low", "close", "volume"]],
            use_container_width=True,
            hide_index=True,
        )

# =============================================================================
# TRADE HISTORY TAB (from old Trade Explorer page 4)
# =============================================================================
with tab_trades:
    st.header("Trade History")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_filter = st.text_input("Symbol", placeholder="BTC_USD")
    with col2:
        side_filter = st.selectbox("Side", ["All", "BUY", "SELL"])
    with col3:
        mode_filter = st.selectbox("Mode", ["All", "DRY_RUN", "LIVE"])

    # Build query params
    params: dict[str, str | int] = {"limit": 100}
    if symbol_filter:
        params["symbol"] = symbol_filter.upper()
    if side_filter != "All":
        params["side"] = side_filter
    if mode_filter != "All":
        params["mode"] = mode_filter

    # Fetch trades
    trades_data = fetch_sync("/api/v1/trades", params)

    if trades_data and "trades" in trades_data and trades_data["trades"]:
        trades = trades_data["trades"]

        # Trade summary metrics
        st.subheader("Summary")
        col1, col2, col3, col4 = st.columns(4)

        total_trades = len(trades)
        buy_trades = sum(1 for t in trades if t.get("side") == "BUY")
        sell_trades = sum(1 for t in trades if t.get("side") == "SELL")
        total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in trades)

        with col1:
            st.metric("Total Trades", total_trades)
        with col2:
            st.metric("Buy Trades", buy_trades)
        with col3:
            st.metric("Sell Trades", sell_trades)
        with col4:
            st.metric("Total P&L", f"${total_pnl:,.2f}")

        # Trades table
        st.dataframe(trades, use_container_width=True)

        # Export functionality
        st.sidebar.markdown("---")
        st.sidebar.header("Export")

        if st.sidebar.button("Export to JSON"):
            json_data = json.dumps(trades, indent=2, default=str)
            st.sidebar.download_button(
                label="Download JSON",
                data=json_data,
                file_name="trades.json",
                mime="application/json",
            )

        if st.sidebar.button("Export to CSV") and trades:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=trades[0].keys())
            writer.writeheader()
            writer.writerows(trades)
            csv_data = output.getvalue()

            st.sidebar.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="trades.csv",
                mime="text/csv",
            )

        # Trade statistics
        st.subheader("Trade Statistics")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("By Symbol")
            if trades:
                symbol_counts: dict[str, int] = {}
                for t in trades:
                    symbol = t.get("symbol", "Unknown")
                    symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
                st.bar_chart(symbol_counts)

        with col2:
            st.markdown("By Side")
            if trades:
                side_counts = {"BUY": buy_trades, "SELL": sell_trades}
                st.bar_chart(side_counts)

    else:
        st.info("No trades found matching the selected filters")

# Auto-refresh
if st.sidebar.checkbox("Auto-refresh", value=True):
    from time import sleep

    sleep(30)
    st.rerun()
