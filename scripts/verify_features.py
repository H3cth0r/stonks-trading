#!/usr/bin/env python3
"""Verify live features match training features.

This script creates synthetic candles and computes features using both
the live feature computer and the training feature function.
"""

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from stonks_trading.domains.trading.neat.features import engineer_features
from stonks_trading.shared.features.live_features import LiveFeatureComputer
from stonks_trading.shared.ingest.adapter import Candle


def main() -> int:
    """Run feature parity verification."""
    print("Verifying feature parity...")

    # Create synthetic candles (250 hours of data)
    np.random.seed(42)
    base_price = 50000.0
    candles = []

    for i in range(250 * 60):  # 250 hours
        noise = np.random.randn() * 100
        candles.append(Candle(
            symbol="BTC_USD",
            venue="test",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=250 * 60 - i),
            open=base_price + noise,
            high=base_price + noise + 50,
            low=base_price + noise - 50,
            close=base_price + noise + 20,
            volume=10.0,
            closed=True,
        ))

    # Compute via live feature computer
    live = LiveFeatureComputer()
    for c in candles[:-1]:  # All but last
        live.on_candle(c)
    live_features = live.on_candle(candles[-1])

    if live_features is None:
        print("ERROR: Live features returned None", file=sys.stderr)
        return 1

    # Compute via training function
    df = pd.DataFrame([
        {"Open": c.open, "High": c.high, "Low": c.low, "Close": c.close, "Volume": c.volume}
        for c in candles
    ])
    df.index = pd.DatetimeIndex([c.timestamp for c in candles])
    train_df = engineer_features(df)
    train_features = train_df.iloc[-1]

    # Compare
    print("\n=== Feature Comparison ===")

    all_match = True
    tolerance = 0.001
    for key in ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]:
        live_val = live_features[key]
        train_val = float(train_features[key])
        diff = abs(live_val - train_val)
        match = diff < tolerance

        status = "✓" if match else "✗"
        print(f"{status} {key}: live={live_val:.6f}, train={train_val:.6f}, diff={diff:.6f}")

        if not match:
            all_match = False

    if all_match:
        print("\n✅ All features match within tolerance (0.001)")
        return 0
    else:
        print("\n❌ Some features differ", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
