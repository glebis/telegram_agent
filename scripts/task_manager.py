#!/usr/bin/env python3
"""
Task Manager - Voice-driven task management integrated with Obsidian vault.

Creates and manages tasks as markdown files in the vault with Dataview-compatible
frontmatter for querying in Obsidian.

Usage:
    python task_manager.py create --title "Task name" --context "Description"
    python task_manager.py list --status active
    python task_manager.py update <task-id> --status active
    python task_manager.py complete <task-id>
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Vault paths
VAULT_ROOT = Path.home() / "Research" / "vault"
TASKS_ROOT = VAULT_ROOT / "Tasks"
DAILY_ROOT = VAULT_ROOT / "Daily"

# Task folders
INBOX = TASKS_ROOT / "inbox"
ACTIVE = TASKS_ROOT / "active"
COMPLETED = TASKS_ROOT / "completed"


def slugify(text: str) -> str:
    """Convert text to filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:50]  # Limit length


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns:
        (frontmatter_dict, body_content)
    """
    if not content.startswith("---\n"):
        return {}, content

    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_text = parts[1]
    body = parts[2]

    # Simple YAML parser (handles basic key: value pairs)
    frontmatter = {}
    for line in frontmatter_text.strip().split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        # Handle lists
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip() for v in value[1:-1].split(",")]

        frontmatter[key] = value

    return frontmatter, body


def create_frontmatter(data: Dict[str, Any]) -> str:
    """Generate YAML frontmatter from dict."""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            if value:
                formatted = "[" + ", ".join(value) + "]"
            else:
                formatted = "[]"
        else:
            formatted = str(value) if value is not None else ""
        lines.append(f"{key}: {formatted}")
    lines.append("---\n")
    return "\n".join(lines)


def create_task(
    title: str,
    context: str = "",
    due: Optional[str] = None,
    tags: Optional[List[str]] = None,
    priority: str = "medium",
    source: str = "voice",
) -> Path:
    """Create a new task in the inbox.

    Args:
        title: Task title
        context: Task description/context
        due: Due date (ISO format or natural like "2026-02-15")
        tags: List of tags
        priority: low, medium, high
        source: voice, telegram, manual

    Returns:
        Path to created task file
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    daily_note = f"Daily/{date_str}"

    # Create filename
    slug = slugify(title)
    filename = f"{date_str}-{slug}.md"
    filepath = INBOX / filename

    # Prepare frontmatter
    frontmatter = {
        "created": now.isoformat(),
        "due": due or "",
        "status": "inbox",
        "tags": tags or [],
        "priority": priority,
        "context": context[:50] if context else "",
        "source": source,
    }

    # Build content
    content_parts = [
        create_frontmatter(frontmatter),
        f"# {title}\n",
        "## Context\n",
        f"{context}\n\n" if context else "\n",
        "## Tasks\n",
        "- [ ] \n\n",
        "## Notes\n\n\n",
        "## Related\n",
        f"- [[{daily_note}]]\n",
    ]

    content = "".join(content_parts)

    # Write file
    INBOX.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")

    return filepath


