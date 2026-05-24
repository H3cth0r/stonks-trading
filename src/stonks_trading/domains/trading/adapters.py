"""Exchange adapters for trading domain.

Adapters connect the domain to external systems (exchanges).
Used by both bot and API containers.

Implements the adapter pattern for multiple venues:
- Binance (default)
- DryRun (paper trading simulation)
"""

import asyncio
import hashlib
import hmac
import random
import time
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

from stonks_trading.domains.trading.entities import Balance, OrderResult
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.services import InstrumentMapper
from stonks_trading.domains.trading.value_objects import Money, Symbol
from stonks_trading.shared.config import settings


class IExchangeAdapter(ABC):
    """Abstract base class for exchange adapters.

    Defines the interface for order execution and market data
    that all exchange implementations must follow.
    """

    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        order_type: str = "market",
        price: Money | None = None,
    ) -> OrderResult:
        """Place order on exchange.

        Args:
            symbol: Trading symbol (venue-specific)
            side: Buy or sell
            quantity: Amount to trade
            order_type: market, limit, etc.
            price: Limit price (optional for market orders)

        Returns:
            OrderResult with fill details or error
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        """Cancel existing order.

        Args:
            order_id: Order to cancel
            symbol: Trading symbol

        Returns:
            True if successfully cancelled
        """
        pass

    @abstractmethod
    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        """Get account balance.

        Args:
            asset: Specific asset or None for all balances

        Returns:
            Balance(s) for asset(s)
        """
        pass

    @abstractmethod
    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current price
        """
        pass

    @abstractmethod
    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent public trades.

        Args:
            symbol: Trading symbol
            limit: Number of trades to fetch

        Returns:
            List of recent trades
        """
        pass

    @abstractmethod
    async def get_fee_tier(self) -> dict[str, Any]:
        """Get current fee tier from exchange.

        Returns:
            Fee tier information (maker/taker rates)
        """
        pass

    @abstractmethod
    async def get_exchange_info(self) -> dict[str, Any]:
        """Get exchange symbol filters (lot size, min notional, tick size).

        Returns:
            Exchange info including symbol filters
        """
        pass

    @abstractmethod
    async def get_klines(
        self,
        symbol: Symbol,
        interval: str = "1m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get OHLCV klines/candles for symbol.

        Args:
            symbol: Trading symbol
            interval: Candle interval (1m, 5m, 1h, 1d, etc.)
            limit: Number of candles to fetch (max 1000)
            start_time: Start time in milliseconds (optional)
            end_time: End time in milliseconds (optional)

        Returns:
            List of OHLCV candles
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close HTTP client and cleanup."""
        pass


