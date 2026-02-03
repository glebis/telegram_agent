#!/usr/bin/env python3
"""
CLI to install/uninstall OS-level schedules for heartbeat (and future jobs).

Usage:
    python scripts/scheduler_install.py install heartbeat --backend launchd
    python scripts/scheduler_install.py install heartbeat --backend systemd
    python scripts/scheduler_install.py install heartbeat --backend cron
    python scripts/scheduler_install.py uninstall heartbeat --backend launchd
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_heartbeat_job():
    """Build a ScheduledJob for heartbeat from config."""
    from src.core.config import get_config_value
    from src.services.scheduler.base import ScheduledJob, ScheduleType

    interval_minutes = get_config_value("heartbeat.interval_minutes", 30)

    return ScheduledJob(
        name="heartbeat",
        callback=lambda ctx: None,  # placeholder, not used by generators
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=interval_minutes * 60,
    )


JOBS = {
    "heartbeat": get_heartbeat_job,
}


def get_python_path() -> str:
    """Detect best Python path."""
    # Prefer the configured one
    from src.core.config import get_settings

    settings = get_settings()
    return settings.python_executable


def cmd_install(args: argparse.Namespace) -> None:
    job_factory = JOBS.get(args.job)
    if not job_factory:
        print(f"Unknown job: {args.job}. Available: {', '.join(JOBS)}")
        sys.exit(1)

    job = job_factory()
    python_path = get_python_path()
    backend = args.backend

    if backend == "launchd":
        from src.services.scheduler.install_generators import (
            generate_launchd_plist,
        )

        plist = generate_launchd_plist(job, PROJECT_ROOT, python_path)
        plist_name = f"com.telegram-agent.{job.name}.plist"
        plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name

        plist_path.write_text(plist)
        print(f"Written: {plist_path}")

        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print(f"Loaded: {plist_name}")

    elif backend == "systemd":
        from src.services.scheduler.install_generators import (
            generate_systemd_units,
        )

        service_text, timer_text = generate_systemd_units(
            job, PROJECT_ROOT, python_path
        )
        unit_name = f"telegram-agent-{job.name}"

        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        systemd_dir.mkdir(parents=True, exist_ok=True)

        service_path = systemd_dir / f"{unit_name}.service"
        timer_path = systemd_dir / f"{unit_name}.timer"

        service_path.write_text(service_text)
        timer_path.write_text(timer_text)
        print(f"Written: {service_path}")
        print(f"Written: {timer_path}")

        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{unit_name}.timer"],
            check=True,
        )
        print(f"Enabled: {unit_name}.timer")

    elif backend == "cron":
        from src.services.scheduler.install_generators import (
            generate_crontab_entry,
        )

        entry = generate_crontab_entry(job, PROJECT_ROOT, python_path)
        print(f"Add this to your crontab (crontab -e):\n\n{entry}\n")

    else:
        print(f"Unknown backend: {backend}")
        sys.exit(1)


def cmd_uninstall(args: argparse.Namespace) -> None:
    job_name = args.job
    backend = args.backend

    if backend == "launchd":
        plist_name = f"com.telegram-agent.{job_name}.plist"
        plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name

        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            plist_path.unlink()
            print(f"Removed: {plist_path}")
        else:
            print(f"Not found: {plist_path}")

    elif backend == "systemd":
        unit_name = f"telegram-agent-{job_name}"
        subprocess.run(
            [
                "systemctl",
                "--user",
                "disable",
                "--now",
                f"{unit_name}.timer",
            ],
            check=False,
        )

        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        for ext in (".service", ".timer"):
            p = systemd_dir / f"{unit_name}{ext}"
            if p.exists():
                p.unlink()
                print(f"Removed: {p}")

        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print(f"Uninstalled: {unit_name}")

    elif backend == "cron":
        print(f"Remove the line containing '# {job_name}' from crontab -e")

    else:
        print(f"Unknown backend: {backend}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install/uninstall OS-level schedules")
    sub = parser.add_subparsers(dest="command", required=True)

    install_parser = sub.add_parser("install", help="Install a scheduled job")
    install_parser.add_argument("job", choices=list(JOBS.keys()), help="Job to install")
    install_parser.add_argument(
        "--backend",
        choices=["launchd", "systemd", "cron"],
        required=True,
        help="OS scheduler backend",
    )
    install_parser.set_defaults(func=cmd_install)

    uninstall_parser = sub.add_parser("uninstall", help="Uninstall a scheduled job")
    uninstall_parser.add_argument(
        "job", choices=list(JOBS.keys()), help="Job to uninstall"
    )
    uninstall_parser.add_argument(
        "--backend",
        choices=["launchd", "systemd", "cron"],
        required=True,
        help="OS scheduler backend",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
