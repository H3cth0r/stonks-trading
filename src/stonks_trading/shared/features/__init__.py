"""Live feature engineering module.

Provides real-time feature computation from streaming candles.
Must produce identical results to the training features module
(domains/trading/neat/features.py).
"""

from stonks_trading.shared.features.live_features import LiveFeatureComputer

__all__ = ["LiveFeatureComputer"]
