"""Live feature engineering module.

Provides real-time feature computation from streaming candles.
Must produce identical results to the training features module
(domains/strategies/neat_swing/features.py).
"""

from stonks_trading.shared.features.live_features import LiveFeatureComputer

__all__ = ["LiveFeatureComputer"]
