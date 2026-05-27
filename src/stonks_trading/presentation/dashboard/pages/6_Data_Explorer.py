"""Data Explorer - Market data search and visualization.

All imports at module level per CLEAN architecture.
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Data Explorer", page_icon="📊", layout="wide")

st.title("📊 Data Explorer")

# === Sidebar: Period Filter ===
st.sidebar.header("Time Range")
period = st.sidebar.selectbox(
    "Period",
    options=["1H", "1D", "1W", "1M", "YTD", "1Y", "MAX"],
    index=1,
)


def get_period_filter(period: str) -> tuple[datetime, datetime | None]:
    """Convert period string to start/end datetimes."""
    now = datetime.now()
    if period == "1H":
        return now - timedelta(hours=1), None
    elif period == "1D":
        return now - timedelta(days=1), None
    elif period == "1W":
        return now - timedelta(weeks=1), None
    elif period == "1M":
        return now - timedelta(days=30), None
    elif period == "YTD":
        return datetime(now.year, 1, 1), None
    elif period == "1Y":
        return now - timedelta(days=365), None
    else:  # MAX
        return datetime(1970, 1, 1), None


# === Main Content ===
col1, col2 = st.columns([3, 1])

with col1:
    ticker = (
        st.text_input(
            "Ticker Symbol",
            value="BTC_USD",
            help="Enter symbol in format: BTC_USD",
        )
        .strip()
        .upper()
    )

with col2:
    st.markdown("###")  # Vertical spacing
    backfill_btn = st.button("Start Backfill", type="primary")

# === Backfill Progress ===
if "backfill_job_id" in st.session_state:
    job_id = st.session_state.backfill_job_id
    status = fetch_sync(f"/api/v1/backfill/jobs/{job_id}")

    if status:
        if status.get("status") == "running":
            progress = status.get("progress", 0)
            st.progress(progress)
            st.text(f"Downloading... {progress * 100:.0f}%")
        elif status.get("status") == "completed":
            st.success(f"Downloaded {status.get('candles_downloaded', 0):,} candles")
            del st.session_state.backfill_job_id
        elif status.get("status") == "failed":
            st.error(f"Backfill failed: {status.get('error', 'Unknown error')}")
            del st.session_state.backfill_job_id

# === Backfill Button Handler ===
if backfill_btn and ticker:
    response = post_sync(
        "/api/v1/backfill/massive",
        {"symbol": ticker, "days": 730},
    )
    if response and "job_id" in response:
        st.session_state.backfill_job_id = response["job_id"]
        st.rerun()

# === Price Chart ===
st.markdown("### Price Chart")

start_dt, _ = get_period_filter(period)

candles_data = fetch_sync(
    "/api/v1/market/candles/BTC_USD",
    {"start": start_dt.isoformat()} if start_dt else None,
)

if candles_data and candles_data.get("candles"):
    df = pd.DataFrame(candles_data["candles"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    st.line_chart(df["close"])
else:
    st.info("No data available. Click 'Start Backfill' to download data.")

# === OHLCV Table ===
st.markdown("### OHLCV Data")

if candles_data and candles_data.get("candles"):
    df = pd.DataFrame(candles_data["candles"])
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(
        df[["timestamp", "open", "high", "low", "close", "volume"]],
        use_container_width=True,
        hide_index=True,
    )
