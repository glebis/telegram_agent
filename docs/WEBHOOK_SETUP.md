# Webhook & TLS Setup Guide

Telegram bots using webhooks require an HTTPS URL that Telegram's servers can reach over the public internet. When Telegram receives a message for your bot, it POSTs a JSON update to your webhook URL. Your FastAPI server (default port 8000) handles this at the `/webhook` endpoint.

This guide covers every supported method for exposing that endpoint.

## Quick reference

| Method | Best for | Stable URL? | TLS handled by |
|---|---|---|---|
| ngrok | Local dev (macOS) | No (free tier) | ngrok |
| Cloudflare Tunnel | Dev or production | Yes | Cloudflare |
| Tailscale Funnel | Dev on Tailscale network | Yes | Tailscale |
| Reverse proxy (Caddy/Nginx) | VPS / self-hosted prod | Yes | Let's Encrypt |
| Manual `WEBHOOK_BASE_URL` | Cloud platforms (Railway) | Yes | Platform |

---

## 1. Tunnel providers (built-in)

The bot has a pluggable tunnel abstraction (`src/tunnel/`) with three providers. The factory in `src/tunnel/factory.py` picks one based on:

1. Explicit `TUNNEL_PROVIDER` env var
2. Auto-detection from `ENVIRONMENT` (`development` -> ngrok, `production` -> cloudflare, `testing` -> none)

### ngrok (default for development)

ngrok is the default when `ENVIRONMENT=development` (or unset). The bot auto-detects the tunnel URL via the ngrok local API at `http://localhost:4040/api/tunnels`.

**Setup:**

```bash
# Install ngrok
brew install ngrok/ngrok/ngrok   # macOS
# or: https://ngrok.com/download  (Linux/Windows)

# Authenticate (free account required)
ngrok config add-authtoken <YOUR_TOKEN>
```

**Env vars (`.env`):**

```bash
TUNNEL_PROVIDER=ngrok              # Optional — auto-detected in development
NGROK_AUTHTOKEN=<your-token>       # Optional if already in ngrok config
NGROK_PORT=8000                    # Port to forward (default: 8000)
NGROK_REGION=us                    # Region: us, eu, ap, au, sa, jp, in
NGROK_TUNNEL_NAME=telegram-agent   # Tunnel name
```

**How it works:**
- `start_dev.py` calls `get_tunnel_provider(port=port)`, which creates an `NgrokTunnelProvider`
- The provider uses `pyngrok` to open an HTTP tunnel
- The public `https://*.ngrok-free.app` URL is registered as the Telegram webhook
- Because free-tier URLs change on restart, a periodic health check (every 5 minutes) re-registers the webhook if the URL drifts

**Notes:**
- ngrok free tier gives you one tunnel at a time with a random URL
- The bot queries `localhost:4040` to discover the URL, so ngrok must be running before or alongside the bot
- Primarily tested on macOS; works on Linux but requires manual install

### Cloudflare Tunnel (cloudflared)

Cloudflare Tunnel provides stable URLs and is the default for `ENVIRONMENT=production`.

**Two modes:**

| Mode | Use case | URL | Config needed |
|---|---|---|---|
| Quick tunnel | Dev/testing | Random `*.trycloudflare.com` | None |
| Named tunnel | Production | Your domain | Credentials + DNS |

**Install cloudflared:**

```bash
# macOS
brew install cloudflared

# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Linux (other)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

**Quick tunnel (no config):**

```bash
TUNNEL_PROVIDER=cloudflare
# That's it. The bot runs `cloudflared tunnel --url http://localhost:8000`
# and parses the trycloudflare.com URL from stderr.
```

**Named tunnel (production):**

```bash
# One-time setup
cloudflared tunnel login
cloudflared tunnel create telegram-agent
cloudflared tunnel route dns telegram-agent bot.yourdomain.com
```

```bash
# .env
TUNNEL_PROVIDER=cloudflare
CF_TUNNEL_NAME=telegram-agent
CF_CREDENTIALS_FILE=/path/to/credentials.json
CF_CONFIG_FILE=/path/to/config.yml          # Optional
WEBHOOK_BASE_URL=https://bot.yourdomain.com  # Required for named tunnels
```

**Sample `config.yml` for named tunnel:**

```yaml
tunnel: telegram-agent
credentials-file: /path/to/credentials.json
ingress:
  - hostname: bot.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

