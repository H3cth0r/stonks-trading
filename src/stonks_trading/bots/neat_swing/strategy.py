"""NEAT Swing Strategy with exact parity to NEAT/main.py.

This strategy implements the exact trading logic from NEAT/main.py:
- DECISION_THRESHOLD = 0.6
- TRANSACTION_FEE = 0.001
- MIN_TRADE_INTERVAL = 15
- 7-element state vector: [is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]
- Uses RecurrentNetwork (not feedforward)
- All-in / all-out trading logic
"""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from neat import Config, DefaultGenome
from neat.nn import RecurrentNetwork

from stonks_trading.bots.base.strategy import BaseStrategy
from stonks_trading.domains.strategies.neat_swing.features import engineer_features
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
        self._last_candle_timestamps: dict[Symbol, datetime] = {}

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
        """Compute NEAT market features from candle history.

        Uses the SAME feature engineering as NEAT/main.py and the training
        pipeline (domains/strategies/neat_swing/features.py) to guarantee
        parity between training and live inference.

        Args:
            symbol: Trading symbol.
            candles: Historical candles (most recent last). Expected keys
                include timestamp/Datetime, open/Open, high/High, low/Low,
                close/Close, and volume/Volume.

        Returns:
            Dictionary of features: trend_1h, rsi_1h, rsi_15m, roc, bb_width.
        """
        if len(candles) < 200:
            return {
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }

        # Build DataFrame from candles using real timestamps.
        rows: list[dict[str, Any]] = []
        timestamps: list[datetime] = []
        for candle in candles:
            ts = candle.get("timestamp") or candle.get("Datetime")
            if ts is None:
                continue
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)
            rows.append(
                {
                    "Open": candle.get("open", candle.get("Open", 0.0)),
                    "High": candle.get("high", candle.get("High", 0.0)),
                    "Low": candle.get("low", candle.get("Low", 0.0)),
                    "Close": candle.get("close", candle.get("Close", 0.0)),
                    "Volume": candle.get("volume", candle.get("Volume", 0.0)),
                }
            )
            timestamps.append(ts)

        if len(rows) < 200:
            return {
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }

        df = pd.DataFrame(rows)
        df.index = pd.DatetimeIndex(timestamps)
        df = df.sort_index().dropna()

        features_df = engineer_features(df)
        if features_df.empty:
            return {
                "trend_1h": 0.0,
                "rsi_1h": 0.5,
                "rsi_15m": 0.5,
                "roc": 0.0,
                "bb_width": 0.0,
            }

        last = features_df.iloc[-1]
        return {
            "trend_1h": float(last["trend_1h"]),
            "rsi_1h": float(last["rsi_1h"]),
            "rsi_15m": float(last["rsi_15m"]),
            "roc": float(last["roc"]),
            "bb_width": float(last["bb_width"]),
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

    def update_last_candle_timestamp(self, symbol: Symbol, timestamp: datetime) -> None:
        """Update the last processed candle timestamp for a symbol.

        Args:
            symbol: Trading symbol.
            timestamp: Candle timestamp.
        """
        self._last_candle_timestamps[symbol] = timestamp

    def get_last_candle_timestamp(self, symbol: Symbol) -> datetime | None:
        """Get the last processed candle timestamp for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Last candle timestamp or None if not set.
        """
        return self._last_candle_timestamps.get(symbol)