def list_tasks(
    status: Optional[str] = None,
    tags: Optional[List[str]] = None,
    due_before: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tasks matching criteria.

    Args:
        status: inbox, active, completed (None = all)
        tags: Filter by tags
        due_before: ISO date string

    Returns:
        List of task dicts with keys: path, title, frontmatter
    """
    results = []

    # Determine which folders to search
    if status == "inbox":
        folders = [INBOX]
    elif status == "active":
        folders = [ACTIVE]
    elif status == "completed":
        folders = [COMPLETED]
    else:
        folders = [INBOX, ACTIVE, COMPLETED]

    for folder in folders:
        if not folder.exists():
            continue

        for filepath in folder.glob("*.md"):
            content = filepath.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)

            # Extract title from first heading
            title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = title_match.group(1) if title_match else filepath.stem

            # Apply filters
            if tags:
                task_tags = frontmatter.get("tags", [])
                if isinstance(task_tags, str):
                    task_tags = [task_tags]
                if not any(tag in task_tags for tag in tags):
                    continue

            if due_before:
                task_due = frontmatter.get("due", "")
                if not task_due or task_due > due_before:
                    continue

            results.append({
                "path": str(filepath),
                "title": title,
                "frontmatter": frontmatter,
                "status": frontmatter.get("status", "unknown"),
            })

    return results


def update_task_status(task_path: Path, new_status: str) -> None:
    """Update task status and move to appropriate folder.

    Args:
        task_path: Path to task file
        new_status: inbox, active, completed
    """
    content = task_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)

    # Update frontmatter
    frontmatter["status"] = new_status
    if new_status == "completed":
        frontmatter["completed"] = datetime.now().isoformat()

    # Determine target folder
    if new_status == "inbox":
        target_folder = INBOX
    elif new_status == "active":
        target_folder = ACTIVE
    elif new_status == "completed":
        target_folder = COMPLETED
    else:
        raise ValueError(f"Invalid status: {new_status}")

    # Write updated content to new location
    target_folder.mkdir(parents=True, exist_ok=True)
    new_path = target_folder / task_path.name
    new_content = create_frontmatter(frontmatter) + body
    new_path.write_text(new_content, encoding="utf-8")

    # Remove old file if different location
    if new_path != task_path:
        task_path.unlink()


def get_today_tasks() -> str:
    """Generate a Dataview query for today's tasks.

    Returns:
        Dataview query string to embed in daily note
    """
    today = datetime.now().strftime("%Y-%m-%d")

    query = f'''## Today's Tasks

```dataview
TASK
FROM "Tasks/active" OR "Tasks/inbox"
WHERE !completed
AND (due = date("{today}") OR due < date("{today}"))
SORT priority DESC, due ASC
```

## Active Tasks

```dataview
TABLE without id
  file.link as Task,
  priority as Priority,
  due as Due,
  tags as Tags
FROM "Tasks/active"
WHERE status = "active"
SORT priority DESC, due ASC
LIMIT 10
```
'''

    return query


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage tasks in Obsidian vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new task")
    create_parser.add_argument("--title", required=True, help="Task title")
    create_parser.add_argument("--context", default="", help="Task context/description")
    create_parser.add_argument("--due", help="Due date (YYYY-MM-DD)")
    create_parser.add_argument("--tags", nargs="*", help="Tags")
    create_parser.add_argument("--priority", default="medium", choices=["low", "medium", "high"])
    create_parser.add_argument("--source", default="manual", help="Source (voice, telegram, manual)")

    # List command
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--status", choices=["inbox", "active", "completed"])
    list_parser.add_argument("--tags", nargs="*", help="Filter by tags")
    list_parser.add_argument("--due-before", help="Due before date (YYYY-MM-DD)")
    list_parser.add_argument("--format", choices=["text", "json"], default="text")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update task status")
    update_parser.add_argument("task_id", help="Task filename or slug")
    update_parser.add_argument("--status", required=True, choices=["inbox", "active", "completed"])

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark task as completed")
    complete_parser.add_argument("task_id", help="Task filename or slug")

    # Daily query command
    subparsers.add_parser("daily-query", help="Generate Dataview query for daily note")

    args = parser.parse_args()

    # Execute command
    if args.command == "create":
        filepath = create_task(
            title=args.title,
            context=args.context,
            due=args.due,
            tags=args.tags,
            priority=args.priority,
            source=args.source,
        )
        print(f"Created task: {filepath}")
        print(f"Obsidian link: [[{filepath.relative_to(VAULT_ROOT)}]]")

    elif args.command == "list":
        tasks = list_tasks(
            status=args.status,
            tags=args.tags,
            due_before=args.due_before,
        )

        if args.format == "json":
            print(json.dumps(tasks, indent=2))
        else:
            for task in tasks:
                status_emoji = {"inbox": "📥", "active": "🔄", "completed": "✅"}.get(
                    task["status"], "❓"
                )
                print(f"{status_emoji} [{task['status']}] {task['title']}")
                if task["frontmatter"].get("due"):
                    print(f"   Due: {task['frontmatter']['due']}")
                print(f"   Path: {task['path']}\n")

    elif args.command == "update":
        # Find task by ID (filename or slug)
        task_path = None
        for folder in [INBOX, ACTIVE, COMPLETED]:
            potential = folder / f"{args.task_id}.md"
            if potential.exists():
                task_path = potential
                break
            # Try glob match
            matches = list(folder.glob(f"*{args.task_id}*.md"))
            if matches:
                task_path = matches[0]
                break

        if not task_path:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        update_task_status(task_path, args.status)
        print(f"Updated task to {args.status}: {task_path.name}")

    elif args.command == "complete":
        # Find and complete task
        task_path = None
        for folder in [INBOX, ACTIVE]:
            potential = folder / f"{args.task_id}.md"
            if potential.exists():
                task_path = potential
                break
            matches = list(folder.glob(f"*{args.task_id}*.md"))
            if matches:
                task_path = matches[0]
                break

        if not task_path:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        update_task_status(task_path, "completed")
        print(f"Completed task: {task_path.name}")

    elif args.command == "daily-query":
        print(get_today_tasks())


if __name__ == "__main__":
    main()