### Tailscale Funnel

Tailscale Funnel exposes a local port to the internet over your Tailscale network with automatic TLS.

**Setup:**

```bash
# Install Tailscale: https://tailscale.com/download
# Enable Funnel in your tailnet's ACL policy (admin console)
tailscale funnel --bg 8000    # Test manually first
```

**Env vars:**

```bash
TUNNEL_PROVIDER=tailscale
TAILSCALE_HOSTNAME=myhost.tail1234.ts.net  # Optional — auto-detected from `tailscale status --json`
```

**How it works:**
- The `TailscaleTunnelProvider` runs `tailscale funnel <port>` as a subprocess
- It reads the public DNS name from `tailscale status --json`
- The URL is stable across restarts, so periodic webhook recovery is skipped

---

## 2. Reverse proxy with Let's Encrypt

If you have a VPS with a public IP and domain, use a reverse proxy for TLS. Set `TUNNEL_PROVIDER=none` and provide `WEBHOOK_BASE_URL`.

### Caddy (simplest)

Caddy handles TLS certificate provisioning automatically.

```bash
# Install: https://caddyserver.com/docs/install
sudo apt install caddy   # Debian/Ubuntu
brew install caddy        # macOS
```

**Caddyfile:**

```
bot.yourdomain.com {
    reverse_proxy localhost:8000
}
```

```bash
sudo caddy start
```

**Env vars:**

```bash
TUNNEL_PROVIDER=none
WEBHOOK_BASE_URL=https://bot.yourdomain.com
```

