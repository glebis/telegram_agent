#!/usr/bin/env python3
"""Interactive setup wizard for Telegram Agent.

Usage:
    python scripts/setup_wizard.py [COMMAND] [OPTIONS]

Commands:
    setup              Run the interactive setup wizard (default)
    install-daemon     Install the bot as a launchd service
    uninstall-daemon   Remove the bot launchd service
    daemon-status      Check if the bot service is loaded
"""

import re
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from scripts.setup_wizard.wizard import SetupWizard  # noqa: E402

app = typer.Typer(help="Interactive setup wizard for Telegram Agent")
console = Console()

PLIST_NAME = "com.telegram-agent.bot.plist"
PLIST_SRC = project_root / "ops" / "launchd" / PLIST_NAME
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def _substitute_plist(src: Path, dest: Path) -> None:
    """Copy plist template and substitute paths from current environment."""
    content = src.read_text()

    # Substitute hardcoded paths with current values
    python_bin = sys.executable
    env_file = str(project_root / ".env.local")

    # Replace known hardcoded paths
    replacements = {
        "/Users/server/ai_projects/telegram_agent": str(project_root),
        "/opt/homebrew/bin/python3.11": python_bin,
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    # Update PORT and ENV_FILE values in plist XML
    content = re.sub(
        r"(<key>ENV_FILE</key>\s*<string>)[^<]*(</string>)",
        rf"\g<1>{env_file}\g<2>",
        content,
    )

    dest.write_text(content)


@app.command()
def setup(
    env_file: str = typer.Option(
        ".env.local",
        help="Path to the environment file to create/update",
    ),
) -> None:
    """Run the interactive setup wizard."""
    env_path = Path(env_file)
    wizard = SetupWizard(env_path=env_path)
    success = wizard.run()
    raise typer.Exit(0 if success else 1)


@app.command("install-daemon")
def install_daemon() -> None:
    """Install the bot as a macOS launchd service."""
    if sys.platform != "darwin":
        console.print("[red]Daemon install is macOS-only (launchd).[/red]")
        raise typer.Exit(1)

    if not PLIST_SRC.exists():
        console.print(f"[red]Plist template not found: {PLIST_SRC}[/red]")
        raise typer.Exit(1)

    dest = LAUNCH_AGENTS / PLIST_NAME
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)

    # Unload first if already loaded
    if dest.exists():
        subprocess.run(
            ["launchctl", "unload", str(dest)],
            capture_output=True,
        )
        console.print("  Unloaded existing service")

    _substitute_plist(PLIST_SRC, dest)
    console.print(f"  [green]OK[/green] Plist written to {dest}")

    result = subprocess.run(
        ["launchctl", "load", str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print("  [green]OK[/green] Service loaded")
        console.print(
            f"\n  Service will start automatically on login."
            f"\n  Logs: {project_root / 'logs' / 'launchd_bot.log'}"
        )
    else:
        console.print(f"  [red]Failed to load service:[/red] {result.stderr.strip()}")
        raise typer.Exit(1)


@app.command("uninstall-daemon")
def uninstall_daemon() -> None:
    """Remove the bot launchd service."""
    if sys.platform != "darwin":
        console.print("[red]Daemon uninstall is macOS-only (launchd).[/red]")
        raise typer.Exit(1)

    dest = LAUNCH_AGENTS / PLIST_NAME

    if not dest.exists():
        console.print("  [yellow]Service not installed.[/yellow]")
        raise typer.Exit(0)

    result = subprocess.run(
        ["launchctl", "unload", str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print("  [green]OK[/green] Service unloaded")
    else:
        console.print(
            f"  [yellow]WARN[/yellow] launchctl unload: {result.stderr.strip()}"
        )

    dest.unlink(missing_ok=True)
    console.print(f"  [green]OK[/green] Removed {dest}")


@app.command("daemon-status")
def daemon_status() -> None:
    """Check if the bot launchd service is loaded."""
    if sys.platform != "darwin":
        console.print("[red]Daemon status is macOS-only (launchd).[/red]")
        raise typer.Exit(1)

    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True,
    )

    for line in result.stdout.splitlines():
        if "com.telegram-agent" in line:
            parts = line.split("\t")
            pid = parts[0] if parts[0] != "-" else "not running"
            label = parts[-1] if len(parts) >= 3 else line
            console.print(f"  {label}: PID={pid}")

    if "com.telegram-agent" not in result.stdout:
        console.print("  [yellow]No telegram-agent services loaded.[/yellow]")
        dest = LAUNCH_AGENTS / PLIST_NAME
        if dest.exists():
            console.print(f"  Plist exists at {dest} but is not loaded.")
            console.print("  Run: python scripts/setup_wizard.py install-daemon")
        else:
            console.print("  Run: python scripts/setup_wizard.py install-daemon")


if __name__ == "__main__":
    app()
