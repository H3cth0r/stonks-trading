# Docker Compose Setup Guide

Complete guide for running the Stonks Trading API locally with Docker Compose.

## Overview

This setup provides:
- **PostgreSQL** database (replaces Neon for local dev)
- **MinIO** S3-compatible storage (replaces Tigris for local dev)
- **Redis** cache and state management
- **FastAPI** application with Tortoise ORM
- **Bot Worker** process manager for bot subprocesses

## Prerequisites

- Docker Desktop installed and running
- Docker Compose v2+
- Ports 5432, 8000, 9000, 9001 available

## Quick Start

```bash
cd infra/
docker-compose -f docker-compose.dev.yml up -d
```

Services will be available at:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Bot Worker: http://localhost:8001 (internal)
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- MinIO Console: http://localhost:9001 (login: minioadmin/minioadmin)
- MinIO S3 API: localhost:9000
- Dashboard: http://localhost:8501

## Database Initialization

The database schema must be initialized before first use:

```bash
# From project root
python scripts/init_db.py
```

Or with the local virtual environment:

```bash
source .venv/bin/activate
python scripts/init_db.py
```

## Seed Test Data (Optional)

Populate the database with sample data:

```bash
python scripts/seed_test_data.py
```

## Service Management

### View Running Services
```bash
docker-compose -f docker-compose.dev.yml ps
```

### View Logs
```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.dev.yml logs -f api
docker-compose -f docker-compose.dev.yml logs -f postgres
```

### Restart Services
```bash
# Restart API after code changes
docker-compose -f docker-compose.dev.yml restart api

# Rebuild after dependency changes
docker-compose -f docker-compose.dev.yml up -d --build api
```

### Stop Everything
```bash
docker-compose -f docker-compose.dev.yml down

# Remove volumes (WARNING: deletes database data)
docker-compose -f docker-compose.dev.yml down -v
```

## Configuration

### Environment Variables

