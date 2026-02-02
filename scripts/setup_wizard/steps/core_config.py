"""Step 2: Core configuration - bot token, webhook secret, environment."""

import secrets

import questionary
from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager


def run(env: EnvManager, console: Console) -> bool:
    """Collect core configuration. Returns False if user cancels."""
    console.print("\n[bold]Step 2/6: Core Configuration[/bold]")

    # Bot token (required)
    existing_token = env.get("TELEGRAM_BOT_TOKEN")
    token_prompt = "Telegram Bot Token (from @BotFather)"
    if existing_token:
        token_prompt += " (already set, Enter to keep)"

    token = questionary.password(token_prompt).ask()
    if token is None:
        return False
    if token:
        env.set("TELEGRAM_BOT_TOKEN", token)
    elif not existing_token:
        console.print("  [red]Bot token is required.[/red]")
        return False

    # Webhook secret
    existing_secret = env.get("TELEGRAM_WEBHOOK_SECRET")
    auto_generate = questionary.confirm(
        "Auto-generate webhook secret?", default=True
    ).ask()
    if auto_generate is None:
        return False

    if auto_generate:
        secret = secrets.token_hex(32)
        env.set("TELEGRAM_WEBHOOK_SECRET", secret)
        console.print(f"  Generated webhook secret ({len(secret)} chars)")
    else:
        secret = questionary.password("Webhook secret").ask()
        if secret is None:
            return False
        env.set("TELEGRAM_WEBHOOK_SECRET", secret or existing_secret or "")

    # Environment
    environment = questionary.select(
        "Environment profile",
        choices=["development", "production", "testing"],
        default="development",
    ).ask()
    if environment is None:
        return False
    env.set("ENVIRONMENT", environment)

    return True
