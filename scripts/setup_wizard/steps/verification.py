"""Step 8: Verification - validate config and show summary."""

import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

from scripts.setup_wizard.env_manager import EnvManager
from scripts.setup_wizard.utils import validate_bot_token

PLUGINS_ROOT = Path(__file__).parent.parent.parent.parent / "plugins"

MASKED_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
}


def _mask(value: str) -> str:
    """Show only the last 4 characters of a secret."""
    if not value:
        return "(not set)"
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _discover_plugins() -> list[tuple[str, bool]]:
    """Discover plugins and their enabled status. Returns (name, enabled) pairs."""
    results = []
    if not PLUGINS_ROOT.exists():
        return results
    try:
        import yaml
    except ImportError:
        return results

    for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        plugin_yaml = plugin_dir / "plugin.yaml"
        if not plugin_yaml.exists():
            continue
        try:
            with open(plugin_yaml) as f:
                config = yaml.safe_load(f) or {}
            name = config.get("name", plugin_dir.name)
            enabled = config.get("enabled", True)
            # Check local override
            local = plugin_dir / "plugin.local.yaml"
            if local.exists():
                with open(local) as lf:
                    override = yaml.safe_load(lf) or {}
                enabled = override.get("enabled", enabled)
            results.append((name, bool(enabled)))
        except Exception:
            results.append((plugin_dir.name, False))
    return results


def _check_daemon_loaded() -> str:
    """Check if the bot launchd service is loaded."""
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "com.telegram-agent.bot" in result.stdout:
            return "loaded"
    except Exception:
        pass
    return "not loaded"


def run(env: EnvManager, console: Console) -> bool:
    """Show configuration summary and validate. Always returns True."""
    console.print("\n[bold]Step 8/8: Verification[/bold]")

    # Save config
    env.save()
    console.print(f"  [green]OK[/green] Configuration saved to {env.path}")

    # Validate bot token
    token = env.get("TELEGRAM_BOT_TOKEN")
    bot_name = ""
    if token:
        console.print("  Validating bot token...")
        valid, bot_name = validate_bot_token(token)
        if valid:
            console.print(f"  [green]OK[/green] Bot token valid (@{bot_name})")
        else:
            console.print(
                "  [yellow]WARN[/yellow] Could not validate bot token"
                " (network issue or invalid token)"
            )

    # Structured summary table
    console.print()
    table = Table(title="Configuration Summary", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    # Bot
    if bot_name:
        table.add_row("Bot", f"@{bot_name}")
    else:
        table.add_row("Bot", _mask(token) if token else "(no token)")

    # Webhook
    webhook_url = env.get("WEBHOOK_BASE_URL") or env.get("TELEGRAM_WEBHOOK_URL")
    table.add_row("Webhook", webhook_url or "not configured")

    # Environment
    table.add_row("Environment", env.get("ENVIRONMENT") or "development")

    # Database
    dsn = env.get("DATABASE_URL")
    if dsn and len(dsn) > 60:
        dsn = dsn[:57] + "..."
    table.add_row("Database", dsn or "sqlite (default)")

    # Plugins
    plugins = _discover_plugins()
    if plugins:
        plugin_parts = []
        for name, enabled in plugins:
            status = "[green]on[/green]" if enabled else "[dim]off[/dim]"
            plugin_parts.append(f"{name} {status}")
        table.add_row("Plugins", ", ".join(plugin_parts))
    else:
        table.add_row("Plugins", "none discovered")

    # Daemon
    daemon_status = _check_daemon_loaded()
    table.add_row("Daemon", daemon_status)

    # API keys (masked)
    api_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]
    key_parts = []
    for key in api_keys:
        val = env.get(key)
        label = key.replace("_API_KEY", "").lower()
        if val:
            key_parts.append(f"{label} {_mask(val)}")
    if key_parts:
        table.add_row("API Keys", ", ".join(key_parts))
    else:
        table.add_row("API Keys", "(none set)")

    console.print(table)

    # Next steps
    console.print("\n[bold green]Setup Complete![/bold green]")
    console.print("\n  [bold]Next steps:[/bold]")
    console.print(
        "  1. Start the bot:    python scripts/start_dev.py start --port 8000"
    )
    console.print("  2. Run diagnostics:  python scripts/doctor.py")
    console.print("  3. Docs:             docs/CONTRIBUTING.md")

    return True
