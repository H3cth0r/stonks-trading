"""Exchange adapters for trading domain.

Adapters connect the domain to external systems (exchanges).
Used by both bot and API containers.

Implements the adapter pattern for multiple venues:
- Binance (default)
- DryRun (paper trading simulation)
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

from stonks_trading.domains.trading.entities import Balance, OrderResult
from stonks_trading.domains.trading.enums import Side
from stonks_trading.domains.trading.value_objects import Money, Symbol


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


class BinanceAdapter(IExchangeAdapter):
    """Binance exchange adapter.

    Implements REST API integration for Binance Spot trading.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.binance.com",
    ):
        """Initialize Binance adapter.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            base_url: Binance API base URL
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={"X-MBX-APIKEY": api_key},
            timeout=30.0,
        )

    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        order_type: str = "market",
        price: Money | None = None,
    ) -> OrderResult:
        """Place order on Binance."""
        params: dict[str, Any] = {
            "symbol": symbol.value.upper(),
            "side": side.value.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }

        if order_type.lower() == "limit" and price:
            params["price"] = price.amount
            params["timeInForce"] = "GTC"

        try:
            # In production, would sign request and make actual API call
            # response = await self._signed_request("POST", endpoint, params)

            # Stub for Phase 1
            return OrderResult(
                success=True,
                order_id=f"binance_stub_{datetime.utcnow().timestamp()}",
                fill_price=price or Money(amount=50000.0, currency="USD"),
                filled_quantity=quantity,
                fee=Money(
                    amount=quantity * (price.amount if price else 50000.0) * 0.001, currency="USD"
                ),
                timestamp=datetime.utcnow(),
            )
        except Exception as e:
            return OrderResult(
                success=False,
                error=str(e),
            )

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        """Cancel order on Binance."""
        # Stub implementation
        return True

    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        """Get Binance account balance."""
        # Stub implementation
        if asset:
            return Balance(asset=asset, free=1.0, locked=0.0, total=1.0)
        return [
            Balance(asset="BTC", free=1.0, locked=0.0, total=1.0),
            Balance(asset="USDT", free=50000.0, locked=0.0, total=50000.0),
        ]

    async def get_price(self, symbol: Symbol) -> Money:
        """Get current price from Binance."""
        try:
            # response = await self.client.get(endpoint, params={"symbol": symbol.value.upper()})
            # data = response.json()
            # return Money(amount=float(data["price"]), currency="USD")

            # Stub for Phase 1
            return Money(amount=50000.0, currency="USD")
        except Exception:
            return Money(amount=0.0, currency="USD")

    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent trades from Binance."""
        # Stub implementation
        return []

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


