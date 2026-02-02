#!/usr/bin/env python3
"""Interactive setup wizard for Telegram Agent.

Usage:
    python scripts/setup_wizard.py [OPTIONS]

Options:
    --env-file PATH   Path to .env file (default: .env.local)
    --help            Show this help message
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer
from scripts.setup_wizard.wizard import SetupWizard

app = typer.Typer(help="Interactive setup wizard for Telegram Agent")


@app.command()
def setup(
    env_file: str = typer.Option(
        ".env.local",
        help="Path to the environment file to create/update",
    ),
):
    """Run the interactive setup wizard."""
    env_path = Path(env_file)
    wizard = SetupWizard(env_path=env_path)
    success = wizard.run()
    raise typer.Exit(0 if success else 1)


if __name__ == "__main__":
    app()
