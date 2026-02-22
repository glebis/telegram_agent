#!/usr/bin/env python3
"""Diagnostic tool for Verity.

Runs preflight checks plus additional health checks for webhook,
plugins, tunnel reachability, and env completeness.

Usage:
    python scripts/doctor.py [--json] [--quiet]
"""

import json
import os
import shutil
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from src.preflight import run_all_checks  # noqa: E402
from src.preflight.models import CheckResult, CheckStatus  # noqa: E402

console = Console()
app = typer.Typer(help="Diagnostic checks for Verity")

PLUGINS_ROOT = project_root / "plugins"
ENV_EXAMPLE = project_root / ".env.example"

# Install hints for plugin prerequisites
PREREQ_HINTS = {
    "marker_single": "pip install marker-pdf",
    "claude": "npm install -g @anthropic-ai/claude-code",
    "ffmpeg": "brew install ffmpeg",
}


def _norm_id(raw: str | None) -> str:
    """Normalize identifier to a stable, lowercase slug."""
    return (raw or "").strip().lower().replace("-", "_")


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict (keys only, ignores values)."""
    keys: dict[str, str] = {}
    if not path.exists():
        return keys
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key:
                keys[key] = stripped.split("=", 1)[1].strip()
    return keys


def check_webhook_status() -> CheckResult:
    """Check Telegram webhook status via getWebhookInfo."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return CheckResult(
            name="webhook_status",
            status=CheckStatus.WARNING,
            message="No bot token set — cannot check webhook",
        )

    try:
        import httpx

        resp = httpx.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return CheckResult(
                name="webhook_status",
                status=CheckStatus.FAIL,
                message="getWebhookInfo returned error",
                details=str(data),
            )

        result = data["result"]
        url = result.get("url", "")
        pending = result.get("pending_update_count", 0)
        last_error = result.get("last_error_message", "")

        expected_base = os.environ.get("WEBHOOK_BASE_URL", "")

        if not url:
            return CheckResult(
                name="webhook_status",
                status=CheckStatus.WARNING,
                message="No webhook URL configured in Telegram",
                details="Run start_dev.py or set webhook manually",
            )

        details_parts = [f"URL: {url}", f"Pending: {pending}"]
        if last_error:
            details_parts.append(f"Last error: {last_error}")

        status = CheckStatus.PASS
        message = "Webhook active"
        if expected_base and not url.startswith(expected_base):
            status = CheckStatus.WARNING
            message = "Webhook URL does not match WEBHOOK_BASE_URL"
        if last_error:
            status = CheckStatus.WARNING
            message = f"Webhook has recent error: {last_error}"

        return CheckResult(
            name="webhook_status",
            status=status,
            message=message,
            details="; ".join(details_parts),
        )

    except ImportError:
        return CheckResult(
            name="webhook_status",
            status=CheckStatus.WARNING,
            message="httpx not installed — cannot check webhook",
        )
    except Exception as e:
        return CheckResult(
            name="webhook_status",
            status=CheckStatus.WARNING,
            message=f"Webhook check failed: {type(e).__name__}",
            details=str(e),
        )


def check_plugin_health() -> list[CheckResult]:
    """Check plugin prerequisites and required env vars."""
    results = []
    if not PLUGINS_ROOT.exists():
        results.append(
            CheckResult(
                name="plugins",
                status=CheckStatus.WARNING,
                message="No plugins directory found",
            )
        )
        return results

    try:
        import yaml
    except ImportError:
        results.append(
            CheckResult(
                name="plugins",
                status=CheckStatus.WARNING,
                message="PyYAML not installed — cannot check plugins",
            )
        )
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
        except Exception as e:
            results.append(
                CheckResult(
                    name=f"plugin_{plugin_dir.name}",
                    status=CheckStatus.FAIL,
                    message=f"Cannot read plugin.yaml: {e}",
                )
            )
            continue

        name = config.get("name", plugin_dir.name)
        # Use stable identifier: explicit 'id' field, then directory name
        ident = _norm_id(config.get("id") or plugin_dir.name)

        # Check local override for enabled
        enabled = config.get("enabled", True)
        local = plugin_dir / "plugin.local.yaml"
        if local.exists():
            try:
                with open(local) as lf:
                    override = yaml.safe_load(lf) or {}
                enabled = override.get("enabled", enabled)
            except Exception:
                pass

        if not enabled:
            results.append(
                CheckResult(
                    name=f"plugin_{name}",
                    status=CheckStatus.PASS,
                    message=f"{name}: disabled",
                )
            )
            continue

        # Check binary prereqs using stable identifier (slug), not display name
        issues = []
        if ident == "pdf":
            if not shutil.which("marker_single"):
                hint = PREREQ_HINTS.get("marker_single", "")
                issues.append(f"missing marker_single ({hint})")
        if ident in ("claude_code", "claude"):
            if not (shutil.which("claude") or shutil.which("claude-code")):
                hint = PREREQ_HINTS.get("claude", "")
                issues.append(f"missing Claude Code CLI ({hint})")

        # Check requires env vars from plugin.yaml
        for var in config.get("requires", []):
            if not os.environ.get(var):
                issues.append(f"missing env var {var}")

        if issues:
            results.append(
                CheckResult(
                    name=f"plugin_{name}",
                    status=CheckStatus.WARNING,
                    message=f"{name}: {'; '.join(issues)}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"plugin_{name}",
                    status=CheckStatus.PASS,
                    message=f"{name}: OK",
                )
            )

    return results


