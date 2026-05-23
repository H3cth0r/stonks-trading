"""NEAT Feature Engineering with exact parity to NEAT/main.py.

Computes the 5 market features used in NEAT state vector:
- trend_1h: (SMA50 - SMA200) / SMA200 on 1h data
- rsi_1h: RSI(14) on 1h / 100.0
- rsi_15m: RSI(14) on 15m / 100.0
- roc: Rate of Change on 1m
- bb_width: Bollinger Band width on 1m

These match exactly the features in NEAT/main.py load_data() lines 58-86
and TradingEnv.get_state() lines 117-136.
"""

from typing import Any

import numpy as np
import pandas as pd
import ta


def compute_features(candles: list[dict[str, Any]]) -> dict[str, float]:
    """Compute NEAT market features from 1m OHLCV candles.

    Matches NEAT/main.py load_data() feature engineering exactly.

    Args:
        candles: List of 1m OHLCV candles with keys: open, high, low, close, volume.
            Optionally may include 'datetime' or 'timestamp' key for time indexing.

    Returns:
        Dictionary with 5 market features:
        - trend_1h: (SMA50 - SMA200) / SMA200
        - rsi_1h: RSI(14) / 100.0
        - rsi_15m: RSI(14) / 100.0
        - roc: Rate of Change (10 period)
        - bb_width: Bollinger Band width (20 period)
    """
    if len(candles) < 200:
        return {
            "trend_1h": 0.0,
            "rsi_1h": 0.5,
            "rsi_15m": 0.5,
            "roc": 0.0,
            "bb_width": 0.0,
        }

    # Check if candles have datetime information
    has_datetime = any("datetime" in c or "timestamp" in c for c in candles)

    if has_datetime:
        # Use datetime index for resampling
        df = pd.DataFrame(candles)
        if "datetime" in df.columns:
            df = df.set_index("datetime")
        elif "timestamp" in df.columns:
            df = df.set_index("timestamp")
        closes = df["close"]
    else:
        # Create sequential datetime index for resampling
        # Assume 1 minute intervals starting from a fixed point
        df = pd.DataFrame(candles)
        start_time = pd.Timestamp("2024-01-01")
        df.index = pd.date_range(start=start_time, periods=len(df), freq="1min")
        closes = df["close"]

    # Resample to 1h for trend and RSI (NEAT/main.py line 61)
    df_1h = closes.resample("1h").last().dropna()

    # 1H Trend (SMA 50 vs SMA 200) - NEAT/main.py lines 63-66
    if len(df_1h) >= 200:
        sma50 = ta.trend.SMAIndicator(df_1h, 50).sma_indicator()
        sma200 = ta.trend.SMAIndicator(df_1h, 200).sma_indicator()
        trend_1h = (sma50 - sma200) / sma200
        trend_1h_value = trend_1h.iloc[-1] if not trend_1h.empty else 0.0
    else:
        trend_1h_value = 0.0

    # 1H RSI - NEAT/main.py line 69
    if len(df_1h) >= 14:
        rsi_1h = ta.momentum.RSIIndicator(df_1h, 14).rsi() / 100.0
        rsi_1h_value = rsi_1h.iloc[-1] if not rsi_1h.empty else 0.5
    else:
        rsi_1h_value = 0.5

    # 15M RSI - NEAT/main.py lines 72-73
    df_15m = closes.resample("15min").last().dropna()
    if len(df_15m) >= 14:
        rsi_15m = ta.momentum.RSIIndicator(df_15m, 14).rsi() / 100.0
        rsi_15m_value = rsi_15m.iloc[-1] if not rsi_15m.empty else 0.5
    else:
        rsi_15m_value = 0.5

    # ROC (Momentum) - NEAT/main.py line 85
    if len(closes) >= 11:
        roc = ta.momentum.ROCIndicator(closes, 10).roc()
        roc_value = roc.iloc[-1] if not roc.empty else 0.0
    else:
        roc_value = 0.0

    # BB Width - NEAT/main.py lines 81-82
    if len(closes) >= 20:
        bb = ta.volatility.BollingerBands(closes, window=20)
        bb_width = bb.bollinger_wband()
        bb_width_value = bb_width.iloc[-1] if not bb_width.empty else 0.0
    else:
        bb_width_value = 0.0

    return {
        "trend_1h": float(trend_1h_value),
        "rsi_1h": float(rsi_1h_value),
        "rsi_15m": float(rsi_15m_value),
        "roc": float(roc_value),
        "bb_width": float(bb_width_value),
    }


def compute_state_vector(
    price: float,
    is_invested: bool,
    unrealized_pnl: float,
    features: dict[str, float],
) -> list[float]:
    """Build 7-element NEAT state vector.

    From NEAT/main.py TradingEnv.get_state() lines 117-136.

    Args:
        price: Current price (unused but kept for interface).
        is_invested: True if in a position.
        unrealized_pnl: Unrealized P&L percentage.
        features: Market features from compute_features().

    Returns:
        7-element state vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
        with values clipped to [-5, 5] and NaN handled.
    """
    # Position state
    position_state = [1.0 if is_invested else -1.0, unrealized_pnl]

    # Market features
    mkt = [
        features.get("trend_1h", 0.0),
        features.get("rsi_1h", 0.5),
        features.get("rsi_15m", 0.5),
        features.get("roc", 0.0),
        features.get("bb_width", 0.0),
    ]

    # Combine: [Invested, Unr_PnL, 5 Market Indicators] = 7 Inputs
    state = np.hstack((position_state, mkt))

    # Clean inputs - clip to [-5, 5] and handle NaN (NEAT/main.py line 136)
    result: list[float] = np.nan_to_num(np.clip(state, -5.0, 5.0)).tolist()
    return result


# Constants from NEAT/main.py
DECISION_THRESHOLD = 0.6
TRANSACTION_FEE = 0.001
MIN_TRADE_INTERVAL = 15
INITIAL_CAPITAL = 10000.0
