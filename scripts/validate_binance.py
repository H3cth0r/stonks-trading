#!/usr/bin/env python3
"""Validate Binance testnet connectivity.

Run before Phase 4 integration tests to ensure API keys work.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stonks_trading.domains.trading.adapters import BinanceAdapter
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.config import settings


async def validate() -> int:
    print("=== Binance Testnet Validation ===")
    print(f"Base URL: {settings.binance_base_url}")

    if not settings.binance_api_key:
        print("ERROR: BINANCE_API_KEY not set")
        return 1

    adapter = BinanceAdapter(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        base_url=settings.binance_base_url,
    )

    try:
        # 1. Test connectivity
        print("\n1. Testing connectivity...")
        price = await adapter.get_price(Symbol(value="BTC_USD"))
        print(f"   BTCUSDT price: ${price.amount:,.2f}")

        # 2. Test balance
        print("\n2. Testing account balance...")
        balances = await adapter.get_balance()
        print(f"   Assets: {len(balances)}")
        for b in balances[:5]:
            print(f"   {b.asset}: free={b.free:.4f}, locked={b.locked:.4f}")

        # 3. Test fee tier
        print("\n3. Testing fee tier...")
        fees = await adapter.get_fee_tier()
        print(f"   Maker: {fees['maker_commission']:.4%}")
        print(f"   Taker: {fees['taker_commission']:.4%}")

        # 4. Test exchange info
        print("\n4. Testing exchange info...")
        info = await adapter.get_exchange_info()
        symbols = [s["symbol"] for s in info.get("symbols", []) if "BTC" in s["symbol"]]
        print(f"   BTC pairs available: {len(symbols)}")

        print("\n=== All validations passed ===")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        return 1
    finally:
        await adapter.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(validate()))
