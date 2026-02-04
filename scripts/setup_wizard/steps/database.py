"""Step 5: Database initialization."""

import os
import subprocess
import sys

from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager


def init_database_sync(env_vars: dict = None) -> bool:
    """Initialize database via subprocess to avoid async issues."""
    run_env = {**os.environ}
    if env_vars:
        run_env.update(env_vars)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio; from src.core.database import init_database; asyncio.run(init_database())",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=run_env,
    )
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(result.stderr.strip()[-200:])
    return result.returncode == 0


def run(env: EnvManager, console: Console) -> bool:
    """Initialize the database. Non-blocking on failure."""
    console.print("\n[bold]Step 7/8: Database[/bold]")

    db_url = env.get("DATABASE_URL", "sqlite+aiosqlite:///./data/telegram_agent.db")
    if not env.has("DATABASE_URL"):
        env.set("DATABASE_URL", db_url)

    # Save env before subprocess so it can read the values
    env.save()

    console.print("  Initializing database...")
    try:
        success = init_database_sync(env_vars=env.values)
        if success:
            console.print("  [green]OK[/green] Database initialized")
        else:
            console.print(
                "  [yellow]WARN[/yellow] Database initialization returned errors (will retry on first startup)"
            )
    except Exception as e:
        console.print(f"  [yellow]WARN[/yellow] Database init failed: {e}")
        console.print("  Database will be initialized on first startup.")

    return True