The API service uses these environment variables (defined in `docker-compose.dev.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgres://stonks:stonks@postgres:5432/stonks_trading` | PostgreSQL connection string |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `LOG_LEVEL` | `DEBUG` | Logging level |

### Database URL Format

Tortoise ORM requires `postgres://` scheme (not `postgresql://`):

```
# Correct
postgres://user:password@host:port/database

# Incorrect
postgresql://user:password@host:port/database
```

## Validation Steps

### 1. Health Checks

**API Health:**
```bash
curl http://localhost:8000/health
```
Expected response:
```json
{"status": "healthy", "version": "0.1.0"}
```

**Worker Health:**
```bash
curl http://localhost:8001/health
```
Expected response:
```json
{"status": "ok", "service": "bot-worker"}
```

### 2. API Endpoints
```bash
# List trades (empty)
curl http://localhost:8000/api/v1/trades

# Create a genome
curl -X POST http://localhost:8000/api/v1/genomes \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC_USD","fitness":1.25,"generation":30}'

# List genomes
curl http://localhost:8000/api/v1/genomes

# Signal evaluation
curl -X POST http://localhost:8000/api/v1/signals/evaluate \
  -H "Content-Type: application/json" \
  -d '{"buy_prob":0.7,"sell_prob":0.3,"current_price":50000}'
```

### 3. Bot Lifecycle Test

```bash
# Register a bot
curl -X POST http://localhost:8000/api/v1/bots \
  -H "Content-Type: application/json" \
  -d '{"bot_type": "neat_swing", "instance_id": "test", "symbols": ["BTC_USD"], "mode": "dry_run"}'

# Start bot (API delegates to Worker)
curl -X POST http://localhost:8000/api/v1/bots/neat_swing/test/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "dry_run"}'

# Check Worker logs
docker-compose -f docker-compose.dev.yml logs -f bot-worker

# Stop bot
curl -X POST http://localhost:8000/api/v1/bots/neat_swing/test/stop
```

### 4. Run Integration Tests
```bash
# Requires local venv with dependencies installed
source .venv/bin/activate
pytest tests/integration/test_api.py -v
pytest tests/integration/test_bot_control_api.py -v
```

### 4. OpenAPI Documentation
Visit http://localhost:8000/docs for interactive API documentation.

## Database Access

### Connect with psql
```bash
psql postgres://stonks:stonks@localhost:5432/stonks_trading
```

### Common Queries
```sql
-- List all tables
\dt

-- View trades
SELECT * FROM trades ORDER BY created_at DESC LIMIT 10;

-- View genomes
SELECT * FROM genomes WHERE is_active = true;

-- View positions
SELECT * FROM positions;
```

## Troubleshooting

### API Container Exits Immediately
Check logs for database connection errors:
```bash
docker-compose -f docker-compose.dev.yml logs api
```

Common causes:
- Database URL scheme incorrect (must be `postgres://`)
- PostgreSQL container not healthy yet (wait and restart)
- Database tables not initialized (run `init_db.py`)
- Worker container not healthy (API depends on Worker)

### Worker Container Issues
Check Worker logs:
```bash
docker-compose -f docker-compose.dev.yml logs bot-worker
```

Common causes:
- Missing bot dependencies (NEAT, pandas)
- Database connection failure
- Port 8001 already in use

### Bot Fails to Start
If API returns error when starting bot:
```bash
# Check Worker health first
curl http://localhost:8001/health

# Check if bot is already running
curl http://localhost:8000/api/v1/bots/running

# View Worker logs for spawn errors
docker-compose -f docker-compose.dev.yml logs -f bot-worker
```

### Database "relation does not exist" Errors
The schema hasn't been initialized. Run:
```bash
python scripts/init_db.py
```

### Port Already in Use
Stop any local PostgreSQL or other services using ports 5432 or 8000:
```bash
# macOS
brew services stop postgresql

# Or find and kill process
lsof -ti:8000 | xargs kill -9
lsof -ti:5432 | xargs kill -9
```

### Volume Permissions (Linux)
If you get permission errors, you may need to adjust volume permissions:
```bash
docker-compose -f docker-compose.dev.yml down -v
sudo rm -rf postgres_data minio_data
docker-compose -f docker-compose.dev.yml up -d
```

## Production Deployment Notes

For production deployment:

1. **Use Neon Postgres** instead of local PostgreSQL
   - Update `DATABASE_URL` to Neon connection string
   - Keep `postgresql://` scheme - Neon handles it

2. **Use Tigris S3** instead of MinIO
   - Update S3 environment variables
   - Remove MinIO service from docker-compose

3. **Security**
   - Change default MinIO credentials
   - Use strong PostgreSQL passwords
   - Enable SSL/TLS for API

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Network                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │   API        │◄──►│   Worker     │    │  PostgreSQL      │  │
│  │   Port 8000  │HTTP│   Port 8001  │    │  Port 5432       │  │
│  │   stonks-api │    │  stonks-bot  │    │  stonks-postgres │  │
│  └──────────────┘    │   -worker    │    └──────────────────┘  │
│                      └──────────────┘    ┌──────────────────┐  │
│                           │              │     Redis        │  │
│                      ┌────┴────┐         │   Port 6379      │  │
│                      │  Bots   │         │   stonks-redis   │  │
│                      │(subproc)│         └──────────────────┘  │
│                      └─────────┘    ┌──────────────────────┐  │
│                                     │     MinIO            │  │
│                                     │  Port 9000/9001      │  │
│                                     │   stonks-minio       │  │
│                                     └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
   ┌──────────────┐
   │   Client     │
   │  localhost   │
   └──────────────┘
```

**Flow:**
1. Dashboard/API calls API container endpoints
2. API delegates bot operations to Worker via HTTP
3. Worker spawns bot subprocesses (inside Worker container)
4. Bots connect to PostgreSQL/Redis for state
5. All containers share the same Docker network

## See Also

- [Phase 3 Implementation Plan](../strategy-research/phases/phase_3_backend.md)
- [Architecture Documentation](architecture.md)
- [API Endpoints](../docs/api-endpoints.md) (if available)
