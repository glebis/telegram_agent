"""Step 6: Verification - validate config and show summary."""

from typing import Tuple

import httpx
from rich.console import Console
from rich.table import Table

from scripts.setup_wizard.env_manager import EnvManager


def validate_bot_token(token: str) -> Tuple[bool, str]:
    """Validate a Telegram bot token via getMe API call."""
    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return True, data["result"].get("username", "")
        return False, ""
    except Exception:
        return False, ""


def run(env: EnvManager, console: Console) -> bool:
    """Show configuration summary and validate. Always returns True."""
    console.print("\n[bold]Step 6/6: Verification[/bold]")

    # Save config
    env.save()
    console.print(f"  [green]OK[/green] Configuration saved to {env.path}")

    # Validate bot token
    token = env.get("TELEGRAM_BOT_TOKEN")
    if token:
        console.print("  Validating bot token...")
        valid, bot_name = validate_bot_token(token)
        if valid:
            console.print(f"  [green]OK[/green] Bot token valid (@{bot_name})")
        else:
            console.print(
                "  [yellow]WARN[/yellow] Could not validate bot token (network issue or invalid token)"
            )

    # Summary table
    console.print()
    table = Table(title="Configuration Summary", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    masked_keys = {"TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET",
                   "OPENAI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"}

    for key, value in env.values.items():
        if key in masked_keys and value:
            display = "********"
        else:
            display = value or "(not set)"
        table.add_row(key, display)

    console.print(table)

    # Next steps
    console.print("\n[bold green]Setup Complete![/bold green]")
    console.print("  Next: python scripts/start_dev.py start --port 8000")
    console.print("  Docs: docs/dev-setup-shell.md")

    return True
