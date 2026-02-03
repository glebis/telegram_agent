#!/usr/bin/env python3
"""
Proactive Task Runner

CLI tool to execute registered proactive tasks.
Usage:
    python -m scripts.proactive_tasks.task_runner run daily-research
    python -m scripts.proactive_tasks.task_runner list
    python -m scripts.proactive_tasks.task_runner status daily-research
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from scripts.proactive_tasks.base_task import BaseTask, TaskResult

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TASK_ENV_REQUIREMENTS = {
    # Research tasks need Google CSE + Firecrawl to avoid silent skips
    "daily-research": ["GOOGLE_API_KEY", "GOOGLE_SEARCH_CX", "FIRECRAWL_API_KEY"],
    "ai-coding-tools-research": ["GOOGLE_API_KEY", "GOOGLE_SEARCH_CX", "FIRECRAWL_API_KEY"],
}


def load_registry() -> Dict[str, Any]:
    """Load task registry from YAML file."""
    registry_path = Path(__file__).parent / "task_registry.yaml"
    if not registry_path.exists():
        raise FileNotFoundError(f"Task registry not found: {registry_path}")

    with open(registry_path, 'r') as f:
        return yaml.safe_load(f)


def load_environment(registry: Dict[str, Any]) -> None:
    """Load environment variables from configured files."""
    settings = registry.get("settings", {})
    env_files = settings.get("env_files", [])

    for env_file in env_files:
        env_path = Path(env_file).expanduser()
        if env_path.exists():
            load_dotenv(env_path)
            logger.debug(f"Loaded environment from: {env_path}")


def get_task_class(task_config: Dict[str, Any]) -> Type[BaseTask]:
    """Dynamically import and return the task class."""
    module_path = task_config.get("module")
    class_name = task_config.get("class", "Task")

    if not module_path:
        raise ValueError("Task configuration must specify 'module'")

    # Handle relative imports
    if module_path.startswith("scripts."):
        module = importlib.import_module(module_path)
    else:
        module = importlib.import_module(module_path)

    task_class = getattr(module, class_name, None)
    if task_class is None:
        raise AttributeError(f"Class '{class_name}' not found in module '{module_path}'")

    if not issubclass(task_class, BaseTask):
        raise TypeError(f"Class '{class_name}' must inherit from BaseTask")

    return task_class


def list_tasks(registry: Dict[str, Any]) -> None:
    """List all registered tasks."""
    tasks = registry.get("tasks", {})

    print("\nRegistered Proactive Tasks:")
    print("=" * 60)

    for task_id, task_config in tasks.items():
        enabled = task_config.get("enabled", True)
        description = task_config.get("description", "No description")
        schedule = task_config.get("schedule", {})

        status = "[enabled]" if enabled else "[disabled]"
        schedule_str = f"{schedule.get('hour', '?'):02d}:{schedule.get('minute', '?'):02d}"

        print(f"\n  {task_id} {status}")
        print(f"    Description: {description}")
        print(f"    Schedule:    {schedule_str} daily")

    print("\n" + "=" * 60)
    print(f"Total: {len(tasks)} tasks")

def _validate_task_env(task_id: str) -> List[str]:
    """Return list of missing env vars required for this task (warn/fail-fast)."""
    required = TASK_ENV_REQUIREMENTS.get(task_id, [])
    return [var for var in required if not os.getenv(var)]


async def run_task(task_id: str, registry: Dict[str, Any]) -> TaskResult:
    """Run a specific task by ID."""
    tasks = registry.get("tasks", {})

    if task_id not in tasks:
        available = ", ".join(tasks.keys())
        raise ValueError(f"Unknown task: {task_id}. Available: {available}")

    task_config = tasks[task_id]

    if not task_config.get("enabled", True):
        logger.warning(f"Task {task_id} is disabled")
        return TaskResult(
            success=False,
            message=f"Task {task_id} is disabled in registry",
        )

    # Load environment
    load_environment(registry)

    missing_env = _validate_task_env(task_id)
    if missing_env:
        msg = f"Missing env vars for task {task_id}: {', '.join(missing_env)}"
        logger.error(msg)
        return TaskResult(success=False, message=msg)

    # Get task class and instantiate
    task_class = get_task_class(task_config)
    task_instance = task_class(config=task_config.get("config", {}))

    # Inject registry settings
    task_instance._registry = registry
    task_instance._task_config = task_config

    # Run the task
    logger.info(f"Executing task: {task_id}")
    result = await task_instance.run()

    # Log result
    if result.success:
        logger.info(f"Task {task_id} completed successfully")
    else:
        logger.error(f"Task {task_id} failed: {result.message}")

    return result


def generate_launchd_plist(task_id: str, registry: Dict[str, Any]) -> str:
    """Generate launchd plist XML for a task."""
    tasks = registry.get("tasks", {})
    settings = registry.get("settings", {})

    if task_id not in tasks:
        raise ValueError(f"Unknown task: {task_id}")

    task_config = tasks[task_id]
    schedule = task_config.get("schedule", {"hour": 10, "minute": 0})
    python_path = settings.get("python_path", "/opt/homebrew/bin/python3.11")
    project_root = settings.get("project_root", "/Users/server/ai_projects/telegram_agent")
    log_dir = settings.get("log_dir", f"{project_root}/logs")

    plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.telegram-agent.{task_id}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>scripts.proactive_tasks.task_runner</string>
        <string>run</string>
        <string>{task_id}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{schedule.get('hour', 10)}</integer>
        <key>Minute</key>
        <integer>{schedule.get('minute', 0)}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_dir}/{task_id}.log</string>

    <key>StandardErrorPath</key>
    <string>{log_dir}/{task_id}.error.log</string>

    <key>WorkingDirectory</key>
    <string>{project_root}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
'''
    return plist


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Proactive Task Runner - Execute and manage scheduled agent tasks"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # List command
    list_parser = subparsers.add_parser("list", help="List all registered tasks")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a specific task")
    run_parser.add_argument("task_id", help="Task identifier (e.g., daily-research)")
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # Generate plist command
    plist_parser = subparsers.add_parser("generate-plist", help="Generate launchd plist for a task")
    plist_parser.add_argument("task_id", help="Task identifier")
    plist_parser.add_argument("--output", "-o", help="Output file path")
    plist_parser.add_argument("--install", action="store_true", help="Install to LaunchAgents")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check task status")
    status_parser.add_argument("task_id", nargs="?", help="Task identifier (optional)")

    args = parser.parse_args(argv)

    try:
        registry = load_registry()

        if args.command == "list":
            list_tasks(registry)
            return 0

        elif args.command == "run":
            if args.dry_run:
                print(f"Would run task: {args.task_id}")
                task_config = registry.get("tasks", {}).get(args.task_id)
                if task_config:
                    print(f"Config: {json.dumps(task_config, indent=2)}")
                return 0

            result = asyncio.run(run_task(args.task_id, registry))
            print(f"\nResult: {json.dumps(result.to_dict(), indent=2)}")
            return 0 if result.success else 1

        elif args.command == "generate-plist":
            plist_content = generate_launchd_plist(args.task_id, registry)

            if args.install:
                output_path = Path.home() / "Library" / "LaunchAgents" / f"com.telegram-agent.{args.task_id}.plist"
            elif args.output:
                output_path = Path(args.output)
            else:
                print(plist_content)
                return 0

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(plist_content)
            print(f"Plist written to: {output_path}")

            if args.install:
                print(f"\nTo activate, run:")
                print(f"  launchctl load {output_path}")
            return 0

        elif args.command == "status":
            # TODO: Implement status checking (last run time, success/failure)
            print("Status command not yet implemented")
            return 0

    except Exception as e:
        logger.exception(f"Task runner failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
