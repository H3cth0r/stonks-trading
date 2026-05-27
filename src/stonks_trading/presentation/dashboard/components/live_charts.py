"""Live chart components for real-time visualization.

Provides Streamlit components for rendering live equity curves,
trade markers, and position charts with WebSocket updates.
"""

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator


class LiveEquityChart:
    """Streamlit component for live equity charting.

    Renders an equity curve with trade markers overlay.
    Updates via WebSocket streaming data.
    """

    def __init__(self, key: str = "live_equity"):
        """Initialize live equity chart.

        Args:
            key: Streamlit element key for state management
        """
        self.key = key
        self._chart_data: list[dict[str, Any]] = []
        self._trade_markers: list[dict[str, Any]] = []
        self._placeholder: DeltaGenerator | None = None

    def initialize(self) -> None:
        """Initialize the chart placeholder in Streamlit."""
        self._placeholder = st.empty()

    def update_data(
        self,
        equity_history: list[dict[str, Any]],
        trade_markers: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update chart with new data.

        Args:
            equity_history: List of equity points with timestamp and equity
            trade_markers: Optional list of trade markers
        """
        self._chart_data = equity_history
        if trade_markers:
            self._trade_markers = trade_markers

    def add_equity_point(self, timestamp: datetime, equity: float) -> None:
        """Add a single equity point.

        Args:
            timestamp: Point timestamp
            equity: Equity value
        """
        self._chart_data.append(
            {
                "timestamp": timestamp,
                "equity": equity,
            }
        )
        # Keep last 1000 points
        if len(self._chart_data) > 1000:
            self._chart_data = self._chart_data[-1000:]

    def render(self) -> None:
        """Render the chart to Streamlit.

        Uses line_chart for equity curve with trade markers as points overlay.
        """
        if not self._chart_data:
            st.info("Waiting for equity data...")
            return

        # Build equity dataframe
        df = pd.DataFrame(self._chart_data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        # Render line chart
        st.line_chart(df, use_container_width=True)

        # Render trade markers if available
        if self._trade_markers:
            self._render_trade_markers()

    def _render_trade_markers(self) -> None:
        """Render trade markers as buy/sell points.

        Uses scatter chart overlay for trade markers.
        """

        if not self._trade_markers:
            return

        buy_markers = [m for m in self._trade_markers if m.get("trade_type") == "BUY"]
        sell_markers = [m for m in self._trade_markers if m.get("trade_type") == "SELL"]

        if buy_markers:
            buy_df = pd.DataFrame(buy_markers)
            buy_df["timestamp"] = pd.to_datetime(buy_df["timestamp"])
            st.markdown(f"**Buy Trades:** {len(buy_markers)}")

        if sell_markers:
            sell_df = pd.DataFrame(sell_markers)
            sell_df["timestamp"] = pd.to_datetime(sell_df["timestamp"])
            st.markdown(f"**Sell Trades:** {len(sell_markers)}")

    def clear(self) -> None:
        """Clear all chart data."""
        self._chart_data = []
        self._trade_markers = []


class PositionChart:
    """Streamlit component for position visualization.

    Shows current positions as a pie chart or bar chart.
    """

    def __init__(self, key: str = "positions"):
        """Initialize position chart.

        Args:
            key: Streamlit element key
        """
        self.key = key
        self._positions: list[dict[str, Any]] = []

    def update_positions(self, positions: list[dict[str, Any]]) -> None:
        """Update positions data.

        Args:
            positions: List of position dictionaries
        """
        self._positions = positions

    def render_pie(self) -> None:
        """Render positions as pie chart."""
        if not self._positions:
            st.info("No open positions")
            return

        df = pd.DataFrame(self._positions)
        if "market_value" in df.columns and "symbol" in df.columns:
            st.bar_chart(df.set_index("symbol")["market_value"])
        else:
            st.info("Position data missing required fields")

    def render_bar(self) -> None:
        """Render positions as bar chart."""
        if not self._positions:
            st.info("No open positions")
            return

        df = pd.DataFrame(self._positions)
        if "market_value" in df.columns and "symbol" in df.columns:
            st.bar_chart(df.set_index("symbol")["market_value"])
        else:
            st.info("Position data missing required fields")


class TradeHistoryTable:
    """Streamlit component for trade history display.

    Shows recent trades in a formatted table.
    """

    def __init__(self, max_rows: int = 20):
        """Initialize trade history table.

        Args:
            max_rows: Maximum number of trades to display
        """
        self.max_rows = max_rows
        self._trades: list[dict[str, Any]] = []

    def update_trades(self, trades: list[dict[str, Any]]) -> None:
        """Update trades data.

        Args:
            trades: List of trade dictionaries
        """
        self._trades = trades[: self.max_rows]

    def render(self) -> None:
        """Render trade history table."""
        if not self._trades:
            st.info("No recent trades")
            return

        df = pd.DataFrame(self._trades)
        st.dataframe(df, use_container_width=True)
