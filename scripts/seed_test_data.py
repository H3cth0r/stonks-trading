#!/usr/bin/env python3
"""Seed test data for development and testing."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tortoise import Tortoise

from stonks_trading.shared.database import TORTOISE_ORM
from stonks_trading.shared.postgres_models import (
    BotDecisionModel,
    DataGapModel,
    GenerationMetricModel,
    GenomeModel,
    OrderModel,
    PositionModel,
    RiskEventModel,
    SystemConfigModel,
    TradeModel,
    TrainingRunModel,
    TradeSide,
    TradingMode,
)


async def seed() -> int:
    """Seed test data for development."""
    print("Seeding test data...")

    # Create test trades
    trades = [
        TradeModel(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            fill_price=50000.0,
            quantity=0.1,
            fee=5.0,
            fee_currency="USDT",
            fee_rate=0.001,
            slippage_bps=1.0,
            mode=TradingMode.DRY_RUN,
            genome_id="genome_001",
            created_at=datetime.now(timezone.utc),
        ),
        TradeModel(
            symbol="BTC_USD",
            side=TradeSide.SELL,
            fill_price=51000.0,
            quantity=0.05,
            fee=2.55,
            fee_currency="USDT",
            fee_rate=0.001,
            slippage_bps=0.5,
            mode=TradingMode.DRY_RUN,
            genome_id="genome_001",
            realized_pnl=47.45,
            created_at=datetime.now(timezone.utc),
        ),
        TradeModel(
            symbol="ETH_USD",
            side=TradeSide.BUY,
            fill_price=3000.0,
            quantity=1.0,
            fee=3.0,
            fee_currency="USDT",
            fee_rate=0.001,
            slippage_bps=2.0,
            mode=TradingMode.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        ),
    ]

    for trade in trades:
        await trade.save()
    print(f"  Created {len(trades)} trades")

    # Create test positions
    positions = [
        PositionModel(
            symbol="BTC_USD",
            quantity=0.05,
            entry_price=51000.0,
            current_price=51500.0,
            unrealized_pnl=25.0,
        ),
        PositionModel(
            symbol="ETH_USD",
            quantity=1.0,
            entry_price=3000.0,
            current_price=3050.0,
            unrealized_pnl=50.0,
        ),
    ]

    for position in positions:
        await position.save()
    print(f"  Created {len(positions)} positions")

    # Create test genomes
    genomes = [
        GenomeModel(
            symbol="BTC_USD",
            genome_data=b"fake_genome_data_btc",
            fitness=1.25,
            generation=30,
            model_family="NEAT_RNN_V1",
            is_active=True,
            roi_validation=0.85,
            roi_test=0.72,
            max_drawdown=0.08,
            num_trades=150,
            total_return=1.25,
            fitness_score=1.25,
            fee_rate_used=0.001,
            trained_at=datetime.now(timezone.utc),
        ),
        GenomeModel(
            symbol="ETH_USD",
            genome_data=b"fake_genome_data_eth",
            fitness=0.95,
            generation=20,
            model_family="NEAT_RNN_V1",
            is_active=False,
            roi_validation=0.65,
            roi_test=0.55,
            max_drawdown=0.12,
            num_trades=100,
            total_return=0.95,
            fitness_score=0.95,
            fee_rate_used=0.001,
            trained_at=datetime.now(timezone.utc),
        ),
    ]

    for genome in genomes:
        await genome.save()
    print(f"  Created {len(genomes)} genomes")

    # Create test orders
    orders = [
        OrderModel(
            symbol="BTC_USD",
            side=TradeSide.BUY,
            status="filled",
            requested_qty=0.1,
            filled_qty=0.1,
            avg_fill_price=50000.0,
            mode=TradingMode.DRY_RUN,
            created_at=datetime.now(timezone.utc),
            filled_at=datetime.now(timezone.utc),
        ),
        OrderModel(
            symbol="ETH_USD",
            side=TradeSide.BUY,
            status="pending",
            requested_qty=1.0,
            filled_qty=0.0,
            mode=TradingMode.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        ),
    ]

    for order in orders:
        await order.save()
    print(f"  Created {len(orders)} orders")

    # Create test risk events
    risk_events = [
        RiskEventModel(
            symbol="BTC_USD",
            event_type="drawdown_warning",
            severity="warning",
            value=0.12,
            threshold=0.15,
            message="Drawdown at 12% - approaching limit",
            mode=TradingMode.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        ),
        RiskEventModel(
            symbol="BTC_USD",
            event_type="trade_limit",
            severity="warning",
            value=35,
            threshold=40,
            message="Daily trade count at 35",
            mode=TradingMode.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        ),
    ]

    for event in risk_events:
        await event.save()
    print(f"  Created {len(risk_events)} risk events")

    # Create test training runs
    training_runs = [
        TrainingRunModel(
            symbol="BTC_USD",
            generations=30,
            best_fitness=1.25,
            best_roi_validation=0.85,
            best_roi_test=0.72,
            pop_size=150,
            fee_rate=0.001,
            status="completed",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        ),
    ]

    for run in training_runs:
        await run.save()
    print(f"  Created {len(training_runs)} training runs")

    # Create test system config
    configs = [
        SystemConfigModel(key="last_training_run", value={"run_id": 1, "timestamp": datetime.now(timezone.utc).isoformat()}),
        SystemConfigModel(key="active_genomes", value={"BTC_USD": 1, "ETH_USD": 2}),
    ]

    for config in configs:
        await config.save()
    print(f"  Created {len(configs)} system configs")

    print("Test data seeded successfully!")
    return 0


async def main() -> int:
    """Initialize Tortoise and seed data."""
    await Tortoise.init(config=TORTOISE_ORM)
    result = await seed()
    await Tortoise.close_connections()
    return result


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))