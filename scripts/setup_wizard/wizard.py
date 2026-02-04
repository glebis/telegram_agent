"""SetupWizard - Orchestrates the interactive setup flow."""

from pathlib import Path
from typing import Callable, List, Tuple

from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager
from scripts.setup_wizard.steps import (
    api_keys,
    core_config,
    database,
    optional_features,
    plugins,
    preflight,
    verification,
    webhook,
)

StepFunc = Callable[[EnvManager, Console], bool]


class SetupWizard:
    """Orchestrates the multi-step interactive setup process."""

    def __init__(self, env_path: Path = None, console: Console = None):
        self.env_path = env_path or Path(".env.local")
        self.console = console or Console()
        self.env = EnvManager(self.env_path)

        self.steps: List[Tuple[str, StepFunc]] = [
            ("Pre-flight Checks", preflight.run),
            ("Core Configuration", core_config.run),
            ("Webhook & Tunnel", webhook.run),
            ("API Keys", api_keys.run),
            ("Optional Features", optional_features.run),
            ("Plugins", plugins.run),
            ("Database", database.run),
            ("Verification", verification.run),
        ]

    def run(self) -> bool:
        """Run all setup steps in sequence. Returns True if completed."""
        self.console.print("\n[bold]Telegram Agent Setup Wizard[/bold]")
        self.console.rule()

        self.env.load()

        try:
            for name, step_func in self.steps:
                ok = step_func(self.env, self.console)
                if not ok:
                    self.console.print(f"\n[yellow]Setup paused at: {name}[/yellow]")
                    self._save_partial()
                    return False

            self.env.save()
            return True

        except KeyboardInterrupt:
            self.console.print("\n\n[yellow]Setup interrupted.[/yellow]")
            self._save_partial()
            return False

    def _save_partial(self):
        """Save whatever config has been collected so far."""
        if self.env.values:
            self.env.save()
            self.console.print(f"  Partial configuration saved to {self.env_path}")