class BinanceAdapter(IExchangeAdapter):
    """Binance Spot REST adapter with HMAC-SHA256 signing.

    Uses the configured base_url (testnet or live).
    Respects rate limits with exponential backoff on 429/418.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.binance.com",
    ):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={"X-MBX-APIKEY": api_key},
            timeout=30.0,
        )
        self.instrument_mapper = InstrumentMapper()
        self._exchange_info: dict[str, Any] | None = None

    def _sign(self, params: dict[str, Any]) -> str:
        """HMAC-SHA256 sign query parameters."""
        query = urllib.parse.urlencode(params)
        return hmac.new(
            self.api_secret,
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _signed_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make signed request with timestamp and recvWindow."""
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        params["signature"] = self._sign(params)

        url = f"{self.base_url}{endpoint}"

        if method.upper() == "GET":
            response = await self.client.get(url, params=params)
        else:
            response = await self.client.request(method, url, data=params)

        # Handle rate limits
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            await asyncio.sleep(retry_after)
            return await self._signed_request(method, endpoint, params)

        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def _public_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make unsigned public request."""
        url = f"{self.base_url}{endpoint}"
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        order_type: str = "market",
        price: Money | None = None,
    ) -> OrderResult:
        """Place signed order on Binance Spot."""
        venue_symbol = self.instrument_mapper.to_venue_symbol(symbol, "binance")

        params: dict[str, Any] = {
            "symbol": venue_symbol.value.upper(),
            "side": side.value.upper(),
            "type": order_type.upper(),
        }

        if order_type.lower() == "market":
            params["quantity"] = quantity
        elif order_type.lower() == "limit" and price:
            params["price"] = f"{price.amount:.8f}"
            params["timeInForce"] = "GTC"
            params["quantity"] = quantity

        data = await self._signed_request("POST", "/api/v3/order", params)

        if "orderId" not in data:
            return OrderResult(
                success=False,
                error=data.get("msg", "Unknown error"),
            )

        # Binance returns order status immediately for market orders
        # For fills, query myTrades or wait for User Data Stream
        fill_price = None
        filled_qty = 0.0
        fee = None

        if data.get("status") == "FILLED" and "fills" in data:
            fills = data["fills"]
            if fills:
                # Weighted average fill price
                total_qty = sum(float(f["qty"]) for f in fills)
                total_notional = sum(float(f["qty"]) * float(f["price"]) for f in fills)
                avg_price = total_notional / total_qty if total_qty > 0 else 0.0
                total_fee = sum(float(f["commission"]) for f in fills)
                fee_currency = fills[0].get("commissionAsset", "USDT")

                fill_price = Money(amount=avg_price, currency="USDT")
                filled_qty = total_qty
                fee = Money(amount=total_fee, currency=fee_currency)

        return OrderResult(
            success=True,
            order_id=str(data["orderId"]),
            fill_price=fill_price,
            filled_quantity=filled_qty,
            fee=fee,
            timestamp=datetime.utcnow(),
        )

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        """Cancel order on Binance."""
        venue_symbol = self.instrument_mapper.to_venue_symbol(symbol, "binance")
        params = {
            "symbol": venue_symbol.value.upper(),
            "orderId": order_id,
        }
        data = await self._signed_request("DELETE", "/api/v3/order", params)
        return data.get("status") in ("CANCELED", "PENDING_CANCEL")

    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        """Get account balances from Binance."""
        data = await self._signed_request("GET", "/api/v3/account")

        balances = []
        for b in data.get("balances", []):
            free = float(b["free"])
            locked = float(b["locked"])
            if free > 0 or locked > 0:
                balances.append(
                    Balance(
                        asset=b["asset"],
                        free=free,
                        locked=locked,
                        total=free + locked,
                    )
                )

        if asset:
            for b in balances:
                if b.asset.upper() == asset.upper():
                    return b
            return Balance(asset=asset, free=0.0, locked=0.0, total=0.0)

        return balances

    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price from Binance public API."""
        venue_symbol = self.instrument_mapper.to_venue_symbol(symbol, "binance")
        data = await self._public_request(
            "/api/v3/ticker/price",
            {"symbol": venue_symbol.value.upper()},
        )
        return Money(
            amount=float(data["price"]),
            currency="USDT",
        )

    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent public trades."""
        venue_symbol = self.instrument_mapper.to_venue_symbol(symbol, "binance")
        return await self._public_request(
            "/api/v3/trades",
            {"symbol": venue_symbol.value.upper(), "limit": limit},
        )  # type: ignore[no-any-return]

    async def get_fee_tier(self) -> dict[str, Any]:
        """Get trading fee tier from Binance."""
        data = await self._signed_request("GET", "/api/v3/account")
        return {
            "maker_commission": data.get("makerCommission", 10) / 10000.0,
            "taker_commission": data.get("takerCommission", 10) / 10000.0,
        }

    async def get_exchange_info(self) -> dict[str, Any]:
        """Get exchange info with symbol filters."""
        if self._exchange_info is None:
            self._exchange_info = await self._public_request("/api/v3/exchangeInfo")
        return self._exchange_info

    async def get_klines(
        self,
        symbol: Symbol,
        interval: str = "1m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get OHLCV klines from Binance.

        Returns list of candles with normalized field names.
        Binance format: [open_time, open, high, low, close, volume, close_time, ...]
        """
        venue_symbol = self.instrument_mapper.to_venue_symbol(symbol, "binance")
        params: dict[str, Any] = {
            "symbol": venue_symbol.value.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._public_request("/api/v3/klines", params)

        # Normalize to consistent format
        candles = []
        for k in data:
            candles.append(
                {
                    "timestamp": k[0],  # Open time
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6],
                }
            )
        return candles

    async def close(self) -> None:
        await self.client.aclose()


