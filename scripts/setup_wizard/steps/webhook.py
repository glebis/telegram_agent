"""Step 3: Webhook and tunnel configuration."""

import questionary
from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager


def _prompt_int(name: str, current: str | None, default: int) -> int:
    """Prompt for an integer setting with validation."""
    answer = questionary.text(f"{name}", default=current or str(default)).ask()
    if answer is None:
        # User cancelled the wizard
        return None  # type: ignore
    try:
        return int(answer)
    except ValueError:
        return default


def _auto_detect_default(env: EnvManager) -> str:
    """Pick the best default tunnel choice from existing env vars."""
    current = env.get("TUNNEL_PROVIDER")
    if current:
        return current
    if env.get("CF_TUNNEL_NAME") or env.get("CF_CREDENTIALS_FILE"):
        return "cloudflare (recommended for prod)"
    if env.get("TAILSCALE_HOSTNAME"):
        return "tailscale"
    if env.get("NGROK_AUTHTOKEN"):
        return "ngrok"
    return "skip"


def _collect_ngrok_config(env: EnvManager) -> bool:
    """Collect ngrok-specific configuration."""
    authtoken = questionary.password(
        "ngrok authtoken",
        default=env.get("NGROK_AUTHTOKEN"),
    ).ask()
    if authtoken is None:
        return False
    if authtoken:
        env.set("NGROK_AUTHTOKEN", authtoken)

    region = questionary.text(
        "ngrok region (us, eu, ap, au, sa, jp, in)",
        default=env.get("NGROK_REGION", "us"),
    ).ask()
    if region is None:
        return False
    env.set("NGROK_REGION", region or "us")

    port = _prompt_int(
        "Tunnel port",
        env.get("TUNNEL_PORT") or env.get("NGROK_PORT"),
        8000,
    )
    if port is None:
        return False
    env.set("TUNNEL_PORT", str(port))
    env.set("NGROK_PORT", str(port))
    return True


def _collect_cloudflare_config(env: EnvManager) -> bool:
    """Collect Cloudflare Tunnel configuration."""
    tunnel_name = questionary.text(
        "Cloudflare tunnel name",
        default=env.get("CF_TUNNEL_NAME", "telegram-agent"),
    ).ask()
    if tunnel_name is None:
        return False
    if tunnel_name:
        env.set("CF_TUNNEL_NAME", tunnel_name)

    credentials = questionary.text(
        "Cloudflare credentials file path (leave empty for quick tunnel)",
        default=env.get("CF_CREDENTIALS_FILE", ""),
    ).ask()
    if credentials is None:
        return False
    if credentials:
        env.set("CF_CREDENTIALS_FILE", credentials)

    port = _prompt_int(
        "Tunnel port",
        env.get("TUNNEL_PORT"),
        8000,
    )
    if port is None:
        return False
    env.set("TUNNEL_PORT", str(port))
    return True


def _collect_tailscale_config(env: EnvManager) -> bool:
    """Collect Tailscale Funnel configuration."""
    hostname = questionary.text(
        "Tailscale machine hostname (leave empty for auto-detect)",
        default=env.get("TAILSCALE_HOSTNAME", ""),
    ).ask()
    if hostname is None:
        return False
    if hostname:
        env.set("TAILSCALE_HOSTNAME", hostname)

    port = _prompt_int(
        "Tunnel port",
        env.get("TUNNEL_PORT"),
        8000,
    )
    if port is None:
        return False
    env.set("TUNNEL_PORT", str(port))
    return True


def run(env: EnvManager, console: Console) -> bool:
    """Collect webhook base URL, safety limits, and optional tunnel info."""
    console.print("\n[bold]Step 3/8: Webhook & Tunnel[/bold]")

    base_url = questionary.text(
        "Webhook base URL (https://example.com)",
        default=env.get("WEBHOOK_BASE_URL"),
    ).ask()
    if base_url is None:
        return False
    if base_url:
        env.set("WEBHOOK_BASE_URL", base_url.strip())

    use_https = questionary.confirm("Webhook served over HTTPS?", default=True).ask()
    if use_https is None:
        return False
    env.set("WEBHOOK_USE_HTTPS", str(use_https).lower())

    # Limits
    max_body = _prompt_int(
        "Webhook max body bytes",
        env.get("WEBHOOK_MAX_BODY_BYTES"),
        1_048_576,
    )
    if max_body is None:
        return False
    env.set("WEBHOOK_MAX_BODY_BYTES", str(max_body))

    rate_limit = _prompt_int(
        "Webhook rate limit (requests per window)",
        env.get("WEBHOOK_RATE_LIMIT"),
        120,
    )
    if rate_limit is None:
        return False
    env.set("WEBHOOK_RATE_LIMIT", str(rate_limit))

    rate_window = _prompt_int(
        "Webhook rate window seconds",
        env.get("WEBHOOK_RATE_WINDOW_SECONDS"),
        60,
    )
    if rate_window is None:
        return False
    env.set("WEBHOOK_RATE_WINDOW_SECONDS", str(rate_window))

    api_body_limit = _prompt_int(
        "API max body bytes",
        env.get("API_MAX_BODY_BYTES"),
        1_000_000,
    )
    if api_body_limit is None:
        return False
    env.set("API_MAX_BODY_BYTES", str(api_body_limit))

    # Tunnel choice
    default_choice = _auto_detect_default(env)
    tunnel_choice = questionary.select(
        "Configure a tunnel for webhooks?",
        choices=[
            "skip",
            "ngrok",
            "cloudflare (recommended for prod)",
            "tailscale",
        ],
        default=default_choice,
    ).ask()
    if tunnel_choice is None:
        return False

    if tunnel_choice == "ngrok":
        env.set("TUNNEL_PROVIDER", "ngrok")
        if not _collect_ngrok_config(env):
            return False
    elif tunnel_choice.startswith("cloudflare"):
        env.set("TUNNEL_PROVIDER", "cloudflare")
        if not _collect_cloudflare_config(env):
            return False
    elif tunnel_choice == "tailscale":
        env.set("TUNNEL_PROVIDER", "tailscale")
        if not _collect_tailscale_config(env):
            return False
    else:
        env.set("TUNNEL_PROVIDER", "none")

    console.print("  [green]OK[/green] Webhook/tunnel settings captured")
    return True
