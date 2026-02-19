"""Todo command handlers for Telegram bot.

Provides /todo command for managing tasks in Obsidian vault via TodoService.
"""

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from src.services.todo_service import get_todo_service

logger = logging.getLogger(__name__)

# Callback prefixes
CB_TODO_LIST = "todo_list"
CB_TODO_DONE = "todo_done"
CB_TODO_DETAILS = "todo_details"
CB_TODO_STATUS = "todo_status"


async def todo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main /todo command dispatcher.

    Usage:
        /todo - list active todos
        /todo add <text> - create new todo
        /todo done <id> - mark complete
        /todo list [status] - filter by status
        /todo show <id> - show details
    """
    args = context.args or []

    if not args:
        # Default: list active
        await _todo_list(update, context, status="active")
    elif args[0] == "add":
        await _todo_add(update, context, " ".join(args[1:]))
    elif args[0] == "done":
        await _todo_done(update, context, args[1] if len(args) > 1 else None)
    elif args[0] == "list":
        status = args[1] if len(args) > 1 else "active"
        await _todo_list(update, context, status)
    elif args[0] == "show":
        await _todo_show(update, context, args[1] if len(args) > 1 else None)
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/todo - list active\n"
            "/todo add <text> - create\n"
            "/todo done <id> - complete\n"
            "/todo list [status] - filter\n"
            "/todo show <id> - details"
        )


async def _todo_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status: str = "active",
):
    """List tasks with inline keyboards."""
    service = get_todo_service()

    try:
        tasks = await service.list_tasks(status=status if status != "active" else None)

        if status == "active":
            # Filter to inbox + active
            tasks = [t for t in tasks if t["status"] in ["inbox", "active"]]

        if not tasks:
            await update.message.reply_text(f"📋 No {status} todos")
            return

        text = f"📋 {status.title()} Todos ({len(tasks)})\n\n"
        keyboard = []

        # Store task IDs for action buttons
        task_ids = []

        for idx, task in enumerate(tasks[:10], 1):  # Limit to 10, start from 1
            task_id = task["id"]
            task_ids.append(task_id)

            title = task["title"]
            status_emoji = "📥" if task["status"] == "inbox" else "🔄"

            # Main line: number, emoji, title
            text += f"{idx}. {status_emoji} {title}\n"

            # Optional second line: due date, tags
            if task.get("due"):
                text += f"   📅 Due: {task['due']}\n"
            if task.get("tags"):
                text += f"   🏷 {', '.join(task['tags'])}\n"

        # Add instruction text
        text += "\n💡 Reply with number for details (e.g. '3')\n"

        # Action buttons row
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📥 Inbox", callback_data=f"{CB_TODO_STATUS}:inbox"
                ),
                InlineKeyboardButton(
                    "🔄 Active", callback_data=f"{CB_TODO_STATUS}:active"
                ),
                InlineKeyboardButton(
                    "✅ Completed", callback_data=f"{CB_TODO_STATUS}:completed"
                ),
            ]
        )

        # Send message and track for reply context
        sent_message = await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Track message for numeric reply handling
        from src.services.reply_context import MessageType, get_reply_context_service

        reply_service = get_reply_context_service()
        reply_service.track_message(
            message_id=sent_message.message_id,
            chat_id=sent_message.chat_id,
            user_id=update.effective_user.id,
            message_type=MessageType.TODO_LIST,
            metadata={"task_ids": task_ids, "status": status},
        )

    except Exception as e:
        logger.error(f"Error listing todos: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to list todos")


async def _todo_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    """Create new task."""
    if not text:
        await update.message.reply_text("❌ Usage: /todo add <text>")
        return

    service = get_todo_service()

    try:
        await service.create_task(title=text, source="telegram")
        await update.message.reply_text(f"✅ Created todo: {text}")
    except Exception as e:
        logger.error(f"Error creating todo: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to create todo")


async def _todo_done(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: Optional[str],
):
    """Mark task complete."""
    if not task_id:
        await update.message.reply_text("❌ Usage: /todo done <id>")
        return

    service = get_todo_service()

    try:
        success = await service.complete_task(task_id)

        if success:
            await update.message.reply_text(f"✅ Completed task #{task_id}")
        else:
            await update.message.reply_text(f"❌ Task #{task_id} not found")
    except Exception as e:
        logger.error(f"Error completing todo: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to complete todo")


async def _todo_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: Optional[str],
):
    """Show full task details."""
    if not task_id:
        await update.message.reply_text("❌ Usage: /todo show <id>")
        return

    service = get_todo_service()

    try:
        tasks = await service.list_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)

        if not task:
            await update.message.reply_text(f"❌ Task #{task_id} not found")
            return

        text = f"📋 Task #{task_id}\n\n"
        text += f"**{task['title']}**\n\n"
        text += f"Status: {task['status']}\n"
        text += f"Priority: {task['priority']}\n"
        if task.get("due"):
            text += f"Due: {task['due']}\n"
        if task.get("tags"):
            text += f"Tags: {', '.join(task['tags'])}\n"
        if task.get("context"):
            text += f"\nContext:\n{task['context']}\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error showing todo: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to show todo")


async def handle_todo_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
):
    """Handle todo callback queries.

    Args:
        update: Telegram update
        context: Bot context
        data: Callback data (prefix:value)
    """
    query = update.callback_query
    await query.answer()

    service = get_todo_service()

    try:
        if data.startswith(CB_TODO_DONE):
            task_id = data.split(":", 1)[1]
            success = await service.complete_task(task_id)

            if success:
                await query.message.edit_text(f"✅ Completed task #{task_id}")
            else:
                await query.message.reply_text(f"❌ Failed to complete #{task_id}")

        elif data.startswith(CB_TODO_STATUS):
            status = data.split(":", 1)[1]
            # Re-list with new status
            await _todo_list(update, context, status)

        elif data.startswith(CB_TODO_DETAILS):
            task_id = data.split(":", 1)[1]
            tasks = await service.list_tasks()
            task = next((t for t in tasks if t["id"] == task_id), None)

            if not task:
                await query.message.reply_text(f"❌ Task #{task_id} not found")
                return

            text = f"📋 Task #{task_id}\n\n"
            text += f"**{task['title']}**\n\n"
            text += f"Status: {task['status']}\n"
            text += f"Priority: {task['priority']}\n"
            if task.get("due"):
                text += f"Due: {task['due']}\n"
            if task.get("tags"):
                text += f"Tags: {', '.join(task['tags'])}\n"
            if task.get("context"):
                text += f"\nContext:\n{task['context']}\n"

            await query.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling todo callback {data}: {e}", exc_info=True)
        await query.message.reply_text("❌ Error handling action")


def register_todo_handlers(application):
    """Register todo command handlers.

    Args:
        application: Telegram Application instance

    Note: Callback handlers are routed through callback_handlers.py (todo_ prefix),
    so we only register the command handler here.
    """
    application.add_handler(CommandHandler("todo", todo_command))
    logger.info("Registered todo command handlers")