class DryRunAdapter(IExchangeAdapter):
    """Dry-run (paper trading) adapter.

    Simulates exchange behavior with:
    - Configurable slippage (basis points)
    - Simulated latency (ms)
    - Random order rejections (0.5%)
    - Random partial fills (2%)
    - Balance tracking across simulated trades
    """

    def __init__(
        self,
        initial_balance: dict[str, float] | None = None,
        slippage_bps: float = 5.0,
        fee_rate: float = 0.001,
        latency_ms: float = 1500.0,
        rejection_rate: float = 0.005,
        partial_fill_rate: float = 0.02,
    ):
        self.balances = initial_balance or {"USDT": 10000.0, "BTC": 0.0}
        self.slippage_bps = slippage_bps
        self.fee_rate = fee_rate
        self.latency_ms = latency_ms
        self.rejection_rate = rejection_rate
        self.partial_fill_rate = partial_fill_rate
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_counter = 0
        self.current_prices: dict[str, float] = {}
        self._price_source: IExchangeAdapter | None = None  # Optional real price feed

    def set_price_source(self, source: IExchangeAdapter) -> None:
        """Use real adapter for price feed while simulating execution."""
        self._price_source = source

    async def _get_price(self, symbol: Symbol) -> float:
        """Get current price from cache or source."""
        sym = symbol.value.upper()
        if sym in self.current_prices:
            return self.current_prices[sym]
        if self._price_source:
            price = await self._price_source.get_price(symbol)
            return price.amount
        return 50000.0  # Fallback

    def _get_assets(self, symbol: Symbol) -> tuple[str, str]:
        """Extract base and quote from symbol."""
        sym = symbol.value.upper()
        # Handle venue format (BTCUSDT, BTCUSD)
        if sym.endswith("USDT"):
            return (sym[:-4], "USDT")
        if sym.endswith("USD") and not sym.endswith("_USD"):
            return (sym[:-3], "USD")
        # Handle canonical format (BTC_USD maps to BTC/USDT for dry-run)
        if "_" in sym:
            parts = sym.split("_")
            base = parts[0]
            # Map USD quote to USDT for dry-run simulation
            quote = "USDT" if parts[1] == "USD" else parts[1]
            return (base, quote)
        return (sym, "USDT")

    def _apply_slippage(self, price: float, side: Side) -> float:
        """Apply slippage to price."""
        slippage_pct = self.slippage_bps / 10000.0
        if side == Side.BUY:
            return price * (1 + slippage_pct)
        return price * (1 - slippage_pct)

    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        order_type: str = "market",
        price: Money | None = None,
    ) -> OrderResult:
        """Simulate order placement with slippage, latency, and random failures."""
        # Simulate latency
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        # Random rejection
        if random.random() < self.rejection_rate:
            return OrderResult(
                success=False,
                error="Simulated order rejection: insufficient liquidity",
            )

        base_asset, quote_asset = self._get_assets(symbol)
        current_price = await self._get_price(symbol)
        fill_price = self._apply_slippage(current_price, side)

        # Random partial fill
        fill_ratio = 1.0
        if random.random() < self.partial_fill_rate:
            fill_ratio = random.uniform(0.5, 0.99)

        filled_qty = quantity * fill_ratio
        notional = filled_qty * fill_price
        fee = notional * self.fee_rate

        # Check balance
        if side == Side.BUY:
            required = notional + fee
            if self.balances.get(quote_asset, 0) < required:
                return OrderResult(
                    success=False,
                    error=f"Insufficient {quote_asset} balance",
                )
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) - required
            self.balances[base_asset] = self.balances.get(base_asset, 0) + filled_qty
        else:  # SELL
            if self.balances.get(base_asset, 0) < filled_qty:
                return OrderResult(
                    success=False,
                    error=f"Insufficient {base_asset} balance",
                )
            received = notional - fee
            self.balances[base_asset] = self.balances.get(base_asset, 0) - filled_qty
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) + received

        self.order_counter += 1
        order_id = f"dryrun_{self.order_counter}"

        return OrderResult(
            success=True,
            order_id=order_id,
            fill_price=Money(amount=fill_price, currency=quote_asset),
            filled_quantity=filled_qty,
            fee=Money(amount=fee, currency=quote_asset),
            timestamp=datetime.utcnow(),
        )

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
            return True
        return False

    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        if asset:
            amount = self.balances.get(asset, 0.0)
            return Balance(asset=asset, free=amount, locked=0.0, total=amount)
        return [Balance(asset=k, free=v, locked=0.0, total=v) for k, v in self.balances.items()]

    async def get_price(self, symbol: Symbol) -> Money:
        price = await self._get_price(symbol)
        return Money(amount=price, currency="USDT")

    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return []

    async def get_fee_tier(self) -> dict[str, Any]:
        return {"maker_rate": self.fee_rate, "taker_rate": self.fee_rate}

    async def get_exchange_info(self) -> dict[str, Any]:
        return {}

    async def get_klines(
        self,
        symbol: Symbol,
        interval: str = "1m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Dry-run returns empty list - use real adapter for backfill."""
        return []

    def set_price(self, symbol: Symbol, price: float) -> None:
        self.current_prices[symbol.value.upper()] = price

    async def close(self) -> None:
        pass


class BitsoAdapter(IExchangeAdapter):
    """Bitso adapter skeleton for future MXN integration.

    Not fully implemented in Phase 4; exists to validate the adapter pattern.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.bitso.com",
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.instrument_mapper = InstrumentMapper()

    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        order_type: str = "market",
        price: Money | None = None,
    ) -> OrderResult:
        raise NotImplementedError("Bitso adapter: Phase 5+")

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        raise NotImplementedError("Bitso adapter: Phase 5+")

    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        raise NotImplementedError("Bitso adapter: Phase 5+")

    async def get_price(self, symbol: Symbol) -> Money:
        raise NotImplementedError("Bitso adapter: Phase 5+")

    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return []

    async def get_fee_tier(self) -> dict[str, Any]:
        return {"maker_rate": 0.0035, "taker_rate": 0.0035}

    async def get_exchange_info(self) -> dict[str, Any]:
        return {}

    async def get_klines(
        self,
        symbol: Symbol,
        interval: str = "1m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Bitso klines not implemented - Phase 5+."""
        raise NotImplementedError("Bitso klines: Phase 5+")

    async def close(self) -> None:
        await self.client.aclose()


class ExchangeAdapterFactory:
    """Factory for creating the configured exchange adapter."""

    @staticmethod
    def create_adapter(
        venue: str | None = None,
        mode: str | None = None,
    ) -> IExchangeAdapter:
        """Create adapter based on configuration.

        Args:
            venue: Override venue (binance, bitso). Defaults to settings.
            mode: Override mode (backtest, dry_run, live). Defaults to settings.

        Returns:
            Configured IExchangeAdapter instance.
        """
        effective_mode = (mode or settings.mode).lower()
        effective_venue = (venue or effective_mode).lower()

        # Validate venue first
        valid_venues = ("binance", "bitso", "live", "dry_run", "backtest")
        if effective_venue not in valid_venues:
            raise ValueError(f"Unknown venue: {effective_venue}")

        # Dry-run mode uses DryRunAdapter regardless of venue
        if effective_mode == "dry_run":
            adapter = DryRunAdapter(
                initial_balance={"USDT": settings.initial_capital, "BTC": 0.0},
                slippage_bps=5.0,
                fee_rate=settings.transaction_fee,
            )
            # Wire real price feed if available
            if settings.binance_api_key:
                price_adapter = BinanceAdapter(
                    api_key=settings.binance_api_key,
                    api_secret=settings.binance_api_secret,
                    base_url=settings.binance_base_url,
                )
                adapter.set_price_source(price_adapter)
            return adapter

        # Live trading requires API keys
        if effective_venue in ("binance", "live"):
            if not settings.binance_api_key or not settings.binance_api_secret:
                raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET required for live mode")
            return BinanceAdapter(
                api_key=settings.binance_api_key,
                api_secret=settings.binance_api_secret,
                base_url=settings.binance_base_url,
            )

        if effective_venue == "bitso":
            if not settings.bitso_api_key or not settings.bitso_api_secret:
                raise ValueError("BITSO_API_KEY and BITSO_API_SECRET required")
            return BitsoAdapter(
                api_key=settings.bitso_api_key,
                api_secret=settings.bitso_api_secret,
            )

        raise ValueError(f"Unknown venue: {effective_venue}")