def check_tunnel_reachability() -> CheckResult:
    """Check if WEBHOOK_BASE_URL is reachable."""
    base_url = os.environ.get("WEBHOOK_BASE_URL", "")
    if not base_url:
        return CheckResult(
            name="tunnel_reachability",
            status=CheckStatus.WARNING,
            message="WEBHOOK_BASE_URL not set — skipping reachability check",
        )

    try:
        import httpx

        resp = httpx.head(base_url, timeout=10, follow_redirects=True)
        # Any response (even 404) means the tunnel is up
        return CheckResult(
            name="tunnel_reachability",
            status=CheckStatus.PASS,
            message=f"Tunnel reachable (HTTP {resp.status_code})",
            details=base_url,
        )
    except ImportError:
        return CheckResult(
            name="tunnel_reachability",
            status=CheckStatus.WARNING,
            message="httpx not installed — cannot check tunnel",
        )
    except Exception as e:
        return CheckResult(
            name="tunnel_reachability",
            status=CheckStatus.FAIL,
            message=f"Tunnel unreachable: {type(e).__name__}",
            details=f"{base_url} — {e}",
        )


def check_env_completeness() -> CheckResult:
    """Compare running env against .env.example keys."""
    if not ENV_EXAMPLE.exists():
        return CheckResult(
            name="env_completeness",
            status=CheckStatus.WARNING,
            message=".env.example not found",
        )

    example_keys = _load_env_file(ENV_EXAMPLE)
    missing = []
    for key in example_keys:
        if not os.environ.get(key):
            missing.append(key)

    if not missing:
        return CheckResult(
            name="env_completeness",
            status=CheckStatus.PASS,
            message=f"All {len(example_keys)} .env.example keys present in environment",
        )

    return CheckResult(
        name="env_completeness",
        status=CheckStatus.WARNING,
        message=f"{len(missing)}/{len(example_keys)} env vars not set",
        details=", ".join(sorted(missing)),
    )


def run_doctor(output_json: bool = False, quiet: bool = False) -> int:
    """Run all diagnostic checks. Returns exit code."""
    # Load .env if present
    for env_file in [project_root / ".env.local", project_root / ".env"]:
        if env_file.exists():
            env_data = _load_env_file(env_file)
            for k, v in env_data.items():
                if k not in os.environ:
                    os.environ[k] = v
            break

    # 1. Preflight checks (read-only)
    report = run_all_checks(auto_fix=False)
    all_checks = list(report.checks)

    # 2. Webhook status
    all_checks.append(check_webhook_status())

    # 3. Plugin health
    all_checks.extend(check_plugin_health())

    # 4. Tunnel reachability
    all_checks.append(check_tunnel_reachability())

    # 5. Env completeness
    all_checks.append(check_env_completeness())

    # Output
    if output_json:
        data = {
            "checks": [c.to_dict() for c in all_checks],
            "passed": sum(1 for c in all_checks if c.status == CheckStatus.PASS),
            "failed": sum(1 for c in all_checks if c.status == CheckStatus.FAIL),
            "warnings": sum(1 for c in all_checks if c.status == CheckStatus.WARNING),
        }
        print(json.dumps(data, indent=2))
    else:
        _print_rich_table(all_checks, quiet)

    has_failures = any(c.status == CheckStatus.FAIL for c in all_checks)
    return 1 if has_failures else 0


STATUS_STYLES = {
    CheckStatus.PASS: ("[green]PASS[/green]", "[green]"),
    CheckStatus.FAIL: ("[red]FAIL[/red]", "[red]"),
    CheckStatus.WARNING: ("[yellow]WARN[/yellow]", "[yellow]"),
    CheckStatus.FIXED: ("[blue]FIXED[/blue]", "[blue]"),
}


def _print_rich_table(checks: list[CheckResult], quiet: bool = False) -> None:
    """Print checks as a rich table."""
    table = Table(title="Verity Doctor", show_header=True)
    table.add_column("Check", style="cyan", min_width=22)
    table.add_column("Status", min_width=6)
    table.add_column("Message")
    if not quiet:
        table.add_column("Details", style="dim")

    for check in checks:
        status_display, _ = STATUS_STYLES.get(check.status, (check.status.value, ""))
        row = [check.name, status_display, check.message]
        if not quiet:
            row.append(check.details or "")
        table.add_row(*row)

    console.print()
    console.print(table)

    passed = sum(1 for c in checks if c.status == CheckStatus.PASS)
    failed = sum(1 for c in checks if c.status == CheckStatus.FAIL)
    warnings = sum(1 for c in checks if c.status == CheckStatus.WARNING)
    console.print(
        f"\n  [green]{passed} passed[/green]  "
        f"[red]{failed} failed[/red]  "
        f"[yellow]{warnings} warnings[/yellow]"
    )
    if failed:
        console.print("\n  [red]Some checks failed — see details above.[/red]")
    else:
        console.print("\n  [green]All checks passed.[/green]")


@app.command()
def doctor(
    output_json: bool = typer.Option(
        False, "--json", "-j", help="Output results as JSON"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Hide details column"),
) -> None:
    """Run diagnostic checks on the Verity installation."""
    code = run_doctor(output_json=output_json, quiet=quiet)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
