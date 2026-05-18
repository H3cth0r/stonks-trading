"""Domain services for trading domain.

Services contain pure business logic with no I/O.
They operate on entities and value objects.
"""

from stonks_trading.domains.trading.entities import Position, RiskCheckResult
from stonks_trading.domains.trading.enums import RiskLevel, Side
from stonks_trading.domains.trading.value_objects import (
    FeeTier,
    Money,
    Symbol,
)


class RiskChecker:
    """Risk management service.

    Validates trades against risk limits before execution.
    Pure logic - no I/O or external dependencies.
    """

    def __init__(
        self,
        max_position_pct: float = 0.95,
        max_drawdown_pct: float = 0.15,
        max_trades_per_day: int = 40,
        min_trade_interval_minutes: int = 15,
    ):
        """Initialize risk checker with limits.

        Args:
            max_position_pct: Max portfolio allocation to single position
            max_drawdown_pct: Kill switch drawdown threshold
            max_trades_per_day: Maximum trades allowed per day
            min_trade_interval_minutes: Minimum minutes between trades
        """
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_trades_per_day = max_trades_per_day
        self.min_trade_interval_minutes = min_trade_interval_minutes

    def check_trade(
        self,
        side: Side,
        notional: Money,
        portfolio_value: Money,
        current_position: Position | None,
        daily_trade_count: int,
        minutes_since_last_trade: int,
        current_drawdown: float = 0.0,
    ) -> RiskCheckResult:
        """Check if trade is allowed under risk limits.

        Args:
            side: Buy or sell
            notional: Trade size in base currency
            portfolio_value: Total portfolio value
            current_position: Current position if any
            daily_trade_count: Number of trades today
            minutes_since_last_trade: Minutes since last trade
            current_drawdown: Current drawdown percentage

        Returns:
            RiskCheckResult with allowed flag and reason
        """
        # Check kill switch - max drawdown
        if current_drawdown > self.max_drawdown_pct:
            return RiskCheckResult(
                allowed=False,
                reason=f"Kill switch: drawdown {current_drawdown:.2%} exceeds limit",
                risk_level=RiskLevel.CRITICAL,
            )

        # Check daily trade limit (churning prevention)
        if daily_trade_count >= self.max_trades_per_day:
            return RiskCheckResult(
                allowed=False,
                reason=f"Daily trade limit reached ({daily_trade_count} trades)",
                risk_level=RiskLevel.WARNING,
            )

        # Check minimum trade interval
        if minutes_since_last_trade < self.min_trade_interval_minutes:
            return RiskCheckResult(
                allowed=False,
                reason=f"Trade interval too short ({minutes_since_last_trade} min)",
                risk_level=RiskLevel.WARNING,
            )

        # Check position size for buys
        if side == Side.BUY:
            if current_position and current_position.is_open():
                # Check if adding to existing position
                position_value = current_position.calculate_market_value(
                    Money(amount=notional.amount, currency=notional.currency)
                )
                new_exposure = (position_value.amount + notional.amount) / portfolio_value.amount
            else:
                new_exposure = notional.amount / portfolio_value.amount

            if new_exposure > self.max_position_pct:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Position size {new_exposure:.2%} exceeds max {self.max_position_pct:.2%}",
                    risk_level=RiskLevel.WARNING,
                )

        return RiskCheckResult(allowed=True)

    def check_drawdown(
        self,
        current_equity: Money,
        peak_equity: Money,
    ) -> RiskCheckResult:
        """Check if drawdown exceeds limits.

        Returns critical risk level if kill switch should trigger.
        """
        if peak_equity.amount <= 0:
            return RiskCheckResult(allowed=True)

        drawdown = (peak_equity.amount - current_equity.amount) / peak_equity.amount

        if drawdown > self.max_drawdown_pct:
            return RiskCheckResult(
                allowed=False,
                reason=f"Max drawdown exceeded: {drawdown:.2%}",
                risk_level=RiskLevel.CRITICAL,
            )

        if drawdown > self.max_drawdown_pct * 0.8:
            return RiskCheckResult(
                allowed=True,
                reason=f"Warning: drawdown at {drawdown:.2%}",
                risk_level=RiskLevel.WARNING,
            )

        return RiskCheckResult(allowed=True)