class DryRunAdapter(IExchangeAdapter):
    """Dry-run (paper trading) adapter.

    Simulates exchange behavior for testing without real capital.
    Uses NEAT trading environment logic for simulation.
    """

    def __init__(
        self,
        initial_balance: dict[str, float] | None = None,
        slippage_bps: float = 5.0,
        fee_rate: float = 0.001,
    ):
        """Initialize dry-run adapter.

        Args:
            initial_balance: Starting balances by asset
            slippage_bps: Slippage in basis points
            fee_rate: Transaction fee rate
        """
        self.balances = initial_balance or {"USDT": 10000.0, "BTC": 0.0}
        self.slippage_bps = slippage_bps
        self.fee_rate = fee_rate
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_counter = 0
        self.current_prices: dict[str, float] = {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0,
        }

    def _get_asset_from_symbol(self, symbol: Symbol) -> tuple[str, str]:
        """Extract base and quote assets from symbol."""
        # Simplified for common pairs
        sym = symbol.value.upper()
        if sym.endswith("USDT"):
            return (sym.replace("USDT", ""), "USDT")
        if sym.endswith("USD"):
            return (sym.replace("USD", ""), "USD")
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
        """Simulate order placement."""
        base_asset, quote_asset = self._get_asset_from_symbol(symbol)

        # Get current price
        current_price = self.current_prices.get(
            symbol.value.upper(),
            50000.0,
        )

        # Apply slippage
        fill_price = self._apply_slippage(current_price, side)

        # Calculate notional and fee
        notional = quantity * fill_price
        fee = notional * self.fee_rate

        # Check balance
        if side == Side.BUY:
            required = notional + fee
            if self.balances.get(quote_asset, 0) < required:
                return OrderResult(
                    success=False,
                    error=f"Insufficient {quote_asset} balance",
                )
            # Update balances
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) - required
            self.balances[base_asset] = self.balances.get(base_asset, 0) + quantity
        else:  # SELL
            if self.balances.get(base_asset, 0) < quantity:
                return OrderResult(
                    success=False,
                    error=f"Insufficient {base_asset} balance",
                )
            # Update balances
            received = notional - fee
            self.balances[base_asset] = self.balances.get(base_asset, 0) - quantity
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) + received

        self.order_counter += 1
        order_id = f"dryrun_{self.order_counter}"

        return OrderResult(
            success=True,
            order_id=order_id,
            fill_price=Money(amount=fill_price, currency=quote_asset),
            filled_quantity=quantity,
            fee=Money(amount=fee, currency=quote_asset),
            timestamp=datetime.utcnow(),
        )

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        """Cancel simulated order."""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
            return True
        return False

    async def get_balance(self, asset: str | None = None) -> Balance | list[Balance]:
        """Get simulated balance."""
        if asset:
            amount = self.balances.get(asset, 0.0)
            return Balance(asset=asset, free=amount, locked=0.0, total=amount)

        return [Balance(asset=k, free=v, locked=0.0, total=v) for k, v in self.balances.items()]

    async def get_price(self, symbol: Symbol) -> Money:
        """Get simulated current price."""
        price = self.current_prices.get(symbol.value.upper(), 50000.0)
        return Money(amount=price, currency="USDT")

    async def get_recent_trades(
        self,
        symbol: Symbol,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get simulated recent trades."""
        return []

    def set_price(self, symbol: Symbol, price: float) -> None:
        """Set simulated price (for testing)."""
        self.current_prices[symbol.value.upper()] = price


class DiscordNotifier:
    """Discord webhook notifier for alerts and reports.

    Used for sending notifications on risk events and trade execution.
    """

    def __init__(self, webhook_url: str):
        """Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send_message(
        self,
        content: str,
        embeds: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send message to Discord webhook.

        Args:
            content: Message content
            embeds: Optional rich embeds

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            return False

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            # response = await self.client.post(self.webhook_url, json=payload)
            # return response.status_code == 204
            return True  # Stub for Phase 1
        except Exception:
            return False

    async def send_risk_alert(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Send risk alert to Discord."""
        color = 0xFF0000 if severity == "critical" else 0xFFA500

        embed = {
            "title": f"Risk Alert: {event_type}",
            "description": message,
            "color": color,
            "fields": [
                {"name": k, "value": str(v), "inline": True} for k, v in (details or {}).items()
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return await self.send_message(
            f"@here Risk Alert ({severity.upper()})",
            embeds=[embed],
        )

    async def send_trade_notification(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: Money,
        pnl: Money | None = None,
    ) -> bool:
        """Send trade execution notification."""
        color = 0x00FF00 if side == Side.BUY else 0xFF0000

        embed = {
            "title": f"Trade Executed: {symbol.value}",
            "color": color,
            "fields": [
                {"name": "Side", "value": side.value.upper(), "inline": True},
                {"name": "Quantity", "value": str(quantity), "inline": True},
                {"name": "Price", "value": str(price), "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        if pnl:
            embed["fields"].append({"name": "P&L", "value": str(pnl), "inline": True})

        return await self.send_message(
            f"Trade: {side.value.upper()} {symbol.value}",
            embeds=[embed],
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
