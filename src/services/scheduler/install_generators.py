"""
OS-level schedule config generators.

These are plain functions that produce config text for launchd, systemd, and cron.
They do NOT run jobs — use JobQueueBackend for in-process execution.
A CLI script (scripts/scheduler_install.py) calls these and writes files to disk.
"""

import getpass
from pathlib import Path

from .base import ScheduledJob, ScheduleType


def generate_launchd_plist(
    job: ScheduledJob,
    project_root: Path,
    python_path: str,
    script_path: str = "scripts/run_heartbeat.py",
) -> str:
    """Generate a macOS launchd plist for a scheduled job."""
    label = f"com.telegram-agent.{job.name}"
    full_script = project_root / script_path
    log_dir = project_root / "logs"

    if job.schedule_type == ScheduleType.INTERVAL:
        interval_xml = (
            f"    <key>StartInterval</key>\n"
            f"    <integer>{job.interval_seconds}</integer>"
        )
    else:
        # Use first daily time
        t = job.daily_times[0] if job.daily_times else None
        if t:
            interval_xml = (
                f"    <key>StartCalendarInterval</key>\n"
                f"    <dict>\n"
                f"        <key>Hour</key>\n"
                f"        <integer>{t.hour}</integer>\n"
                f"        <key>Minute</key>\n"
                f"        <integer>{t.minute}</integer>\n"
                f"    </dict>"
            )
        else:
            interval_xml = "    <key>StartInterval</key>\n    <integer>1800</integer>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{full_script}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}</string>
{interval_xml}
    <key>StandardOutPath</key>
    <string>{log_dir}/{job.name}.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/{job.name}.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""


def generate_systemd_units(
    job: ScheduledJob,
    project_root: Path,
    python_path: str,
    script_path: str = "scripts/run_heartbeat.py",
) -> tuple:
    """Generate systemd service + timer unit files. Returns (service, timer)."""
    full_script = project_root / script_path
    user = getpass.getuser()

    service = f"""[Unit]
Description=Telegram Agent {job.name}
After=network.target

[Service]
Type=oneshot
User={user}
WorkingDirectory={project_root}
ExecStart={python_path} {full_script}
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
"""

    if job.schedule_type == ScheduleType.INTERVAL:
        interval_sec = f"OnUnitActiveSec={job.interval_seconds}s"
        on_boot = f"OnBootSec={job.first_delay_seconds}s"
        timer_schedule = f"{on_boot}\n{interval_sec}"
    else:
        parts = []
        for t in job.daily_times:
            parts.append(f"OnCalendar=*-*-* {t.hour:02d}:{t.minute:02d}:00")
        timer_schedule = "\n".join(parts)

    timer = f"""[Unit]
Description=Timer for Telegram Agent {job.name}

[Timer]
{timer_schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""

    return service, timer


def generate_crontab_entry(
    job: ScheduledJob,
    project_root: Path,
    python_path: str,
    script_path: str = "scripts/run_heartbeat.py",
) -> str:
    """Generate a crontab entry for the job."""
    full_script = project_root / script_path
    cmd = f"cd {project_root} && {python_path} {full_script}"

    if job.schedule_type == ScheduleType.INTERVAL:
        minutes = max(1, (job.interval_seconds or 1800) // 60)
        return f"*/{minutes} * * * * {cmd}  # {job.name}"
    else:
        lines = []
        for t in job.daily_times:
            lines.append(f"{t.minute} {t.hour} * * * {cmd}  # {job.name}")
        return "\n".join(lines)