class InstrumentMapper:
    """Maps canonical symbols to venue-specific symbols.

    Provides consistent symbol handling across different exchanges.
    """

    # Default mappings for supported venues
    DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
        "binance": {
            "BTC_USD": "BTCUSDT",
            "ETH_USD": "ETHUSDT",
            "XRP_USD": "XRPUSDT",
            "SOL_USD": "SOLUSDT",
            "ADA_USD": "ADAUSDT",
        },
        "bitso": {
            "BTC_USD": "btc_mxn",
            "ETH_USD": "eth_mxn",
            "XRP_USD": "xrp_mxn",
        },
        "kraken": {
            "BTC_USD": "XXBTZUSD",
            "ETH_USD": "XETHZUSD",
            "XRP_USD": "XXRPZUSD",
        },
    }

    def __init__(self, mappings: dict[str, dict[str, str]] | None = None):
        """Initialize with optional custom mappings.

        Args:
            mappings: Venue-specific symbol mappings
        """
        self.mappings = mappings or self.DEFAULT_MAPPINGS

    def to_venue_symbol(self, canonical: Symbol, venue: str) -> Symbol:
        """Convert canonical symbol to venue-specific symbol.

        Args:
            canonical: Canonical symbol (e.g., BTC_USD)
            venue: Target venue (binance, bitso, kraken)

        Returns:
            Venue-specific symbol
        """
        venue = venue.lower()
        canonical_str = canonical.value.upper()

        # Handle symbols that are already in venue format
        if venue == "binance" and canonical_str.endswith("USDT"):
            return canonical

        if venue in self.mappings:
            venue_sym = self.mappings[venue].get(canonical_str, canonical_str.lower())
            return Symbol(value=venue_sym)

        return canonical

    def to_canonical(self, venue_symbol: Symbol, venue: str) -> Symbol:
        """Convert venue symbol to canonical symbol.

        Args:
            venue_symbol: Venue-specific symbol
            venue: Source venue

        Returns:
            Canonical symbol
        """
        venue = venue.lower()
        venue_str = venue_symbol.value.upper()

        # Reverse lookup
        if venue in self.mappings:
            for canonical, venue_sym in self.mappings[venue].items():
                if venue_sym.upper() == venue_str:
                    return Symbol(value=canonical)

        # If no mapping found, convert to canonical format
        # e.g., BTCUSDT -> BTC_USD
        if venue == "binance" and venue_str.endswith("USDT"):
            base = venue_str[:-4]
            return Symbol(value=f"{base}_USD")

        return venue_symbol

    def get_supported_symbols(self, venue: str) -> list[Symbol]:
        """Get list of supported symbols for venue."""
        venue = venue.lower()
        if venue not in self.mappings:
            return []
        return [Symbol(value=k) for k in self.mappings[venue]]


class FeeCalculator:
    """Calculate fees for trades based on tier and venue."""

    # Default fee tiers (approximate, should be synced from exchange API)
    DEFAULT_TIERS: dict[str, FeeTier] = {
        "binance_default": FeeTier(maker_rate=0.001, taker_rate=0.001),
        "binance_vip1": FeeTier(maker_rate=0.0009, taker_rate=0.001),
        "bitso_default": FeeTier(maker_rate=0.0035, taker_rate=0.0035),
    }

    def __init__(
        self,
        tier_name: str = "binance_default",
        custom_tiers: dict[str, FeeTier] | None = None,
    ):
        """Initialize fee calculator.

        Args:
            tier_name: Fee tier to use
            custom_tiers: Optional custom fee tiers
        """
        tiers = {**self.DEFAULT_TIERS, **(custom_tiers or {})}
        self.tier = tiers.get(tier_name, self.DEFAULT_TIERS["binance_default"])

    def calculate_fee(
        self,
        notional: Money,
        is_maker: bool = False,
    ) -> Money:
        """Calculate fee for a trade.

        Args:
            notional: Trade notional value
            is_maker: Whether order is maker (limit) or taker (market)

        Returns:
            Fee amount
        """
        return self.tier.calculate_fee(notional, is_maker)

    def calculate_neat_equivalent(
        self,
        notional: Money,
        neat_fee_rate: float = 0.001,
    ) -> Money:
        """Calculate fee using NEAT's simplified fee model.

        Used for parity with NEAT training.
        """
        return Money(amount=notional.amount * neat_fee_rate, currency=notional.currency)
