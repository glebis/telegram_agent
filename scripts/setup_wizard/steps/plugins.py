"""Step 6: Plugin enablement and prerequisite checks."""

import shutil
from pathlib import Path

import questionary
import yaml
from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager

PLUGINS_ROOT = Path(__file__).parent.parent.parent.parent / "plugins"

# Install hints for missing plugin prerequisites
PREREQ_HINTS = {
    "marker_single": "pip install marker-pdf",
    "claude": "npm install -g @anthropic-ai/claude-code",
    "ffmpeg": "brew install ffmpeg",
}


def _load_plugin_config(plugin_dir: Path) -> dict:
    with open(plugin_dir / "plugin.yaml") as f:
        return yaml.safe_load(f) or {}


def _write_local_override(plugin_dir: Path, enabled: bool) -> None:
    override_path = plugin_dir / "plugin.local.yaml"
    with open(override_path, "w") as f:
        yaml.safe_dump({"enabled": enabled}, f)


def _check_prereqs(name: str) -> list[tuple[str, str]]:
    """Check prerequisites. Returns (description, hint) tuples."""
    missing: list[tuple[str, str]] = []
    if name == "pdf":
        if not shutil.which("marker_single"):
            missing.append(
                ("marker_single binary", PREREQ_HINTS.get("marker_single", ""))
            )
    if name == "claude-code":
        if not (shutil.which("claude") or shutil.which("claude-code")):
            missing.append(("Claude Code CLI", PREREQ_HINTS.get("claude", "")))
    return missing


def run(env: EnvManager, console: Console) -> bool:
    """Enable/disable plugins and warn on missing prerequisites."""
    console.print("\n[bold]Step 6/8: Plugins[/bold]")

    if not PLUGINS_ROOT.exists():
        console.print("  [yellow]WARN[/yellow] No plugins directory found; skipping")
        return True

    plugin_dirs = [
        p
        for p in PLUGINS_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith("_") and (p / "plugin.yaml").exists()
    ]
    if not plugin_dirs:
        console.print("  [yellow]WARN[/yellow] No plugins discovered; skipping")
        return True

    for plugin_dir in plugin_dirs:
        config = _load_plugin_config(plugin_dir)
        name = config.get("name", plugin_dir.name)
        desc = config.get("description", "")
        enabled_default = bool(config.get("enabled", True))

        missing = _check_prereqs(name)
        if missing:
            for prereq_desc, hint in missing:
                msg = f"  [yellow]WARN[/yellow] {name}: missing {prereq_desc}"
                if hint:
                    msg += f"  →  [cyan]{hint}[/cyan]"
                console.print(msg)

        enable = questionary.confirm(
            f"Enable plugin '{name}'? {desc}",
            default=False if missing else enabled_default,
        ).ask()
        if enable is None:
            return False

        if enable and missing:
            console.print(
                "  [yellow]WARN[/yellow] Enabling without"
                " prerequisites may fail at runtime"
            )

        _write_local_override(plugin_dir, enable)
        tag = "[green]Enabled[/green]" if enable else "[cyan]Disabled[/cyan]"
        console.print(f"  {tag} {name}")

    console.print("  [green]OK[/green] Plugin preferences saved (plugin.local.yaml)")
    return True
