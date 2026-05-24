"""Trade Log - Complete trade history with filters.

All imports at module level per CLEAN architecture - no lazy imports.
"""

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(page_title="Trade Log", page_icon="📋")

st.title("📋 Trade Log")

# Filters sidebar
st.sidebar.header("Filters")
symbol_filter = st.sidebar.text_input("Symbol", placeholder="BTCUSDT")
side_filter = st.sidebar.selectbox("Side", ["All", "BUY", "SELL"])
mode_filter = st.sidebar.selectbox("Mode", ["All", "DRY_RUN", "LIVE"])

# Date range (placeholder - would need date filters on API)
st.sidebar.markdown("---")
st.sidebar.info("Date range filters coming soon...")

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
    st.header("Summary")
    col1, col2, col3, col4 = st.columns(4)

    total_trades = len(trades)
    buy_trades = sum(1 for t in trades if t.get("side") == "BUY")
    sell_trades = sum(1 for t in trades if t.get("side") == "SELL")

    # Calculate P&L if available
    total_pnl = sum(
        t.get("realized_pnl", 0) or 0 for t in trades
    )

    with col1:
        st.metric("Total Trades", total_trades)
    with col2:
        st.metric("Buy Trades", buy_trades)
    with col3:
        st.metric("Sell Trades", sell_trades)
    with col4:
        st.metric("Total P&L", f"${total_pnl:,.2f}")

    # Trades table
    st.header("Trade History")
    st.dataframe(trades, use_container_width=True)

    # Export functionality
    st.sidebar.markdown("---")
    st.sidebar.header("Export")

    if st.sidebar.button("Export to JSON"):
        import json
        json_data = json.dumps(trades, indent=2, default=str)
        st.sidebar.download_button(
            label="Download JSON",
            data=json_data,
            file_name="trades.json",
            mime="application/json",
        )

    # CSV export
    if st.sidebar.button("Export to CSV"):
        import csv
        import io

        if trades:
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
    st.header("Trade Statistics")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("By Symbol")
        if trades:
            symbol_counts: dict[str, int] = {}
            for t in trades:
                symbol = t.get("symbol", "Unknown")
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            st.bar_chart(symbol_counts)

    with col2:
        st.subheader("By Side")
        if trades:
            side_counts = {"BUY": buy_trades, "SELL": sell_trades}
            st.bar_chart(side_counts)

else:
    st.info("No trades found matching the selected filters")
