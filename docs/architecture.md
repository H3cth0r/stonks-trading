# Architecture Documentation

This document describes the architecture of the Stonks Trading system.

For the full implementation plan, see the main PLAN.md in the strategy-research repository.

## Overview

Stonks Trading is a NEAT-based crypto swing trading system built with CLEAN architecture principles, supporting multiple trading strategies.

### Multi-Strategy Architecture (Phase 10)

The system supports multiple trading strategies through a unified interface:

- **NEAT Swing Trading** - Original NEAT-based strategy
- **FIBRAS Value Strategy** - (planned)
- **Custom strategies** - Via plugin interface

Each strategy implements a common interface and can be trained, backtested, and deployed independently.

## Architecture Principles

### 1. No Changes to NEAT/main.py

The file `strategy-research/NEAT/main.py` is the canonical reference. This repository extracts and ports its behavior without modification.

### 2. No Lazy Imports (STRICT)

Direct imports only. No `TYPE_CHECKING` blocks or string annotations.

### 3. CLEAN Architecture

**Domain Layer** (`domains/trading/`):
- `entities.py` — Pure dataclasses (no framework deps)
- `repositories.py` — Standalone functions
- `services.py` — Pure business logic
- `use_cases.py` — Orchestration
- `adapters.py` — External service adapters

**Shared Layer** (`shared/`):
- `config.py` — Pydantic settings
- `logger.py` — Structured logging
- `database.py` — Connection management
- `postgres_models.py` — Tortoise ORM models
- `serializers.py` — Base response classes

**API Layer** (`domains/trading/routes.py`, `dtos.py`, `mappers.py`):
- FastAPI routes (not imported by bot)
- Pydantic request/response DTOs
- Entity ↔ DTO mappers

### 4. Repository Pattern (Single File)

Each domain has one `repositories.py` file with standalone functions:
- `save_trade()`
- `get_trade_by_id()`
- `list_trades_by_symbol()`

### 5. Container Separation

**API Container** (Lightweight - imports HTTP layer only):
- FastAPI routes, DTOs, mappers
- HTTP client for Worker communication
- Database ORM (Tortoise)
- Redis client
- NO bot subprocesses
- NO NEAT dependencies

**Bot Worker Container** (Process Manager):
- HTTP API for bot lifecycle (`worker/main.py`)
- ProcessManager (spawns subprocesses directly)
- Bot dependencies (NEAT, pandas, ta, duckdb)
- Runs bot subprocesses internally
- Shares network with API

**Bot Subprocesses** (Inside Worker):
- NEAT Swing Bot instances
- Exchange adapters
- IngestionOrchestrator per bot

## Directory Structure

```
stonks-trading/
├── src/stonks_trading/
│   ├── shared/              # Infrastructure layer
│   │   ├── config.py
│   │   ├── logger.py
│   │   ├── database.py
│   │   ├── postgres_models.py
│   │   ├── serializers.py
│   │   ├── redis_client.py   # Redis + CacheManager
│   │   └── websocket_api.py # WebSocket + RateLimitedBroadcaster
│   ├── bots/                 # Bot implementations
│   │   ├── base/
│   │   │   ├── strategy.py  # Base strategy interface
│   │   │   └── context.py    # BotContext
│   │   └── neat_swing/      # NEAT swing strategy
│   │       └── strategy.py
│   ├── domains/             # Domain modules
│   │   ├── backtesting/      # Backtesting domain
│   │   ├── botcontrol/       # Bot lifecycle management
│   │   ├── capital/          # Capital management
│   │   ├── health/           # Health checks
│   │   ├── reconciliation/   # Trade reconciliation
│   │   ├── strategies/        # Strategy registry
│   │   ├── trading/          # Trading domain (core)
│   │   └── training/          # Training domain
│   └── presentation/
│       └── dashboard/         # Streamlit dashboard
│           └── pages/         # Dashboard pages
├── tests/
│   ├── parity/              # Parity tests vs NEAT/main.py
│   ├── unit/                # Unit tests
│   ├── integration/          # Integration tests
│   └── e2e/                 # End-to-end tests
└── infra/
    └── docker-compose.dev.yml
```

### Multi-Domain Structure

Each domain follows CLEAN architecture:
- `entities.py` — Pure dataclasses
- `repositories.py` — Standalone async functions
- `services.py` — Business logic
- `use_cases.py` — Orchestration
- `routes.py` — API endpoints (API layer only)
- `dtos.py` — Pydantic request/response
- `mappers.py` — Entity ↔ DTO conversion

## NEAT Extraction

### trading_env.py

Extracted from NEAT/main.py lines 97-179 with configurable parameters:
- `fee_rate` (default 0.001)
- `slippage_bps` (default 0)
- `mode` (backtest, dry_run, live)

With defaults, produces identical results to original.

### fitness.py

Extracted from NEAT/main.py lines 185-236:
- `calculate_fitness()` - composite score
- `calculate_metrics()` - performance metrics

### features.py

Extracted from NEAT/main.py lines 60-88:
- Feature engineering (trend_1h, rsi_1h, rsi_15m, roc, bb_width)
- `prepare_neat_inputs()` - 7 input preparation

### config_builder.py

Extracted from NEAT/main.py lines 341-421:
- Default NEAT configuration
- Programmatic config generation

### reporter.py

Extracted from NEAT/main.py lines 261-334:
- `PeriodicReporter` - training progress
- Checkpoint saving
- Plotly report generation

### trainer.py

Extracted from NEAT/main.py eval_genomes:
- `NeatTrainer` - training orchestration
- `evaluate_genome_on_data()` - evaluation

## Testing

### Parity Tests

Verify extracted code matches original:
- `test_trading_env_parity.py` - TradingEnv equivalence
- Run with same data, compare equity curves

### Unit Tests

Co-located in `domains/trading/tests/`:
- `test_entities.py`
- `test_value_objects.py`
- `test_services.py`

### CI Pipeline

GitHub Actions workflow:
- pytest with coverage (≥80%)
- mypy type checking (strict)
- ruff linting
- Pattern verification (no TYPE_CHECKING, no string annotations)

## References

- **Implementation Plans**: `tmp/MASTER_ARCHITECTURE_PLAN.md`
- **Phase Guides**: `tmp/PHASE_*_IMPLEMENTATION_GUIDE.md`
- **Original NEAT**: `/Users/h3cth0r/Documents/strategy-research/NEAT/main.py`