### Nginx + certbot

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d bot.yourdomain.com
```

**`/etc/nginx/sites-available/telegram-bot`:**

```nginx
server {
    listen 443 ssl;
    server_name bot.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/bot.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**Env vars:**

```bash
TUNNEL_PROVIDER=none
WEBHOOK_BASE_URL=https://bot.yourdomain.com
```

---

## 3. Manual webhook setup

### Setting `WEBHOOK_BASE_URL` directly

If you already have an HTTPS endpoint (cloud platform, load balancer, etc.), skip the tunnel entirely:

```bash
TUNNEL_PROVIDER=none
WEBHOOK_BASE_URL=https://your-public-url.example.com
```

On startup, the bot calls `get_webhook_base_url()` (in `src/utils/ip_utils.py`), which checks `WEBHOOK_BASE_URL` first, then Railway env vars, then falls back to external IP detection.

### Using the Telegram API directly

You can register or change the webhook without restarting the bot:

```bash
# Set webhook
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-url.example.com/webhook",
    "secret_token": "your-secret-here",
    "allowed_updates": ["message", "callback_query", "poll_answer"]
  }'

# Check current webhook
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" | python3 -m json.tool

# Delete webhook (switch to polling or reset)
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook"
```

### Disabling HTTPS enforcement for local development

If your tunnel already handles TLS but reports an HTTP URL locally:

```bash
WEBHOOK_USE_HTTPS=false
```

This disables the HTTPS check in the webhook URL builder. Only use this for local development.

---

## 4. Platform-specific notes

### Railway

Railway auto-provides environment variables that the bot detects in order:

```
RAILWAY_PUBLIC_DOMAIN -> https://{domain}
RAILWAY_SERVICE_URL
RAILWAY_STATIC_URL
RAILWAY_APP_URL
```

No tunnel provider is needed. The bot's `get_webhook_base_url()` function picks up these variables automatically. Set `TUNNEL_PROVIDER=none` or leave it unset with `ENVIRONMENT=production`.

### Docker

Expose port 8000 from the container and use a reverse proxy or tunnel on the host:

```bash
docker run -p 8000:8000 --env-file .env telegram-agent
```

Then run your tunnel or reverse proxy on the host machine pointing to `localhost:8000`.

### Linux / WSL with public IP

If your server has a public IP and a domain with DNS pointed at it, skip tunnels entirely and use a reverse proxy (Caddy or Nginx) for TLS. See section 2 above.

### macOS (launchd production)

The project includes launchd plists for running as a service. The production plist (`com.telegram-agent.bot`) uses the startup script at `scripts/run_agent_launchd.sh`, which handles tunnel setup via the configured `TUNNEL_PROVIDER`.

---

## 5. Troubleshooting

### Check webhook status

```bash
source .env
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" | python3 -m json.tool
```

Key fields in the response:
- `url` -- the currently registered webhook URL (empty = no webhook)
- `pending_update_count` -- queued messages waiting for delivery
- `last_error_message` -- last delivery error from Telegram
- `last_error_date` -- Unix timestamp of last error

### Common issues

**"Webhook was not set" / empty URL:**
- The tunnel may not have started before webhook registration
- Check that the tunnel process is running: `ps aux | grep -E 'ngrok|cloudflared|tailscale'`
- For ngrok, verify the local API is responding: `curl http://localhost:4040/api/tunnels`

**"Wrong response from the webhook: 502 Bad Gateway":**
- The FastAPI server is not running or not listening on the expected port
- Check: `curl http://localhost:8000/health`

**"SSL certificate problem" / TLS errors:**
- Telegram requires a valid, publicly trusted TLS certificate
- Self-signed certificates need to be uploaded via `setWebhook` with the `certificate` parameter (not supported by the bot's auto-setup; use a tunnel or Let's Encrypt instead)
- Quick tunnels (ngrok, trycloudflare) handle TLS automatically

**ngrok "localhost:4040 connection refused":**
- ngrok is not running. Start it: `ngrok http 8000`
- Or use the dev script: `python scripts/start_dev.py start --port 8000`

**"ERR_NGROK_108: Only one tunnel per ngrok agent":**
- Free-tier ngrok allows one tunnel. Kill existing tunnels: `pkill ngrok`

**Webhook URL does not match tunnel URL:**
- The tunnel URL changed (ngrok free tier). The bot's periodic webhook check should recover this automatically
- Force a refresh: restart the bot or use the admin API at `POST /admin/webhook/refresh`

### Admin API endpoints

The bot exposes webhook management endpoints (requires `X-Api-Key` header derived from `TELEGRAM_WEBHOOK_SECRET`):

```
GET    /admin/webhook/status    -- Current webhook and tunnel status
POST   /admin/webhook/update    -- Set a specific webhook URL
POST   /admin/webhook/refresh   -- Re-detect tunnel URL and re-register
DELETE /admin/webhook/           -- Remove the webhook
```

---

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `TUNNEL_PROVIDER` | auto | `ngrok`, `cloudflare`, `tailscale`, `none`, or empty (auto-detect) |
| `TUNNEL_PORT` | 8000 | Port the tunnel forwards to (also reads `NGROK_PORT`) |
| `WEBHOOK_BASE_URL` | (empty) | Explicit public HTTPS URL; skips tunnel when set |
| `WEBHOOK_USE_HTTPS` | `true` | Enforce HTTPS in webhook URLs; set `false` for local dev |
| `TELEGRAM_WEBHOOK_SECRET` | (empty) | Secret token for webhook request verification |
| `NGROK_AUTHTOKEN` | (empty) | ngrok auth token |
| `NGROK_PORT` | 8000 | Legacy alias for `TUNNEL_PORT` |
| `NGROK_REGION` | `us` | ngrok region |
| `NGROK_TUNNEL_NAME` | `telegram-agent` | ngrok tunnel name |
| `CF_TUNNEL_NAME` | (empty) | Cloudflare named tunnel ID |
| `CF_CREDENTIALS_FILE` | (empty) | Path to cloudflared credentials JSON |
| `CF_CONFIG_FILE` | (empty) | Path to cloudflared config YAML |
| `TAILSCALE_HOSTNAME` | (auto) | Tailscale Funnel hostname |
| `RAILWAY_PUBLIC_DOMAIN` | (empty) | Railway auto-detected domain |
| `ENVIRONMENT` | `development` | Controls default tunnel provider and webhook behavior |
