# Dev Environment Separation Plan

## Current State

The telegram_agent currently uses **ngrok for both dev and production**. Production runs via launchd on port 8847, starting ngrok in `run_agent_launchd.sh`, with periodic health checks and webhook recovery scripts to handle ngrok URL changes. Dev uses `start_dev.py` to spin up ngrok on port 8000.

**Pain points:**
- ngrok URLs change on every restart, requiring webhook recovery
- Health check scripts poll every 60s to detect broken webhooks
- Production depends on ngrok uptime and API availability
- No stable staging environment
- Dev and prod share the same bot token (same Telegram bot)
- Recovery scripts add complexity (`webhook_recovery.py`, `health_check.sh`, `auto_update_webhook_on_restart`)

**What works well (keep):**
- Profile system (`config/profiles/{development,production,testing}.yaml`)
- Separate databases (`telegram_agent.db` vs `telegram_agent_dev.db`)
- `.env` hierarchy (global → project → local)
- Docker/Railway support as cloud deployment option
- Admin webhook API for manual intervention

---

## What OpenClaw Does (Relevant Patterns)

OpenClaw avoids ngrok entirely and uses:

| Pattern | How It Works | Applicability |
|---------|-------------|---------------|
| **Bind modes** | `auto/lan/loopback/tailnet/custom` — flexible per-environment networking | High — we need different networking per env |
| **Tailscale Funnel** | Public HTTPS endpoint via Tailscale, zero-config | Medium — good option if already using Tailscale |
| **SSH tunnels** | Programmatic SSH port forwarding to remote hosts | Low — overkill for our use case |
| **State directory isolation** | `OPENCLAW_STATE_DIR` per deployment, each has own DB/config/sessions | High — clean env separation |
| **Token-based auth** | Auto-generated 32-byte hex gateway tokens | Medium — we already have webhook secret |
| **Config schema validation** | Strict validation, refuse to start on bad config | Medium — prevents misconfig in prod |
| **Multi-platform Docker + GHCR** | Semantic versioning, multi-arch builds | Low priority for now |
| **GitHub Actions CI** | Matrix testing across platforms | High — we have none currently |

---

## Recommended Architecture

### Option A: Cloudflare Tunnel (Recommended)

Replace ngrok with `cloudflared` for production. Keep ngrok for dev only.

**Why Cloudflare Tunnel:**
- Free tier supports named tunnels with **stable subdomains** (no URL changes)
- No recovery scripts needed — URL is permanent
- Built-in DDoS protection and TLS
- Runs as daemon, integrates with launchd
- No dependency on ngrok API or dashboard

**Setup:**
```
Production: cloudflared tunnel → https://telegram-bot.yourdomain.com → localhost:8847
Dev:        ngrok (or cloudflared dev tunnel) → localhost:8000
Staging:    cloudflared tunnel → https://telegram-bot-stage.yourdomain.com → localhost:8848
```

**Requires:** A domain you control (for DNS records pointing to Cloudflare).

### Option B: Tailscale Funnel

Use Tailscale's built-in HTTPS exposure.

**Why Tailscale Funnel:**
- Zero-config public HTTPS endpoint
- Stable URL tied to machine name
- Already handles TLS and auth
- No external dependencies beyond Tailscale

**Drawback:** Requires Tailscale running on the host. Less conventional.

### Option C: Static IP + Reverse Proxy

For a Mac mini server, use the static local IP with a reverse proxy (Caddy/nginx) and dynamic DNS or a VPS forwarding port.

**Drawback:** More infrastructure to manage.

---

## Implementation Plan

### Phase 1: Separate Telegram Bots

**Goal:** Dev and prod never interfere with each other.

1. Create a second Telegram bot via @BotFather (e.g., `@YourBot_dev`)
2. Add to env files:
   - `.env` (prod): `TELEGRAM_BOT_TOKEN=<prod_token>`
   - `.env.local` (dev): `TELEGRAM_BOT_TOKEN=<dev_token>`
3. Each bot gets its own webhook URL, so dev/prod can run simultaneously
4. Optional: Create a third bot for staging (`@YourBot_stage`)

### Phase 2: Cloudflare Tunnel for Production

**Goal:** Stable webhook URL, no recovery scripts.

1. Install cloudflared: `brew install cloudflare/cloudflare/cloudflared`
2. Authenticate: `cloudflared tunnel login`
3. Create named tunnel: `cloudflared tunnel create telegram-bot`
4. Configure DNS: `cloudflared tunnel route dns telegram-bot telegram-bot.yourdomain.com`
5. Create tunnel config (`config/cloudflared.yml`):
   ```yaml
   tunnel: <tunnel-id>
   credentials-file: ~/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: telegram-bot.yourdomain.com
       service: http://localhost:8847
     - service: http_status:404
   ```
