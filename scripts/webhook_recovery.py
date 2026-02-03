#!/usr/bin/env python3
"""
Webhook Recovery Script - Automatically fixes common Telegram webhook issues.

Handles:
- 401 Unauthorized (secret token mismatch)
- Webhook URL mismatch (ngrok URL changed)
- High pending update count (webhook not responding)
- Webhook not set

Called by health_check.sh when webhook issues are detected.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Load environment
project_root = Path(__file__).parent.parent
env_file = os.environ.get("ENV_FILE", project_root / ".env")


def load_env(path: Path) -> dict:
    """Load environment variables from file."""
    env = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# Load env
env_vars = load_env(Path(env_file))
for k, v in env_vars.items():
    if k not in os.environ:
        os.environ[k] = v

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
TUNNEL_PROVIDER = os.environ.get("TUNNEL_PROVIDER", "ngrok").lower()
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"


def log(msg: str, error: bool = False):
    """Print log message."""
    prefix = "ERROR" if error else "INFO"
    print(
        f"[webhook_recovery] {prefix}: {msg}", file=sys.stderr if error else sys.stdout
    )


def get_webhook_info() -> dict | None:
    """Get current webhook info from Telegram."""
    if not BOT_TOKEN:
        log("TELEGRAM_BOT_TOKEN not set", error=True)
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                return data.get("result", {})
    except Exception as e:
        log(f"Failed to get webhook info: {e}", error=True)
    return None


def get_ngrok_url() -> str | None:
    """Get current ngrok public URL."""
    try:
        with urllib.request.urlopen(NGROK_API_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            tunnels = data.get("tunnels", [])
            for tunnel in tunnels:
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
    except Exception as e:
        log(f"Failed to get ngrok URL: {e}", error=True)
    return None


def get_tunnel_url() -> str | None:
    """Get current tunnel URL based on TUNNEL_PROVIDER."""
    if TUNNEL_PROVIDER == "ngrok":
        return get_ngrok_url()

    if TUNNEL_PROVIDER in ("cloudflare", "tailscale"):
        # Stable providers — use WEBHOOK_BASE_URL
        base_url = os.environ.get("WEBHOOK_BASE_URL")
        if base_url:
            return base_url.rstrip("/")
        log(f"WEBHOOK_BASE_URL not set for {TUNNEL_PROVIDER}", error=True)
        return None

    if TUNNEL_PROVIDER in ("none", "skip"):
        base_url = os.environ.get("WEBHOOK_BASE_URL")
        if base_url:
            return base_url.rstrip("/")
        return None

    # Unknown provider, try ngrok as fallback
    return get_ngrok_url()


def set_webhook(webhook_url: str, secret_token: str | None = None) -> bool:
    """Set the Telegram webhook."""
    if not BOT_TOKEN:
        return False

    params = f"url={webhook_url}"
    if secret_token:
        params += f"&secret_token={secret_token}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                log(f"Webhook set successfully: {webhook_url}")
                return True
            else:
                log(f"Failed to set webhook: {data}", error=True)
    except Exception as e:
        log(f"Exception setting webhook: {e}", error=True)
    return False


def diagnose_webhook_error(webhook_info: dict) -> str | None:
    """
    Diagnose the webhook error type.

    Returns:
        Error type: 'unauthorized', 'url_mismatch', 'not_set', 'high_pending', 'other', or None
    """
    if not webhook_info:
        return "not_set"

    url = webhook_info.get("url", "")
    if not url:
        return "not_set"

    last_error = webhook_info.get("last_error_message", "")
    pending_count = webhook_info.get("pending_update_count", 0)

    # Check for specific errors
    if "401" in last_error or "Unauthorized" in last_error:
        return "unauthorized"

    if "Wrong response" in last_error:
        return "unauthorized"  # Usually secret mismatch

    # Check if tunnel URL changed
    tunnel_url = get_tunnel_url()
    if tunnel_url and not url.startswith(tunnel_url):
        return "url_mismatch"

    # High pending count suggests webhook isn't working
    if pending_count > 10:
        return "high_pending"

    if last_error:
        return "other"

    return None


def recover(error_type: str) -> bool:
    """
    Attempt to recover from the webhook error.

    Returns:
        True if recovery succeeded, False otherwise.
    """
    log(f"Attempting recovery for error type: {error_type}")

    tunnel_url = get_tunnel_url()
    if not tunnel_url:
        log("Cannot recover: tunnel not running or URL not available", error=True)
        return False

    webhook_url = f"{tunnel_url}/webhook"

    if error_type == "unauthorized":
        # Re-register with correct secret
        log("Re-registering webhook with secret token...")
        return set_webhook(webhook_url, WEBHOOK_SECRET)

    elif error_type == "url_mismatch":
        # Update to new ngrok URL
        log(f"Updating webhook URL to: {webhook_url}")
        return set_webhook(webhook_url, WEBHOOK_SECRET)

    elif error_type == "not_set":
        # Set the webhook
        log("Setting webhook (was not set)...")
        return set_webhook(webhook_url, WEBHOOK_SECRET)

    elif error_type == "high_pending":
        # Re-register to clear pending and ensure connectivity
        log("Re-registering webhook to clear high pending count...")
        return set_webhook(webhook_url, WEBHOOK_SECRET)

    elif error_type == "other":
        # Try re-registering as general fix
        log("Attempting general webhook re-registration...")
        return set_webhook(webhook_url, WEBHOOK_SECRET)

    return False


def main():
    """Main entry point."""
    if not BOT_TOKEN:
        log("TELEGRAM_BOT_TOKEN not configured", error=True)
        sys.exit(1)

    webhook_info = get_webhook_info()

    # Diagnose the issue
    error_type = diagnose_webhook_error(webhook_info)

    if not error_type:
        log("No webhook issues detected")
        sys.exit(0)

    log(f"Detected webhook issue: {error_type}")
    if webhook_info:
        log(f"  URL: {webhook_info.get('url', 'not set')}")
        log(f"  Last error: {webhook_info.get('last_error_message', 'none')}")
        log(f"  Pending updates: {webhook_info.get('pending_update_count', 0)}")

    # Attempt recovery
    if recover(error_type):
        # Verify recovery worked
        new_info = get_webhook_info()
        new_error = diagnose_webhook_error(new_info)

        if not new_error:
            log("Recovery successful!")
            sys.exit(0)
        else:
            log(
                f"Recovery may have partially worked, remaining issue: {new_error}",
                error=True,
            )
            sys.exit(1)
    else:
        log("Recovery failed", error=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
