"""Beads issue tracker command handlers.

Commands:
- /bd — List unblocked (ready) issues
- /bd add <title> — Create a new issue
- /bd done <id> — Close an issue
- /bd show <id> — Show issue details
- /bd all — List all issues
- /bd stats — Project statistics
- /bd block <child> <parent> — Add dependency
"""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from ...services.beads_service import get_beads_service
from .formatting import escape_html

logger = logging.getLogger(__name__)

# Priority labels for display
_PRIORITY_LABEL = {0: "P0", 1: "P1", 2: "P2", 3: "P3"}


async def bd_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /bd and /bd <subcommand>."""
    if not update.message:
        return

    args = context.args or []

    if not args:
        await _bd_ready(update)
    elif args[0] == "add":
        await _bd_add(update, args[1:])
    elif args[0] == "done":
        await _bd_done(update, args[1:])
    elif args[0] == "show":
        await _bd_show(update, args[1:])
    elif args[0] == "all":
        await _bd_all(update)
    elif args[0] == "stats":
        await _bd_stats(update)
    elif args[0] == "block":
        await _bd_block(update, args[1:])
    else:
        # Treat everything after /bd as a title for quick add
        await _bd_add(update, args)


async def _bd_ready(update: Update) -> None:
    """List unblocked issues."""
    service = get_beads_service()
    try:
        issues = await service.ready()
    except Exception as e:
        await update.message.reply_text(f"bd error: {e}")
        return

    if not issues:
        await update.message.reply_text("No unblocked issues.")
        return

    lines = ["<b>Ready issues</b>\n"]
    for issue in issues[:15]:
        iid = escape_html(issue.get("id", "?"))
        title = escape_html(issue.get("title", ""))
        pri = _PRIORITY_LABEL.get(issue.get("priority"), "")
        lines.append(f"<code>{iid}</code> {pri} {title}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _bd_add(update: Update, args: list) -> None:
    """Create a new issue from args."""
    if not args:
        await update.message.reply_text(
            "Usage: /bd add <title>\n"
            "Or: /bd add <title> p0|p1|p2|p3\n"
            "Or: /bd add <title> bug|feature|task"
        )
        return

    from ...services.beads_service import get_beads_service

    # Parse priority and type from last args
    priority = 2
    issue_type = "task"
    title_parts = list(args)

    # Check last arg for priority
    if title_parts and title_parts[-1].lower() in ("p0", "p1", "p2", "p3"):
        priority = int(title_parts.pop()[-1])

    # Check last arg for type
    if title_parts and title_parts[-1].lower() in (
        "bug",
        "feature",
        "task",
        "epic",
        "chore",
    ):
        issue_type = title_parts.pop().lower()

    title = " ".join(title_parts)
    if not title:
        await update.message.reply_text("Title required.")
        return

    service = get_beads_service()
    try:
        result = await service.create_issue(
            title, priority=priority, issue_type=issue_type
        )
        iid = result.get("id", "?")
        await update.message.reply_text(
            f"Created <code>{escape_html(iid)}</code>: "
            f"{escape_html(title)}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


async def _bd_done(update: Update, args: list) -> None:
    """Close an issue."""
    if not args:
        await update.message.reply_text("Usage: /bd done <id> [reason]")
        return

    from ...services.beads_service import get_beads_service

    issue_id = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else "Done"

    service = get_beads_service()
    try:
        await service.close(issue_id, reason=reason)
        await update.message.reply_text(
            f"Closed <code>{escape_html(issue_id)}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


async def _bd_show(update: Update, args: list) -> None:
    """Show issue details."""
    if not args:
        await update.message.reply_text("Usage: /bd show <id>")
        return

    service = get_beads_service()
    try:
        issue = await service.show(args[0])
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return

    if not issue:
        await update.message.reply_text("Issue not found.")
        return

    iid = escape_html(issue.get("id", "?"))
    title = escape_html(issue.get("title", ""))
    status = escape_html(issue.get("status", "?"))
    pri = _PRIORITY_LABEL.get(issue.get("priority"), "?")
    desc = escape_html(issue.get("description", ""))
    itype = escape_html(issue.get("type", ""))

    lines = [
        f"<b>{iid}</b> {title}",
        f"Status: {status} | Priority: {pri} | Type: {itype}",
    ]
    if desc:
        lines.append(f"\n{desc}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _bd_all(update: Update) -> None:
    """List all issues."""
    service = get_beads_service()
    try:
        issues = await service.list_issues()
    except Exception as e:
        await update.message.reply_text(f"bd error: {e}")
        return

    if not issues:
        await update.message.reply_text("No issues.")
        return

    lines = ["<b>All issues</b>\n"]
    for issue in issues[:20]:
        iid = escape_html(issue.get("id", "?"))
        title = escape_html(issue.get("title", ""))
        status = issue.get("status", "?")
        pri = _PRIORITY_LABEL.get(issue.get("priority"), "")
        lines.append(f"<code>{iid}</code> [{status}] {pri} {title}")

    if len(issues) > 20:
        lines.append(f"\n... and {len(issues) - 20} more")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _bd_stats(update: Update) -> None:
    """Show project statistics."""
    service = get_beads_service()
    try:
        stats = await service.stats()
    except Exception as e:
        await update.message.reply_text(f"bd error: {e}")
        return

    lines = ["<b>Beads stats</b>\n"]
    for key, val in stats.items():
        lines.append(f"{escape_html(str(key))}: {escape_html(str(val))}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _bd_block(update: Update, args: list) -> None:
    """Add a blocking dependency."""
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /bd block <child> <parent>\n"
            "child is blocked by parent"
        )
        return

    service = get_beads_service()
    try:
        await service.add_dependency(args[0], args[1])
        await update.message.reply_text(
            f"<code>{escape_html(args[0])}</code> blocked by "
            f"<code>{escape_html(args[1])}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


def register_beads_handlers(application) -> None:
    """Register beads command handlers."""
    application.add_handler(CommandHandler("bd", bd_command))
    logger.info("Registered beads command handlers")
