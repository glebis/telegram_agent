#!/usr/bin/env python3
"""Interactive setup wizard for Verity.

Usage:
    python scripts/setup_wizard.py [COMMAND] [OPTIONS]

Commands:
    setup              Run the interactive setup wizard (default)
    install-daemon     Install the bot as a launchd service
    uninstall-daemon   Remove the bot launchd service
    daemon-status      Check if the bot service is loaded
"""

import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from scripts.setup_wizard.wizard import SetupWizard  # noqa: E402

app = typer.Typer(help="Interactive setup wizard for Verity")
console = Console()

INSTALL_SCRIPT = project_root / "scripts" / "install_launchd.sh"
UNINSTALL_SCRIPT = project_root / "scripts" / "uninstall_launchd.sh"


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
    """Install all telegram-agent launchd services."""
    if sys.platform != "darwin":
        console.print("[red]Daemon install is macOS-only (launchd).[/red]")
        raise typer.Exit(1)

    if not INSTALL_SCRIPT.exists():
        console.print(f"[red]Install script not found: {INSTALL_SCRIPT}[/red]")
        raise typer.Exit(1)

    result = subprocess.run(
        ["bash", str(INSTALL_SCRIPT)],
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]Install script failed.[/red]")
        raise typer.Exit(1)


@app.command("uninstall-daemon")
def uninstall_daemon() -> None:
    """Remove all telegram-agent launchd services."""
    if sys.platform != "darwin":
        console.print("[red]Daemon uninstall is macOS-only (launchd).[/red]")
        raise typer.Exit(1)

    if not UNINSTALL_SCRIPT.exists():
        console.print(f"[red]Uninstall script not found: {UNINSTALL_SCRIPT}[/red]")
        raise typer.Exit(1)

    result = subprocess.run(
        ["bash", str(UNINSTALL_SCRIPT)],
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]Uninstall script failed.[/red]")
        raise typer.Exit(1)


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
        console.print("  Run: python scripts/setup_wizard.py install-daemon")


if __name__ == "__main__":
    app()
