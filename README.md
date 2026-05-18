# Stonks Trading

NEAT-based crypto swing trading system with CLEAN architecture.

## Overview

This is a production-grade implementation of a NEAT (NeuroEvolution of Augmenting Topologies) based
cryptocurrency trading system. It extracts and modularizes the proven trading logic from the
strategy-research prototype while adding production features like risk management, database
persistence, and API interfaces.

## Architecture

The project follows CLEAN Architecture principles:

- **Domain Layer** (`domains/trading/`): Pure business logic with zero framework dependencies
- **Shared Layer** (`shared/`): Common infrastructure (database, logging, config)
- **Interface Layer**: FastAPI routes and data transfer objects

## Project Structure

```
stonks-trading/
├── src/stonks_trading/
│   ├── shared/              # Infrastructure layer
│   │   ├── config.py        # Pydantic settings
│   │   ├── logger.py        # Structured logging
│   │   ├── serializers.py   # Base response models
│   │   └── database.py      # Database connection
│   └── domains/trading/     # Domain layer (FLAT structure)
│       ├── entities.py      # Domain entities (dataclasses)
│       ├── value_objects.py # Value objects (Pydantic frozen)
│       ├── repositories.py  # Data access (standalone functions)
│       ├── use_cases.py     # Orchestration logic
│       ├── services.py      # Pure business logic
│       ├── adapters.py      # External service adapters
│       ├── routes.py        # FastAPI routes (API only)
│       ├── dtos.py          # API request/response DTOs
│       ├── mappers.py       # Entity ↔ DTO conversion
│       └── neat/            # NEAT training modules
│           ├── trading_env.py
│           ├── fitness.py
│           ├── features.py
│           ├── trainer.py
│           ├── config_builder.py
│           └── reporter.py
├── tests/
│   ├── parity/              # Parity tests vs NEAT/main.py
│   └── integration/         # Cross-domain integration tests
└── infra/                   # Docker and deployment configs
```

## Key Principles

1. **No changes to NEAT/main.py**: The original prototype is the canonical reference.
   Extracted code must pass parity tests with identical default parameters.

2. **No lazy imports**: Direct imports only, no `TYPE_CHECKING` blocks or string annotations.

3. **Domain purity**: Domain layer has zero framework imports (no FastAPI, no ORM).

4. **Repository pattern**: Standalone functions, no classes or ABCs for data access.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (recommended)
pre-commit install

# Run tests
pytest

# Run type checking
mypy src/stonks_trading --strict

# Run linting
ruff check src/stonks_trading
```

## Pre-Commit Hooks

This project uses pre-commit hooks to ensure code quality. They automatically run on every commit:

- **Ruff** - Linting and formatting
- **MyPy** - Type checking
- **General checks** - JSON/YAML validation, trailing whitespace

To run hooks manually on all files:
```bash
pre-commit run --all-files
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## License

MIT
