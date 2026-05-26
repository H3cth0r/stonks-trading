"""Value objects for trading domain.

Value objects are immutable, frozen Pydantic models that represent
domain concepts with validation and equality based on their values.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from stonks_trading.domains.trading.enums import Side


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
        """Convert canonical symbol to venue-specific symbol."""
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
        """Convert venue symbol to canonical symbol."""
        venue = venue.lower()
        venue_str = venue_symbol.value.upper()

        # Reverse lookup
        if venue in self.mappings:
            for canonical, venue_sym in self.mappings[venue].items():
                if venue_sym.upper() == venue_str:
                    return Symbol(value=canonical)

        # If no mapping found, convert to canonical format
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


class Symbol(BaseModel):
    """Trading symbol value object.

    Represents a canonical symbol that can be mapped to
    venue-specific symbols via InstrumentMapper.

    Examples:
        - BTC_USD (canonical)
        - BTCUSDT (Binance)
        - BTC_MXN (Bitso)
    """

    value: str = Field(..., min_length=1, max_length=20)

    model_config = {"frozen": True}

    @field_validator("value")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase."""
        return v.upper()

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)


class Money(BaseModel):
    """Money value object with amount and currency.

    Immutable representation of a monetary amount with
    validation for precision and currency code.
    """

    amount: float = Field(..., description="Monetary amount")
    currency: str = Field(default="USD", min_length=3, max_length=10)  # Support USDT, USDC, etc.

    model_config = {"frozen": True}

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        """Normalize currency to uppercase."""
        return v.upper()

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    def to_float(self) -> float:
        """Return raw float amount (for serialization)."""
        return self.amount

    def __add__(self, other: Money) -> Money:
        """Add two Money objects of same currency."""
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        """Subtract two Money objects of same currency."""
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {other.currency} from {self.currency}")
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, scalar: float) -> Money:
        """Multiply Money by scalar."""
        return Money(amount=self.amount * scalar, currency=self.currency)

    def __rmul__(self, scalar: float) -> Money:
        """Scalar multiplication (reverse)."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Money:
        """Divide Money by scalar."""
        if scalar == 0:
            raise ValueError("Cannot divide by zero")
        return Money(amount=self.amount / scalar, currency=self.currency)


class FeeTier(BaseModel):
    """Exchange fee tier configuration.

    Represents maker/taker fee rates for a specific tier.
    """

    maker_rate: float = Field(..., ge=0, le=0.01)
    taker_rate: float = Field(..., ge=0, le=0.01)
    tier_name: str = Field(default="default")

    model_config = {"frozen": True}

    def calculate_fee(
        self,
        notional: Money,
        is_maker: bool = False,
    ) -> Money:
        """Calculate fee for a given notional amount."""
        rate = self.maker_rate if is_maker else self.taker_rate
        return Money(
            amount=notional.amount * rate,
            currency=notional.currency,
        )


class Decision(BaseModel):
    """NEAT network output decision.

    Represents the raw output from the neural network
    before threshold application.
    """

    buy_prob: float = Field(..., ge=0.0, le=1.0)
    sell_prob: float = Field(..., ge=0.0, le=1.0)

    model_config = {"frozen": True}

    def get_action(self, threshold: float = 0.6) -> Side | None:
        """Get trading action if threshold is exceeded."""
        from stonks_trading.domains.trading.enums import Side

        if self.buy_prob > threshold and self.buy_prob > self.sell_prob:
            return Side.BUY
        if self.sell_prob > threshold and self.sell_prob > self.buy_prob:
            return Side.SELL
        return None

    def is_confident(self, threshold: float = 0.6) -> bool:
        """Check if either probability exceeds threshold."""
        return self.buy_prob > threshold or self.sell_prob > threshold


class BotContext(BaseModel):
    """Bot context value object for multi-bot isolation.

    Immutable identifier for bot instances that separates
    data and operations between different bots.
    """

    bot_type: str = Field(..., min_length=1, max_length=50)
    instance_id: str = Field(..., min_length=1, max_length=100)

    model_config = {"frozen": True}

    def __str__(self) -> str:
        return f"{self.bot_type}/{self.instance_id}"

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for serialization."""
        return {"bot_type": self.bot_type, "bot_instance_id": self.instance_id}
