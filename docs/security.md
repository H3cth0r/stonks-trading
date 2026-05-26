# Security Documentation

Security procedures and configurations for the Stonks Trading system.

## Table of Contents

- [Overview](#overview)
- [API Key Rotation](#api-key-rotation)
- [IP Allowlist Configuration](#ip-allowlist-configuration)
- [Fly.io Security Settings](#flyio-security-settings)
- [Emergency Access Procedures](#emergency-access-procedures)
- [Security Checklist](#security-checklist)

## Overview

This document describes security hardening measures for production deployment of the Stonks Trading system. Phase 9E implements:

- **Zero-downtime deployments** via Fly.io bluegreen strategy
- **API key rotation** with validation against exchange test endpoints
- **IP-based access control** for administrative endpoints
- **Encrypted secrets** managed via Fly.io secrets

## API Key Rotation

### Prerequisites

- `flyctl` CLI installed and authenticated
- New API credentials from your exchange (Binance or Bitso)
- Discord webhook configured for notifications
- Health check endpoint accessible

### Rotation Procedure

#### Step 1: Validate New Keys

Before rotating, validate the new keys work:

```bash
# For Binance
python scripts/rotate_api_keys.py \
    --exchange binance \
    --api-key "your_new_key" \
    --api-secret "your_new_secret" \
    --validate-only

# For Bitso
python scripts/rotate_api_keys.py \
    --exchange bitso \
    --api-key "your_new_key" \
    --api-secret "your_new_secret" \
    --validate-only
```

**Expected output:**
```
INFO: Validating binance API keys...
INFO: Key validation passed: Valid key. Account can trade: True
INFO: Validation only mode - skipping deployment
```

#### Step 2: Execute Rotation

Run the full rotation with bluegreen deployment:

```bash
# Rotate Binance keys
python scripts/rotate_api_keys.py \
    --exchange binance \
    --api-key "$BINANCE_API_KEY" \
    --api-secret "$BINANCE_API_SECRET"
```

The script will:
1. ✅ Validate keys against exchange test endpoints
2. ✅ Update Fly.io secrets using `fly secrets set`
3. ✅ Trigger bluegreen deployment
4. ✅ Wait 30 seconds for deployment
5. ✅ Verify `/health/ready` endpoint
6. ✅ Send Discord notification on success/failure

#### Step 3: Verify Deployment

Check the deployment status:

```bash
# Check Fly.io status
fly status -a stonks-trading-api

# Verify health endpoint
curl https://stonks-trading-api.fly.dev/health/ready
```

#### Step 4: Monitor for Issues

Watch logs for any authentication errors:

```bash
fly logs -a stonks-trading-api
```

### Rotation Schedule

| Key Type | Rotation Frequency | Notes |
|----------|-------------------|-------|
| Exchange API Keys | Every 90 days | Or immediately if compromised |
| Discord Webhook URL | Annually | Less critical but good practice |
| Database Password | Every 180 days | Managed by Neon/Fly.io |

### Emergency Rotation

If keys are compromised:

1. **Immediately** revoke old keys on the exchange
2. Generate new keys on exchange
3. Run rotation script with new keys
4. Verify trading continues normally
5. Review recent API logs for unauthorized access

## IP Allowlist Configuration

### Overview

IP allowlisting restricts API access to specific IP addresses or networks. This is implemented at the application level using FastAPI middleware.

### Configuration

#### Step 1: Define Allowed IPs

Set the `ALLOWED_IPS` environment variable:

```bash
# Comma-separated list
export ALLOWED_IPS="1.2.3.4,5.6.7.8,10.0.0.0/24"
```

#### Step 2: Generate Configuration

```bash
# Generate all configuration formats
python scripts/setup_ip_allowlist.py --ips "$ALLOWED_IPS"

# Generate specific format
python scripts/setup_ip_allowlist.py --ips "$ALLOWED_IPS" --format python

# Save to file
python scripts/setup_ip_allowlist.py --ips "$ALLOWED_IPS" -o infra/ip_allowlist.py
```

#### Step 3: Apply to Application

The IP middleware should be added to `api.py`:

```python
from stonks_trading.api.middleware import ip_allowlist_middleware

app = FastAPI()
app.middleware("http")(ip_allowlist_middleware)
```

### Supported Formats

| Format | Use Case |
|--------|----------|
| `toml` | Fly.io services configuration reference |
| `nginx` | If using nginx reverse proxy |
| `python` | FastAPI middleware code |
| `docs` | Markdown documentation |

### IP Validation Rules

The script validates:
- IPv4 addresses (`1.2.3.4`)
- IPv6 addresses (`2001:db8::1`)
- CIDR blocks (`192.168.0.0/24`)

### Testing IP Filtering

```bash
# From allowed IP (should succeed)
curl https://stonks-trading-api.fly.dev/health

# From disallowed IP (should get 403)
curl https://stonks-trading-api.fly.dev/health
```

## Fly.io Security Settings

### Application Security

#### Fly.toml Configuration

All Fly.io configurations enforce:

```toml
[http_service]
  force_https = true      # Redirect HTTP to HTTPS
  auto_stop_machines = false  # Keep machines running (trading app)

[[http_service.checks]]
  # Health checks ensure only healthy machines receive traffic
  grace_period = "30s"
  interval = "15s"
  timeout = "5s"
```

#### Secrets Management

Secrets are encrypted and never stored in the codebase:

```bash
# Set secrets
fly secrets set -a stonks-trading-api \
    BINANCE_API_KEY="xxx" \
    BINANCE_API_SECRET="xxx" \
    DISCORD_WEBHOOK_URL="xxx"

# List secrets (names only)
fly secrets list -a stonks-trading-api

# Unset secrets
fly secrets unset -a stonks-trading-api BINANCE_API_KEY
```

### Network Security

#### Private Networking

Fly.io provides private networking between apps:

```bash
# Apps in same organization can communicate privately
# API app can reach bot app via internal DNS
INTERNAL_URL="http://stonks-trading-bot.internal:8080"
```

#### WireGuard VPN

For secure access to internal services:

```bash
# Generate WireGuard config
fly wireguard create

# Export config
fly wireguard list
```

### Deployment Security

#### Bluegreen Deployments

All apps use bluegreen strategy for zero-downtime updates:

```toml
[deploy]
  strategy = "bluegreen"
```

**How it works:**
1. New machines spin up alongside old ones
2. Health checks validate new machines
3. Traffic switches to new machines
4. Old machines shut down

**Benefits:**
- Zero downtime during updates
- Instant rollback if health checks fail
- No dropped requests during deployment

### Monitoring and Alerts

#### Security Events

Discord notifications are sent for:
- API key rotation (start/complete/failed)
- Deployment status
- Health check failures
- Reconciliation issues

#### Log Aggregation

Security-relevant logs are tagged:
- `log_type=AUDIT` - Authentication events
- `log_type=ERROR` - Failed security checks
- `log_type=INFRA` - Deployment events

View in Grafana: http://localhost:3000 (when running observability stack)

## Emergency Access Procedures

### Scenario: Locked Out Due to IP Filter

If you accidentally block all IPs:

1. **SSH into the VM** (bypasses HTTP layer):
   ```bash
   fly ssh console -a stonks-trading-api
   ```

2. **Edit the allowlist** (inside the VM):
   ```bash
   # Add your current IP to the allowlist
   echo "YOUR_IP" >> /app/allowed_ips.txt
   ```

3. **Or temporarily disable filtering** by setting `ALLOWED_IPS=*`:
   ```bash
   fly secrets set -a stonks-trading-api ALLOWED_IPS="*"
   fly deploy -c infra/fly.api.toml --strategy immediate
   ```

4. **Fix the configuration** and redeploy

### Scenario: Compromised API Keys

1. **Revoke keys immediately** on the exchange
2. **Rotate to new keys** using the script
3. **Check logs** for unauthorized activity:
   ```bash
   fly logs -a stonks-trading-api --since 24h
   ```
4. **Review recent trades** for unauthorized orders
5. **Enable additional monitoring** temporarily

### Scenario: Deployment Failure

If bluegreen deployment fails:

1. **Check status**:
   ```bash
   fly status -a stonks-trading-api
   ```

2. **View deployment logs**:
   ```bash
   fly logs -a stonks-trading-api
   ```

3. **Rollback if needed**:
   ```bash
   fly deploy -a stonks-trading-api --image-ref $(fly releases list -a stonks-trading-api | grep -v pending | head -2 | tail -1 | awk '{print $1}')
   ```

4. **Monitor health** after rollback

### Emergency Contacts

| Issue | Action |
|-------|--------|
| Exchange compromise | Revoke keys via exchange dashboard immediately |
| Fly.io outage | Check [status.fly.io](https://status.fly.io) |
| Database issues | Contact Neon support (if using Neon) |
| Discord webhook failure | Check webhook URL in Fly secrets |

## Security Checklist

### Pre-Deployment

- [ ] API keys are set via `fly secrets`, not in code
- [ ] HTTPS is enforced (`force_https = true`)
- [ ] IP allowlist configured for admin endpoints
- [ ] Discord webhook configured for alerts
- [ ] Health checks configured and passing
- [ ] Bluegreen deploy strategy enabled

### Post-Deployment

- [ ] Verify `/health/ready` returns 200
- [ ] Verify `/metrics` is accessible (if public)
- [ ] Test Discord notifications work
- [ ] Verify IP filtering is active (if enabled)
- [ ] Confirm secrets are not in logs
- [ ] Check no sensitive data in error responses

### Periodic

- [ ] Rotate API keys (every 90 days)
- [ ] Review IP allowlist for stale entries
- [ ] Audit access logs for anomalies
- [ ] Verify Discord webhook still works
- [ ] Test emergency procedures

### Incident Response

- [ ] Document any security incidents
- [ ] Review and update procedures
- [ ] Rotate keys if compromise suspected
- [ ] Notify relevant parties via Discord

---

## References

- [Fly.io Security](https://fly.io/docs/reference/security/)
- [Fly.io Secrets](https://fly.io/docs/reference/secrets/)
- [Binance API Security](https://binance-docs.github.io/apidocs/spot/en/#security)
- [Neon Security](https://neon.tech/docs/security/security-overview)
- [OWASP API Security](https://owasp.org/www-project-api-security/)

---

*Last updated: Phase 9E Implementation*
