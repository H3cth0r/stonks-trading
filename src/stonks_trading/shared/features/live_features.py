"""Live feature computation from streaming candles.

This module computes features on streaming data, maintaining rolling
windows for 1H and 15M resampling. It uses the SAME ta library calls
as the training features to ensure parity between training and live inference.

MUST produce identical results to training features (features.py).
"""

import pandas as pd

from stonks_trading.domains.trading.neat.features import engineer_features
from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.logger import logger


class LiveFeatureComputer:
    """Compute features on streaming data.

    Maintains rolling windows for 1H and 15M resampling, computing
    the same features used during training:
    - trend_1h: (SMA50 - SMA200) / SMA200 on 1h data
    - rsi_1h: RSI(14) / 100 on 1h data
    - rsi_15m: RSI(14) / 100 on 15m data
    - roc: Rate of Change (10-period) on 1m data
    - bb_width: Bollinger Band width on 1m data

    Requires at least 200 hours of 1m data (200 * 60 = 12,000 candles)
    to compute SMA200 for the 1H trend feature.

    Example:
        computer = LiveFeatureComputer(window_hours=200)
        for candle in stream:
            features = computer.on_candle(candle)
            if features:
                # Use features for inference
                pass
    """

    def __init__(self, window_hours: int = 200) -> None:
        """Initialize with window size for SMA200.

        Args:
            window_hours: Number of hours of historical data to maintain.
                         Default 200 allows SMA200 computation on 1H data.
        """
        self.window_hours = window_hours
        self._1m_data: dict[str, list[Candle]] = {}  # symbol -> recent candles
        self._max_candles = window_hours * 60 + 1000  # Buffer for safety

    def on_candle(self, candle: Candle) -> dict[str, float] | None:
        """Process new closed candle, return features if computable.

        Adds the candle to the rolling window for its symbol, trims old data,
        and computes features if enough data is available.

        Args:
            candle: Normalized closed candle from adapter

        Returns:
            Dictionary with computed features, or None if insufficient data
        """
        symbol = candle.symbol

        if symbol not in self._1m_data:
            self._1m_data[symbol] = []

        self._1m_data[symbol].append(candle)

        # Trim old data
        if len(self._1m_data[symbol]) > self._max_candles:
            self._1m_data[symbol] = self._1m_data[symbol][-self._max_candles:]

        # Compute features if we have enough data
        # Need at least 200 hours for SMA200 computation
        min_candles = 200 * 60  # 200 hours * 60 minutes
        if len(self._1m_data[symbol]) < min_candles:
            logger.debug(
                "Insufficient data for feature computation",
                symbol=symbol,
                candles=len(self._1m_data[symbol]),
                min_required=min_candles,
            )
            return None

        return self._compute(symbol)

    def _compute(self, symbol: str) -> dict[str, float]:
        """Compute features from accumulated candles.

        Uses the SAME feature engineering logic as training
        (domains/trading/neat/features.py) to ensure parity.

        Args:
            symbol: Symbol to compute features for

        Returns:
            Dictionary with feature values
        """
        candles = self._1m_data[symbol]

        # Build DataFrame matching training format
        df = pd.DataFrame([
            {
                "Open": c.open,
                "High": c.high,
                "Low": c.low,
                "Close": c.close,
                "Volume": c.volume,
            }
            for c in candles
        ])

        # Create datetime index (required for resampling)
        df.index = pd.DatetimeIndex([c.timestamp for c in candles])

        # Use SAME feature computation as training
        features_df = engineer_features(df)

        # Return last row features
        last = features_df.iloc[-1]
        return {
            "trend_1h": float(last["trend_1h"]),
            "rsi_1h": float(last["rsi_1h"]),
            "rsi_15m": float(last["rsi_15m"]),
            "roc": float(last["roc"]),
            "bb_width": float(last["bb_width"]),
        }

    def get_feature_df(self, symbol: str) -> pd.DataFrame | None:
        """Get full feature DataFrame for a symbol.

        Returns the complete feature DataFrame including all historical
        data for the symbol. Useful for debugging or analysis.

        Args:
            symbol: Symbol to get features for

        Returns:
            DataFrame with all features, or None if insufficient data
        """
        if symbol not in self._1m_data:
            return None

        candles = self._1m_data[symbol]
        min_candles = 200 * 60

        if len(candles) < min_candles:
            return None

        df = pd.DataFrame([
            {
                "Open": c.open,
                "High": c.high,
                "Low": c.low,
                "Close": c.close,
                "Volume": c.volume,
            }
            for c in candles
        ])

        df.index = pd.DatetimeIndex([c.timestamp for c in candles])

        return engineer_features(df)

    def get_stats(self, symbol: str | None = None) -> dict:
        """Get statistics about the feature computer.

        Args:
            symbol: Optional symbol to get stats for. If None, returns stats
                   for all symbols.

        Returns:
            Dictionary with statistics
        """
        if symbol:
            if symbol not in self._1m_data:
                return {"symbol": symbol, "candles": 0, "has_features": False}

            candles = self._1m_data[symbol]
            min_candles = 200 * 60
            return {
                "symbol": symbol,
                "candles": len(candles),
                "has_features": len(candles) >= min_candles,
                "time_span_hours": len(candles) / 60,
            }

        # Stats for all symbols
        return {
            "symbols": list(self._1m_data.keys()),
            "total_candles": sum(len(candles) for candles in self._1m_data.values()),
            "symbol_stats": {
                symbol: self.get_stats(symbol)
                for symbol in self._1m_data
            },
        }

    def reset(self, symbol: str | None = None) -> None:
        """Clear accumulated data.

        Args:
            symbol: Symbol to clear. If None, clears all symbols.
        """
        if symbol:
            if symbol in self._1m_data:
                del self._1m_data[symbol]
                logger.info("Reset feature computer for symbol", symbol=symbol)
        else:
            self._1m_data.clear()
            logger.info("Reset feature computer for all symbols")
