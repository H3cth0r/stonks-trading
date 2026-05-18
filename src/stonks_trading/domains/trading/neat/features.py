"""Feature engineering extracted from NEAT/main.py lines 60-88.

This module provides the same feature engineering logic used in the
prototype, extracted for modularity and testability.

Original source: NEAT/main.py lines 60-88
"""

import numpy as np
import pandas as pd
import ta


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer features from raw OHLCV data.

    This function replicates the exact feature engineering from
    NEAT/main.py lines 60-88 for parity testing.

    Features produced:
        - trend_1h: (SMA50 - SMA200) / SMA200 on 1h data
        - rsi_1h: RSI(14) / 100 on 1h data
        - rsi_15m: RSI(14) / 100 on 15m data
        - roc: Rate of Change (10-period) on 1m data
        - bb_width: Bollinger Band width on 1m data

    Args:
        df: DataFrame with columns [Close, High, Low, Open, Volume]
            and Datetime index (1-minute frequency)

    Returns:
        DataFrame with original columns plus engineered features

    Note:
        - Forward fills from resampled timeframes to 1m
        - Drops rows with NaN values
        - Fills remaining NaN with 0
    """
    df = df.copy()
    df = df.sort_index().dropna()

    # --- Feature Engineering ---

    # 1. Resample to 1 Hour (Macro Trend)
    df_1h = df.resample("1h").agg({"Close": "last", "High": "max", "Low": "min"}).dropna()

    # 1H Trend (SMA 50 vs SMA 200)
    df_1h["sma50"] = ta.trend.SMAIndicator(df_1h["Close"], window=50).sma_indicator()
    df_1h["sma200"] = ta.trend.SMAIndicator(df_1h["Close"], window=200).sma_indicator()
    df_1h["trend_1h"] = (df_1h["sma50"] - df_1h["sma200"]) / df_1h["sma200"]

    # 1H RSI
    df_1h["rsi_1h"] = ta.momentum.RSIIndicator(df_1h["Close"], window=14).rsi() / 100.0

    # 2. Resample to 15 Min (Intermediate)
    df_15m = df.resample("15min").agg({"Close": "last"}).dropna()
    df_15m["rsi_15m"] = ta.momentum.RSIIndicator(df_15m["Close"], window=14).rsi() / 100.0

    # Map back to 1m
    df = df.join(df_1h[["trend_1h", "rsi_1h"]].reindex(df.index, method="ffill"))
    df = df.join(df_15m[["rsi_15m"]].reindex(df.index, method="ffill"))

    # 3. Micro Features (1m)
    # Volatility (Bollinger Width)
    bb = ta.volatility.BollingerBands(df["Close"], window=20)
    df["bb_width"] = bb.bollinger_wband()

    # ROC (Momentum)
    df["roc"] = ta.momentum.ROCIndicator(df["Close"], window=10).roc()

    df.dropna(inplace=True)
    df.fillna(0, inplace=True)

    return df


def get_feature_columns() -> list[str]:
    """Return list of feature column names.

    These match the columns used in NEAT/main.py line 115:
    self.feats = self.data[["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]].values
    """
    return ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]


def prepare_neat_inputs(
    features: np.ndarray,
    is_invested: bool,
    unrealized_pnl_pct: float,
) -> np.ndarray:
    """Prepare NEAT network inputs from features and position state.

    This matches the input preparation in NEAT/main.py lines 117-136:
    - is_invested: 1.0 if holdings > 0 else -1.0
    - unrealized_pnl_pct: (price - entry_price) / entry_price
    - 5 market features
    Total: 7 inputs

    Args:
        features: Array of 5 market features [trend_1h, rsi_1h, rsi_15m, roc, bb_width]
        is_invested: Whether position is currently open
        unrealized_pnl_pct: Unrealized P&L percentage

    Returns:
        Array of 7 clipped and cleaned inputs for NEAT network
    """
    # Is Invested? (Binary 1.0 or -1.0)
    invested_flag = 1.0 if is_invested else -1.0

    # Combine [Invested, Unr_PnL, 5 Market Indicators] = 7 Inputs
    state = np.hstack(([invested_flag, unrealized_pnl_pct], features))

    # Clean inputs - clip to prevent extreme values and handle NaN
    return np.nan_to_num(np.clip(state, -5.0, 5.0))


def load_and_engineer(
    data_path: str,
    train_split: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load data and apply feature engineering.

    Mirrors the load_data() function in NEAT/main.py lines 44-91.

    Args:
        data_path: Path to CSV file with OHLCV data
        train_split: Fraction of data to use for training (0.8 = 80%)

    Returns:
        Tuple of (train_df, test_df) with engineered features
    """
    cols = ["Datetime", "Close", "High", "Low", "Open", "Volume"]

    df = pd.read_csv(
        data_path,
        skiprows=[1, 2],  # MultiIndex CSV format
        header=0,
        names=cols,
        parse_dates=["Datetime"],
        index_col="Datetime",
        dtype={"Volume": "float64"},
        na_values=["NA", "N/A", ""],
        keep_default_na=True,
    )

    df = engineer_features(df)

    split = int(len(df) * train_split)
    return df.iloc[:split], df.iloc[split:]
