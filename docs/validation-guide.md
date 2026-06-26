# Validation Guide

Complete validation steps for all phases of the Stonks Trading platform.

## Quick Start

```bash
# Ensure virtual environment is activated
cd /Users/h3cth0r/Documents/stonks-trading
source .venv/bin/activate

# Run all validations
./scripts/validate_all.sh
```

---

## Phase Validation Matrix

| Phase | Component | Validation Script | Test Command |
|-------|-----------|-------------------|--------------|
| 1 | CLEAN Architecture | `scripts/validate_structure.py` | `pytest tests/unit/ -v` |
| 2 | Data Pipeline | `scripts/validate_ingestion.py` | `pytest tests/integration/test_ingestion.py -v` |
| 3 | Database + Backend | `scripts/validate_phase3.sh` | `pytest tests/integration/test_api.py -v` |
| 4 | Exchange Integration | `scripts/validate_binance.py` | `pytest tests/integration/test_exchange.py -v` |
| 5 | Live Bot + Dashboard | `scripts/validate_bot.py` | `pytest tests/integration/test_bot.py -v` |

---

## Environment Setup

### Required Environment Variables

Create `.env` file with:

```bash
# Database (PostgreSQL)
DATABASE_URL=postgres://stonks:stonks@localhost:5432/stonks_trading

# Binance (Testnet for development)
BINANCE_API_KEY=your_testnet_key
BINANCE_API_SECRET=your_testnet_secret
BINANCE_BASE_URL=https://testnet.binance.vision

# Optional: Discord notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Trading mode
dry_run  # Options: backtest, dry_run, live
```

### Docker Services

```bash
cd infra
docker-compose -f docker-compose.dev.yml up -d

docker-compose -f docker-compose.dev.yml ps
# Expected: stonks-api, stonks-postgres, stonks-minio all healthy
```

---

## Phase 1: CLEAN Architecture

### Validate Domain Structure

```bash
python scripts/validate_structure.py
```

Checks:
- Entities have no framework dependencies
- Services contain pure business logic
- Repositories use standalone functions
- Adapters implement interfaces

### Run Unit Tests

```bash
pytest tests/unit/ -v
```

Expected: 50+ tests passing

---

## Phase 2: Data Pipeline

### Validate Data Ingestion

```bash
python scripts/validate_ingestion.py
```

### Run Ingestion Tests

```bash
pytest tests/integration/test_ingestion.py -v
```

Expected:
- DuckDB operations work
- Feature computation accurate
- Binance symbol conversion correct

---

## Phase 3: Database + Backend

### Initialize Database

```bash
python scripts/init_db.py
```

Expected output:
```
Database initialized successfully!
```

### Seed Test Data (Optional)

```bash
python scripts/seed_test_data.py
```

### Run API Tests

```bash
pytest tests/integration/test_api.py -v
```

Expected: 25 tests passing

### Manual API Validation

```bash
# Health check
curl http://localhost:8000/health

# List trades
curl http://localhost:8000/api/v1/trades

# Create genome
curl -X POST http://localhost:8000/api/v1/genomes \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC_USD","fitness":1.25,"generation":30}'

# Signal evaluation
curl -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.7,"sell_prob":0.3,"current_price":50000}'
```

---

## Phase 4: Exchange Integration

### Validate Binance Testnet

```bash
python scripts/validate_binance.py
```

Expected output:
```
=== Binance Testnet Validation ===
Base URL: https://testnet.binance.vision
1. Testing connectivity... ✅ BTCUSDT price: $xx,xxx.xx
2. Testing account balance... ✅ X assets found
3. Testing fee tier... ✅ Maker: x.xxxx%, Taker: x.xxxx%
4. Testing exchange info... ✅ XX BTC pairs available
=== All validations passed ===
```

### Run Exchange Tests

```bash
# With credentials
export $(grep -E "^BINANCE_" .env | xargs)
pytest tests/integration/test_exchange.py -v
```

Expected: 23 tests passing

### Test Market Endpoints

```bash
# Get current price (now implemented)
curl http://localhost:8000/api/v1/market/price/BTC_USD

# Get OHLCV candles (now implemented)
curl http://localhost:8000/api/v1/market/candles/BTC_USD

# Get portfolio balance (now implemented)
curl http://localhost:8000/api/v1/portfolio/balance

# Execute trade (now implemented)
curl -X POST http://localhost:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC_USD","side":"buy","quantity":0.001}'
```

