"""
Task ledger command handlers.

Commands:
- /tasks — List all scheduled tasks for the chat
- /tasks pause <id> — Disable a task
- /tasks resume <id> — Re-enable a task
- /tasks history <id> — Show last 5 runs with status/duration
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .formatting import escape_html

logger = logging.getLogger(__name__)


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tasks and /tasks <subcommand> <id>."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    args = context.args or []

    # Dispatch subcommands
    if args and args[0].lower() == "pause":
        await _tasks_pause(update, context, args[1:])
    elif args and args[0].lower() == "resume":
        await _tasks_resume(update, context, args[1:])
    elif args and args[0].lower() == "history":
        await _tasks_history(update, context, args[1:])
    else:
        await _tasks_list(update, context)


async def _tasks_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled tasks for the current chat."""
    chat = update.effective_chat
    if not chat or not update.message:
        return

    from ...services.task_ledger_service import get_task_ledger_service

    service = get_task_ledger_service()
    tasks = await service.list_tasks(chat_id=chat.id)

    if not tasks:
        await update.message.reply_text(
            "<b>Scheduled Tasks</b>\n\nNo tasks registered for this chat.",
            parse_mode="HTML",
        )
        return

    lines = ["<b>Scheduled Tasks</b>\n"]
    for task in tasks:
        status_icon = "on" if task.enabled else "off"
        schedule = _format_schedule(task)

        # Fetch last run info
        history = await service.get_run_history(task.id, limit=1)
        last_run = ""
        if history:
            last = history[0]
            last_run = f" | last: {last.status.value}"

        lines.append(
            f"<code>#{task.id}</code> "
            f"<b>{escape_html(task.task_type)}</b> "
            f"[{status_icon}] "
            f"({schedule}{last_run})"
        )

    lines.append("\n<i>Use /tasks pause|resume|history &lt;id&gt;</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _tasks_pause(
    update: Update, context: ContextTypes.DEFAULT_TYPE, args: list
) -> None:
    """Pause (disable) a task by ID."""
    if not update.message:
        return

    task_id = _parse_task_id(args)
    if task_id is None:
        await update.message.reply_text(
            "Usage: <code>/tasks pause &lt;id&gt;</code>", parse_mode="HTML"
        )
        return

    from ...services.task_ledger_service import get_task_ledger_service

    service = get_task_ledger_service()
    try:
        task = await service.get_task(task_id)
        if task is None:
            await update.message.reply_text(f"Task #{task_id} not found.")
            return
        if not task.enabled:
            await update.message.reply_text(f"Task #{task_id} is already paused.")
            return
        await service.toggle_task(task_id)
        name = escape_html(task.task_type)
        await update.message.reply_text(
            f"Task <code>#{task_id}</code> (<b>{name}</b>) paused.",
            parse_mode="HTML",
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc))


async def _tasks_resume(
    update: Update, context: ContextTypes.DEFAULT_TYPE, args: list
) -> None:
    """Resume (enable) a task by ID."""
    if not update.message:
        return

    task_id = _parse_task_id(args)
    if task_id is None:
        await update.message.reply_text(
            "Usage: <code>/tasks resume &lt;id&gt;</code>", parse_mode="HTML"
        )
        return

    from ...services.task_ledger_service import get_task_ledger_service

    service = get_task_ledger_service()
    try:
        task = await service.get_task(task_id)
        if task is None:
            await update.message.reply_text(f"Task #{task_id} not found.")
            return
        if task.enabled:
            await update.message.reply_text(f"Task #{task_id} is already running.")
            return
        await service.toggle_task(task_id)
        name = escape_html(task.task_type)
        await update.message.reply_text(
            f"Task <code>#{task_id}</code> (<b>{name}</b>) resumed.",
            parse_mode="HTML",
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc))


async def _tasks_history(
    update: Update, context: ContextTypes.DEFAULT_TYPE, args: list
) -> None:
    """Show last 5 runs for a task."""
    if not update.message:
        return

    task_id = _parse_task_id(args)
    if task_id is None:
        await update.message.reply_text(
            "Usage: <code>/tasks history &lt;id&gt;</code>", parse_mode="HTML"
        )
        return

    from ...services.task_ledger_service import get_task_ledger_service

    service = get_task_ledger_service()
    task = await service.get_task(task_id)
    if task is None:
        await update.message.reply_text(f"Task #{task_id} not found.")
        return

    runs = await service.get_run_history(task_id, limit=5)
    if not runs:
        await update.message.reply_text(
            f"<b>History for #{task_id}</b> ({escape_html(task.task_type)})\n\n"
            "No runs recorded yet.",
            parse_mode="HTML",
        )
        return

    lines = [f"<b>History for #{task_id}</b> ({escape_html(task.task_type)})\n"]
    for run in runs:
        duration = ""
        if run.started_at and run.completed_at:
            delta = (run.completed_at - run.started_at).total_seconds()
            duration = f" ({delta:.1f}s)"

        status_icon = {
            "success": "ok",
            "error": "ERR",
            "timeout": "TIMEOUT",
        }.get(run.status.value, run.status.value)

        detail = ""
        if run.result_summary:
            detail = f" - {escape_html(run.result_summary)}"
        elif run.error_message:
            detail = f" - {escape_html(run.error_message)}"

        ts = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "?"
        lines.append(f"  [{status_icon}] {ts}{duration}{detail}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# -- Helpers -----------------------------------------------------------


def _parse_task_id(args: list) -> int | None:
    """Extract an integer task ID from argument list."""
    if not args:
        return None
    raw = args[0].lstrip("#")
    try:
        return int(raw)
    except ValueError:
        return None


def _format_schedule(task) -> str:
    """Return a short human-readable schedule description."""
    if task.schedule_cron:
        return f"cron: {task.schedule_cron}"
    if task.schedule_interval_seconds:
        secs = task.schedule_interval_seconds
        if secs >= 3600:
            return f"every {secs // 3600}h"
        if secs >= 60:
            return f"every {secs // 60}m"
        return f"every {secs}s"
    if task.schedule_once_at:
        return f"once: {task.schedule_once_at.strftime('%Y-%m-%d %H:%M')}"
    return "unscheduled"


def register_task_handlers(application) -> None:
    """Register task ledger command handlers with the application."""
    from telegram.ext import CommandHandler

    application.add_handler(CommandHandler("tasks", tasks_command))