6. Create launchd plist for cloudflared (runs as daemon)
7. Update `production.yaml` profile:
   ```yaml
   webhook:
     base_url: "https://telegram-bot.yourdomain.com"
     use_ngrok: false
   ```
8. Set webhook once (it never changes):
   ```bash
   curl "https://api.telegram.org/bot${PROD_TOKEN}/setWebhook?url=https://telegram-bot.yourdomain.com/webhook&secret_token=${SECRET}"
   ```
9. Remove ngrok from production startup (`run_agent_launchd.sh`)
10. Simplify health check — no longer needs webhook URL recovery

### Phase 3: Staging Environment

**Goal:** Test changes before they hit production.

1. Add `config/profiles/staging.yaml`:
   ```yaml
   environment: staging
   database:
     url: "sqlite+aiosqlite:///./data/telegram_agent_staging.db"
   webhook:
     base_url: "https://telegram-bot-stage.yourdomain.com"
     use_ngrok: false
   logging:
     level: DEBUG
     format: json
   ```
2. Create a second cloudflared tunnel for staging (port 8848)
3. Add staging bot token to `.env.staging`
4. Add launchd plist for staging service (`com.telegram-agent.staging.plist`)
5. Create a `start_staging.sh` convenience script

### Phase 4: Environment Switching & Workflow

**Goal:** Simple commands to work in each environment.

```bash
# Development (local, ngrok, dev bot)
python scripts/start_dev.py start --port 8000

# Staging (local, cloudflared, staging bot)
ENVIRONMENT=staging python scripts/start_dev.py start --port 8848 --skip-ngrok

# Production (launchd, cloudflared, prod bot)
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist
```

Add a unified CLI:
```bash
# scripts/env.py
python scripts/env.py dev      # start dev
python scripts/env.py stage    # start staging
python scripts/env.py prod     # show prod status
python scripts/env.py status   # show all environments
```

### Phase 5: CI/CD (GitHub Actions)

**Goal:** Automated testing on push, deployment validation.

1. Add `.github/workflows/ci.yml`:
   - Lint (black, flake8, isort)
   - Type check (mypy)
   - Tests (pytest with testing profile)
   - Triggered on: push to `main`, PRs
2. Add `.github/workflows/deploy.yml` (optional):
   - SSH into Mac mini to restart production service
   - Or trigger launchd reload remotely

### Phase 6: Cleanup

**Goal:** Remove ngrok complexity from production path.

1. Remove ngrok from `run_agent_launchd.sh` (replace with cloudflared check)
2. Simplify `health_check.sh` — remove webhook URL recovery logic
3. Remove `webhook_recovery.py` (no longer needed for prod)
4. Keep ngrok utilities in `src/utils/ngrok_utils.py` for dev mode only
5. Update `docker-compose.yml` to use `WEBHOOK_BASE_URL` instead of ngrok service
6. Update setup wizard to offer cloudflared as primary option

---

## Environment Matrix

| Aspect | Development | Staging | Production |
|--------|-------------|---------|------------|
| **Bot** | @YourBot_dev | @YourBot_stage | @YourBot |
| **Tunnel** | ngrok (dynamic) | cloudflared (stable) | cloudflared (stable) |
| **Port** | 8000 | 8848 | 8847 |
| **Database** | `telegram_agent_dev.db` | `telegram_agent_staging.db` | `telegram_agent.db` |
| **Webhook URL** | `*.ngrok-free.app` | `bot-stage.domain.com` | `bot.domain.com` |
| **Log level** | DEBUG | DEBUG | INFO |
| **Log format** | text | json | json |
| **Startup** | `start_dev.py` | `start_staging.sh` | launchd plist |
| **Config** | `profiles/development.yaml` | `profiles/staging.yaml` | `profiles/production.yaml` |
| **Env file** | `.env.local` | `.env.staging` | `.env` |

---

## Immediate Next Steps

1. **Create dev bot** via @BotFather — separate token for development
2. **Decide on tunnel solution** — Cloudflare Tunnel vs Tailscale Funnel vs keep ngrok
3. **Set up Cloudflare Tunnel** if chosen (requires a domain)
4. **Add staging profile** YAML
5. **Add GitHub Actions CI** for automated linting/testing