---

## Phase 5: Live Bot + Dashboard

### Validate Bot Configuration

```bash
python scripts/validate_bot.py
```

### Run Bot Tests

```bash
pytest tests/integration/test_bot.py -v
```

### Test Streamlit Dashboard

```bash
streamlit run src/stonks_trading/presentation/dashboard/app.py
```

Visit http://localhost:8501

---

# Phase 6: Data Explorer, Massive Backfill, and Training Delegation

### Start Services

```bash
cd infra
docker-compose -f docker-compose.dev.yml up -d
```

Expected healthy services: `stonks-api`, `stonks-bot-worker`, `stonks-dashboard`, `stonks-postgres`, `stonks-redis`, `stonks-minio`.

### Validate Endpoints

```bash
bash tmp/validate_endpoints.sh
```

Expected: 19/19 endpoints pass.

### Validate Training Delegation End-to-End

```bash
# Create an async training job (API delegates to Worker subprocess)
curl -X POST http://localhost:8000/api/v1/training/async-training-jobs \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC_USD","generations":2,"population_size":20,"training_capital":10000,"checkpoint_interval":1}'

# Poll until status is completed
curl -s "http://localhost:8000/api/v1/training/async-training-jobs/{job_id}"

# Verify artifacts and model persistence
curl -s "http://localhost:8000/api/v1/training/async-training-jobs/{job_id}/checkpoints"
curl -s "http://localhost:8000/api/v1/training/async-training-jobs/{job_id}/plot" | wc -c
curl -s http://localhost:8000/api/v1/genomes
curl -s http://localhost:8000/api/v1/models/
```

Expected:
- API `/health` stays responsive during training.
- Worker spawns training subprocess and reports progress via Redis.
- Checkpoints saved every `checkpoint_interval` generations.
- Plot HTML generated (large response).
- Winner genome saved to PostgreSQL and visible in `/models/`.

### Validate Dashboard Pages

| Page | URL | Tabs |
|------|-----|------|
| Trading Hub | http://localhost:8501 | Portfolio, Bot Control, Models/Training, Configuration |
| Analytics Hub | http://localhost:8501/page/Analytics_Hub | Performance, Risk + Capital |
| Market Hub | http://localhost:8501/page/Market_Hub | Market Data, Trade History |

---

## Complete Validation

### Run All Tests

```bash
# With Binance credentials
export $(grep -E "^BINANCE_" .env | xargs)

# Full test suite
pytest tests/ -v --tb=short
```

Expected Results by Phase:
- Phase 1: 50+ unit tests passing
- Phase 2: 10+ ingestion tests passing
- Phase 3: 25 API tests passing
- Phase 4: 23 exchange tests passing
- Phase 5: bot + dashboard tests passing
- Phase 6: training delegation tests passing

### Pattern Validation

```bash
python scripts/validate_phase_7_8.py
```

Checks:
- No `TYPE_CHECKING` blocks
- No string annotations
- No imports inside functions in `domains/training/` and `domains/backtesting/`
- Repositories use standalone functions only

### Validation Checklist

- [ ] Environment variables configured
- [ ] Docker services running
- [ ] Database initialized
- [ ] Health endpoint responding
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Binance testnet validated (if Phase 4+)
- [ ] Trade execution working (if Phase 4+)
- [ ] Bot starting without errors (if Phase 5+)
- [ ] Training delegation produces genomes and plots (Phase 6+)
- [ ] Pattern validation passes (Phase 7/8+)

---

## Troubleshooting

### Database "relation does not exist"
```bash
python scripts/init_db.py
```

### API "Connection refused"
```bash
docker-compose -f infra/docker-compose.dev.yml up -d
```

### Tests skipping Binance tests
```bash
export BINANCE_API_KEY=xxx
export BINANCE_API_SECRET=yyy
```

### Import errors
```bash
pip install -e ".[dev]"
```

### Port conflicts
```bash
# Kill processes using ports
lsof -ti:8000 | xargs kill -9
lsof -ti:5432 | xargs kill -9
```

---

## Sign-Off

| Phase | Status | Date | Tests Passing |
|-------|--------|------|---------------|
| 1 | ⬜ | | /50 |
| 2 | ⬜ | | /10 |
| 3 | ⬜ | | /25 |
| 4 | ⬜ | | /23 |
| 5 | ⬜ | | / |

**Approved by:** _________________

**Date:** _________________
