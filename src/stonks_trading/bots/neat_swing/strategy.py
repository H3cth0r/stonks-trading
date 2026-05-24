"""NEAT Swing Strategy with exact parity to NEAT/main.py.

This strategy implements the exact trading logic from NEAT/main.py:
- DECISION_THRESHOLD = 0.6
- TRANSACTION_FEE = 0.001
- MIN_TRADE_INTERVAL = 15
- 7-element state vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
- Uses RecurrentNetwork (not feedforward)
- All-in / all-out trading logic
"""

from typing import Any

import numpy as np
from neat import Config, DefaultGenome
from neat.nn import RecurrentNetwork

from stonks_trading.bots.base.strategy import BaseStrategy
from stonks_trading.domains.trading.entities import Signal
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Symbol

# Exact constants from NEAT/main.py
DECISION_THRESHOLD = 0.6
TRANSACTION_FEE = 0.001
MIN_TRADE_INTERVAL = 15


class NeatSwingStrategy(BaseStrategy):
    """NEAT swing trading strategy.

    Implements the exact strategy from NEAT/main.py TradingEnv.step().

    State vector (7 elements):
        [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]

    The first two elements are position-dependent:
        - is_invested: 1.0 if holdings > 0 else -1.0
        - unrealized_pnl: (price - entry_price) / entry_price if invested else 0.0

    The remaining 5 elements are market features computed by compute_features().
    """

    def __init__(self, config_path: str = "config-neat.txt"):
        """Initialize NEAT strategy.

        Args:
            config_path: Path to NEAT config file.
        """
        self.config_path = config_path
        self.neat_config: Config | None = None
        self.genomes: dict[Symbol, DefaultGenome] = {}
        self.networks: dict[Symbol, RecurrentNetwork] = {}

    @property
    def name(self) -> str:
        return "neat_swing"

    @property
    def version(self) -> str:
        return "1.0.0"

    def compute_features(
        self,
        symbol: Symbol,
        candles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute 5 market features for NEAT state vector.

        Features 3-7 from NEAT/main.py TradingEnv.get_state():
        - trend_1h: (SMA50 - SMA200) / SMA200 on 1h data
        - rsi_1h: RSI(14) on 1h / 100
        - rsi_15m: RSI(14) on 15m / 100
        - roc: Rate of Change on 1m
        - bb_width: Bollinger Band width on 1m

        Args:
            symbol: Trading symbol.
            candles: List of 1m OHLCV candles.

        Returns:
            Dictionary with 5 market features.
        """
        if len(candles) < 200:
            return {
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }

        import pandas as pd
        import ta

        closes = pd.Series([c["close"] for c in candles])

        # Create sequential datetime index if not present (for resampling)
        start_time = pd.Timestamp("2024-01-01")
        closes.index = pd.date_range(start=start_time, periods=len(closes), freq="1min")

        # Resample to 1h for trend and RSI
        df_1h = closes.resample("1h").last().dropna()

        # Trend: (SMA50 - SMA200) / SMA200
        if len(df_1h) >= 200:
            sma50 = ta.trend.SMAIndicator(df_1h, 50).sma_indicator()
            sma200 = ta.trend.SMAIndicator(df_1h, 200).sma_indicator()
            trend_1h = (sma50 - sma200) / sma200
            trend_1h_value = trend_1h.iloc[-1] if not trend_1h.empty else 0.0
        else:
            trend_1h_value = 0.0

        # RSI 1h
        if len(df_1h) >= 14:
            rsi_1h = ta.momentum.RSIIndicator(df_1h, 14).rsi() / 100.0
            rsi_1h_value = rsi_1h.iloc[-1] if not rsi_1h.empty else 0.5
        else:
            rsi_1h_value = 0.5

        # RSI 15m
        df_15m = closes.resample("15min").last().dropna()
        if len(df_15m) >= 14:
            rsi_15m = ta.momentum.RSIIndicator(df_15m, 14).rsi() / 100.0
            rsi_15m_value = rsi_15m.iloc[-1] if not rsi_15m.empty else 0.5
        else:
            rsi_15m_value = 0.5

        # ROC on 1m
        if len(closes) >= 11:
            roc = ta.momentum.ROCIndicator(closes, 10).roc()
            roc_value = roc.iloc[-1] if not roc.empty else 0.0
        else:
            roc_value = 0.0

        # BB width on 1m
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

    def generate_signal(
        self,
        symbol: Symbol,
        candle: dict[str, Any],
        features: dict[str, Any],
        current_position: Any | None,
    ) -> Signal | None:
        """Generate trading signal from NEAT output.

        Args:
            symbol: Trading symbol.
            candle: Current 1m candle.
            features: Market features from compute_features().
            current_position: Current position for this symbol (if any).

        Returns:
            Signal if action should be taken, None otherwise.
        """
        # This method is not used in the live bot - we use the network directly
        # Keeping for interface compliance
        return None

    def build_state_vector(
        self,
        price: float,
        current_position: Any | None,
        features: dict[str, Any],
    ) -> list[float]:
        """Build 7-element state vector matching NEAT/main.py exactly.

        From NEAT/main.py TradingEnv.get_state() lines 117-136:
        1. is_invested: 1.0 if holdings > 0 else -1.0
        2. unrealized_pnl: (price - entry_price) / entry_price if invested else 0.0
        3. trend_1h: (sma50_1h - sma200_1h) / sma200_1h
        4. rsi_1h: RSI(14) on 1h / 100.0
        5. rsi_15m: RSI(14) on 15m / 100.0
        6. roc: Rate of Change (momentum)
        7. bb_width: Bollinger Band width

        Args:
            price: Current price.
            current_position: Current position (if any).
            features: Market features dict from compute_features().

        Returns:
            7-element state vector with values clipped to [-5, 5].
        """
        # 1. Is Invested
        is_invested = 1.0 if current_position and current_position.quantity > 0 else -1.0

        # 2. Unrealized PnL
        if current_position and current_position.quantity > 0 and current_position.entry_price:
            unrealized_pnl = (
                price - current_position.entry_price.amount
            ) / current_position.entry_price.amount
        else:
            unrealized_pnl = 0.0

        # Extract market features
        mkt = [
            features.get("trend_1h", 0.0),
            features.get("rsi_1h", 0.5),
            features.get("rsi_15m", 0.5),
            features.get("roc", 0.0),
            features.get("bb_width", 0.0),
        ]

        # Combine [Invested, Unr_PnL, 5 Market Indicators] = 7 Inputs
        state = np.hstack(([is_invested, unrealized_pnl], mkt))

        # Clean inputs - clip to [-5, 5] and handle NaN (exact from NEAT/main.py line 136)
        result: list[float] = np.nan_to_num(np.clip(state, -5.0, 5.0)).tolist()
        return result

    def load_genome(
        self,
        symbol: Symbol,
        genome: DefaultGenome,
        config: Config,
    ) -> None:
        """Load a genome and create RecurrentNetwork for a symbol.

        Args:
            symbol: Trading symbol.
            genome: NEAT genome to load.
            config: NEAT configuration.
        """
        self.genomes[symbol] = genome
        self.networks[symbol] = RecurrentNetwork.create(genome, config)

    def activate_network(
        self,
        symbol: Symbol,
        state_vector: list[float],
    ) -> tuple[float, float]:
        """Activate NEAT network for a symbol.

        Args:
            symbol: Trading symbol.
            state_vector: 7-element state vector.

        Returns:
            Tuple of (buy_prob, sell_prob) from network output.
        """
        if symbol not in self.networks:
            return (0.0, 0.0)

        network = self.networks[symbol]
        output = network.activate(state_vector)
        buy_prob = float(output[0])
        sell_prob = float(output[1])

        return (buy_prob, sell_prob)

    def determine_action(
        self,
        buy_prob: float,
        sell_prob: float,
        is_invested: bool,
    ) -> Side | None:
        """Determine trading action from NEAT output.

        EXACT logic from NEAT/main.py TradingEnv.step() lines 158-177.

        Args:
            buy_prob: Buy probability from network.
            sell_prob: Sell probability from network.
            is_invested: Whether currently in a position.

        Returns:
            Side.BUY, Side.SELL, or None (no action).
        """
        # Buy Signal (NEAT/main.py line 158)
        if buy_prob > DECISION_THRESHOLD and buy_prob > sell_prob:
            if not is_invested:
                return Side.BUY

        # Sell Signal (NEAT/main.py line 169)
        elif sell_prob > DECISION_THRESHOLD and sell_prob > buy_prob and is_invested:
            return Side.SELL

        return None
