# Stonks Trading - Claude Code Instructions

This file contains persistent instructions for Claude Code to maintain project consistency.

## Important References

- **Architecture**: `docs/architecture.md` - System architecture and patterns
- **Parity Guarantees**: `docs/parity-guarantees.md` - NEAT parity requirements
- **Docker Setup**: `docs/docker-setup.md` - Container configuration
- **Validation Guide**: `docs/validation-guide.md` - Testing procedures
- **Implementation Plan**: `tmp/MASTER_ARCHITECTURE_PLAN.md` - Phase implementation roadmap
- **Worker Separation Plan**: `tmp/bot-worker-separation-plan.md` - API/Worker architecture (COMPLETED)

## Non-Negotiable Patterns

### 1. No Lazy Imports
```python
# ✅ CORRECT - All imports at module level
from datetime import datetime
from stonks_trading.domains.trading.entities import Trade

def process(trade: Trade) -> None:
    ...

# ❌ WRONG - No TYPE_CHECKING, no string annotations
if TYPE_CHECKING:
    from stonks_trading.domains.trading.entities import Trade

def process(trade: "Trade") -> None:
    from stonks_trading.domains.trading.entities import Trade  # NEVER
```

### 2. CLEAN Architecture Layers
```
Domain Layer (entities.py, repositories.py, services.py, use_cases.py):
  ✅ NO FastAPI imports
  ✅ NO routes, Response, HTTPException
  ✅ Pure business logic only

API Layer (routes.py, dtos.py, mappers.py):
  ✅ FastAPI imports OK here
  ✅ HTTP concerns only
```

### 3. Repository Pattern - Standalone Functions Only
```python
# ✅ CORRECT - Standalone functions ONLY
async def save_strategy(strategy: Strategy) -> Strategy:
    """Save strategy to database."""
    ...

async def get_strategy_by_id(strategy_id: int) -> Strategy | None:
    """Get strategy by ID."""
    ...

# ❌ WRONG - Never class-based repositories
class StrategyRepository:  # NEVER!
    @staticmethod
    async def save(strategy): ...
```

### 4. Router Factory Pattern
```python
# ✅ All routes must use factory pattern
def get_strategies_router() -> APIRouter:
    router = APIRouter(prefix="/strategies", tags=["strategies"])

    @router.get("/")
    async def list_strategies():
        ...

    return router
```

### 5. No Changes to NEAT/main.py
The file `/Users/h3cth0r/Documents/strategy-research/NEAT/main.py` is the canonical reference. Never modify the original NEAT implementation.

### 6. Import Order
```python
# 1. Standard library
from datetime import datetime

# 2. Third-party
import pandas as pd

# 3. Shared layer
from stonks_trading.shared.logger import logger

# 4. Same domain (relative)
from .entities import Strategy

# 5. Cross-domain (absolute)
from stonks_trading.domains.trading.entities import Trade
```

## Validation Protocol

Before completing any implementation:

```bash
# 1. Run parity tests (CRITICAL - must pass)
pytest tests/parity/ -v --timeout=60

# 2. Run unit tests
pytest tests/unit/ -v --timeout=60 -x

# 3. Check for pattern violations
grep -r "TYPE_CHECKING" src/stonks_trading/ --include="*.py" && echo "FAIL: TYPE_CHECKING found"
grep -r "class.*Repository" src/stonks_trading/domains/*/repositories.py && echo "FAIL: Repository classes found"

# 4. Docker services validation
cd infra && docker-compose -f docker-compose.dev.yml up -d
curl -f http://localhost:8000/health
curl -f http://localhost:8501
```

## Domain Structure

Each domain follows this pattern:
```
domains/{name}/
├── __init__.py
├── entities.py      # Pure dataclasses
├── repositories.py # Standalone async functions
├── services.py     # Business logic
├── use_cases.py    # Orchestration
├── routes.py       # API endpoints (APIs only)
├── dtos.py         # Pydantic models
└── mappers.py      # Entity ↔ DTO conversion
```

## Dashboard Pages

Dashboard pages are located at `src/stonks_trading/presentation/dashboard/pages/`:

| Page | File | Purpose |
|------|------|---------|
| Portfolio | `0_Portfolio_Overview.py` | Portfolio metrics |
| Live Trading | `1_Live_Trading.py` | Real-time trading |
| Strategy Mgmt | `2_Strategy_Management.py` | Model/training |
| Analytics | `3_Performance_Analytics.py` | Backtest/live perf |
| Trade Explorer | `4_Trade_Explorer.py` | Trade history |
| Risk Monitor | `5_Risk_Monitor.py` | Risk/capital |

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

Key endpoints:
- `/strategies` - List strategies
- `/models` - Model management (replaces genomes)
- `/bots` - Bot lifecycle
- `/capital/pools` - Capital management
- `/training/runs` - Training runs
- `/backtest` - Backtesting
- `/market/candles/{symbol}` - Market data

## Feature Flags

No explicit feature flags in code. Configuration is environment-based via `settings` in `shared/config.py`.

## Known External References

- **NEAT Prototype**: `/Users/h3cth0r/Documents/strategy-research/NEAT/main.py`
- **Strategy Research**: `/Users/h3cth0r/Documents/strategy-research/`
