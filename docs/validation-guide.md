# Phase 3 Validation Guide

Complete validation steps for Phase 3 (Database + Backend) implementation.

## Prerequisites

```bash
# Ensure virtual environment is set up and dependencies installed
cd /Users/h3cth0r/Documents/stonks-trading
source .venv/bin/activate

# Verify asyncpg is installed
python -c "import asyncpg; print('asyncpg OK')"
```

## Environment Setup

### 1. Local Development (Docker)

```bash
# Update .env file for local Docker
export DATABASE_URL=postgres://stonks:stonks@localhost:5432/stonks_trading
```

### 2. Neon Postgres (Production)

```bash
# Update .env file for Neon
export DATABASE_URL=postgresql://user:password@hostname.region.aws.neon.tech/dbname?sslmode=require
```

**Note**: Tortoise ORM expects `postgres://` for local, but Neon URLs work with `postgresql://`.

## Step 1: Database Initialization

### Initialize Schema
```bash
python scripts/init_db.py
```

Expected output:
```
Initializing database connection...
Generating database schemas...
Database initialized successfully!
```

### Verify Tables Created
```bash
psql $DATABASE_URL -c "\dt"
```

Expected tables:
- `bot_decisions`
- `data_gaps`
- `generation_metrics`
- `genomes`
- `orders`
- `positions`
- `risk_events`
- `system_config`
- `trades`
- `training_runs`

## Step 2: Seed Test Data (Optional)

```bash
python scripts/seed_test_data.py
```

Expected output:
```
Seeding test data...
  Created 3 trades
  Created 2 positions
  Created 2 genomes
  Created 2 orders
  Created 2 risk events
  Created 1 training runs
  Created 2 system configs
Test data seeded successfully!
```

## Step 3: Run Integration Tests

### Database Tests
```bash
pytest tests/integration/test_database.py -v
```

Expected: 19 tests (all skipped if running locally without DATABASE_URL, run manually to verify)

### API Tests
```bash
pytest tests/integration/test_api.py -v
```

Expected:
```
======================== 25 passed, 1 warning in ~2s =========================
```

### All Integration Tests
```bash
pytest tests/integration/ -v
```

## Step 4: Manual API Validation

### Start Services (if using Docker)
```bash
cd infra
docker-compose -f docker-compose.dev.yml up -d
```

### Health Check
```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status": "healthy", "version": "0.1.0"}
```

### Test Trade Endpoints

```bash
# List trades (empty)
curl -s http://localhost:8000/api/v1/trades | jq

# Get trade by ID (not found)
curl -s http://localhost:8000/api/v1/trades/999999 | jq

# Expected: {"detail": "Trade 999999 not found"}
```

### Test Genome Endpoints

```bash
# Create genome
curl -s -X POST http://localhost:8000/api/v1/genomes \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC_USD",
    "fitness": 1.25,
    "generation": 30,
    "fee_rate": 0.001,
    "slippage_bps": 5,
    "mode": "dry_run"
  }' | jq

# List genomes
curl -s http://localhost:8000/api/v1/genomes | jq

# Activate genome
curl -s -X POST http://localhost:8000/api/v1/genomes/activate \
  -H "Content-Type: application/json" \
  -d '{"genome_id": 1}' | jq

# Get active genome
curl -s http://localhost:8000/api/v1/genomes/active | jq
```

### Test Signal Evaluation

```bash
# Buy signal
curl -s -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.7,"sell_prob":0.3,"current_price":50000}' | jq

# Expected: action="buy", should_trade=true

# Sell signal
curl -s -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.2,"sell_prob":0.8,"current_price":50000}' | jq

# Expected: action="sell", should_trade=true

# Hold signal
curl -s -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.4,"sell_prob":0.35,"current_price":50000}' | jq

# Expected: action=null, should_trade=false
```

### Test Portfolio & Risk

```bash
# Portfolio
curl -s http://localhost:8000/api/v1/portfolio | jq

# Balance
curl -s http://localhost:8000/api/v1/portfolio/balance | jq

# Risk status
curl -s http://localhost:8000/api/v1/risk/status | jq

# Risk events
curl -s http://localhost:8000/api/v1/risk/events | jq
```

## Step 5: OpenAPI Documentation

Visit interactive documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Step 6: Docker Compose Validation

### Build and Start
```bash
cd infra
docker-compose -f docker-compose.dev.yml up -d --build
```

### Verify Services
```bash
docker-compose -f docker-compose.dev.yml ps
```

Expected:
```
NAME                STATUS
stonks-api          Up (healthy)
stonks-postgres     Up (healthy)
stonks-minio        Up (healthy)
```

### Run Tests Against Docker
```bash
# Tests use localhost:8000 by default
pytest tests/integration/test_api.py -v
```

## Step 7: Complete Validation Script

Run all validations at once:

```bash
#!/bin/bash
set -e

echo "=== Phase 3 Validation ==="

echo "1. Database Initialization..."
python scripts/init_db.py

echo "2. Running API Tests..."
pytest tests/integration/test_api.py -v --tb=short

echo "3. Health Check..."
curl -sf http://localhost:8000/health || exit 1

echo "4. Testing Endpoints..."
curl -sf http://localhost:8000/api/v1/trades > /dev/null
curl -sf http://localhost:8000/api/v1/genomes > /dev/null
curl -sf http://localhost:8000/api/v1/positions > /dev/null
curl -sf http://localhost:8000/api/v1/risk/events > /dev/null
curl -sf http://localhost:8000/api/v1/portfolio > /dev/null

echo "5. Testing Signal Evaluation..."
curl -sf -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.7,"sell_prob":0.3,"current_price":50000}' > /dev/null

echo ""
echo "✅ All validations passed!"
```

Save as `validate_phase3.sh` and run:
```bash
chmod +x validate_phase3.sh
./validate_phase3.sh
```

## Expected Test Results

### API Test Summary (25 tests)

| Test Category | Tests | Status |
|---------------|-------|--------|
| Health | 1 | ✅ Pass |
| Trade Routes | 4 | ✅ Pass |
| Position Routes | 2 | ✅ Pass |
| Genome Routes | 5 | ✅ Pass |
| Risk Routes | 4 | ✅ Pass |
| Market Routes | 2 | ✅ Pass |
| Portfolio Routes | 2 | ✅ Pass |
| Signal Routes | 3 | ✅ Pass |
| Response Format | 2 | ✅ Pass |

## Troubleshooting

### Tests Fail with "Connection Refused"
- Ensure API server is running: `docker-compose -f docker-compose.dev.yml up -d`
- Check API logs: `docker-compose -f docker-compose.dev.yml logs api`

### "Relation does not exist" Errors
- Database tables not created. Run: `python scripts/init_db.py`

### "Unknown DB scheme" Error
- Database URL must use `postgres://` not `postgresql://` for local development

### Import Errors in Tests
- Ensure virtual environment is activated
- Reinstall dependencies: `pip install -e ".[dev]"`

## Sign-Off Checklist

- [ ] Database schema initialized
- [ ] All 25 API tests passing
- [ ] Health endpoint responding
- [ ] All CRUD endpoints working
- [ ] Docker Compose services healthy
- [ ] OpenAPI documentation accessible
- [ ] Signal evaluation working correctly

## Next Steps

After Phase 3 validation:
1. Merge Phase 3 to `main`
2. Begin Phase 4: Exchange Integration
3. Set up production Neon Postgres
4. Configure production deployment
