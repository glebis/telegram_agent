"""Step 1: Pre-flight checks - validates environment before setup."""

from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager
from src.preflight import CheckStatus, run_all_checks


def run(env: EnvManager, console: Console) -> bool:
    """Run preflight checks. Returns False if blocking failures found."""
    console.print("\n[bold]Step 1/8: Pre-flight Checks[/bold]")

    try:
        report = run_all_checks(auto_fix=True)
    except Exception as e:
        console.print(f"  [yellow]WARN[/yellow] Preflight check runner failed: {e}")
        console.print("  Continuing with setup (checks will run again at startup).")
        return True

    for check in report.checks:
        if check.status == CheckStatus.PASS:
            console.print(f"  [green]OK[/green] {check.message}")
        elif check.status == CheckStatus.FIXED:
            console.print(f"  [yellow]FIXED[/yellow] {check.message}")
        elif check.status == CheckStatus.WARNING:
            console.print(f"  [yellow]WARN[/yellow] {check.message}")
        elif check.status == CheckStatus.FAIL:
            console.print(f"  [red]FAIL[/red] {check.message}")
            if check.details:
                console.print(f"       {check.details}")

    if report.should_block_startup:
        console.print(
            "\n[red]Blocking issues found. Please fix them before continuing.[/red]"
        )
        return False

    return True
