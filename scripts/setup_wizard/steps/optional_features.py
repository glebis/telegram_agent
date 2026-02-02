"""Step 4: Optional features - vault path, Claude work dir."""

from pathlib import Path

import questionary
from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager


def run(env: EnvManager, console: Console) -> bool:
    """Collect optional feature paths. Returns True always."""
    console.print("\n[bold]Step 4/6: Optional Features[/bold] (Enter to skip)")

    # Obsidian vault path
    existing_vault = env.get("OBSIDIAN_VAULT_PATH")
    vault = questionary.text(
        "Obsidian vault path",
        default=existing_vault,
    ).ask()
    if vault is None:
        return True
    if vault:
        expanded = str(Path(vault).expanduser().resolve())
        env.set("OBSIDIAN_VAULT_PATH", expanded)
        vault_name = Path(expanded).name
        env.set("OBSIDIAN_VAULT_NAME", vault_name)

    # Claude Code work directory
    existing_workdir = env.get("CLAUDE_CODE_WORK_DIR")
    workdir = questionary.text(
        "Claude Code work directory",
        default=existing_workdir,
    ).ask()
    if workdir is None:
        return True
    if workdir:
        expanded = str(Path(workdir).expanduser().resolve())
        env.set("CLAUDE_CODE_WORK_DIR", expanded)

    return True
