import logging
import json
import os
from typing import Optional
from sqlalchemy import select

from telegram import Update
from telegram.ext import ContextTypes

from ..core.config import get_settings
from ..core.database import get_db_session
from ..core.mode_manager import ModeManager
from ..models.user import User
from ..models.chat import Chat
from ..utils.subprocess_helper import run_python_script
from ..utils.completion_reactions import send_completion_reaction
from ..utils.session_emoji import format_session_id, get_session_emoji

logger = logging.getLogger(__name__)


def _run_telegram_api_sync(method: str, payload: dict) -> Optional[dict]:
    """Call Telegram Bot API using secure subprocess (bypasses async blocking)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    try:
        # Secure script - data passed via stdin, token via env var
        script = '''
import sys
import json
import os
import requests

# Read payload from stdin
data = json.load(sys.stdin)
method = data["method"]
payload = data["payload"]

# Get token from environment (not interpolated in script)
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

r = requests.post(
    f"https://api.telegram.org/bot{bot_token}/{method}",
    json=payload,
    timeout=30
)
result = r.json()
if result.get("ok"):
    print(json.dumps({"success": True, "result": result["result"]}))
else:
    print(json.dumps({"success": False, "error": result}))
'''
        result = run_python_script(
            script=script,
            input_data={"method": method, "payload": payload},
            env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
            timeout=60,
        )

        if result.success:
            response = json.loads(result.stdout)
            if response.get("success"):
                return response.get("result")
            else:
                logger.warning(f"Telegram API {method} failed: {response.get('error')}")
                return None
        else:
            logger.warning(f"Telegram API {method} subprocess failed: {result.error}")
            return None
    except Exception as e:
        logger.error(f"Error calling Telegram API {method}: {e}")
        return None


def send_message_sync(chat_id: int, text: str, parse_mode: str = "HTML", reply_to: int = None, reply_markup: dict = None) -> Optional[dict]:
    """Send a message using the Telegram HTTP API via subprocess (bypasses async blocking)."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _run_telegram_api_sync("sendMessage", payload)


def edit_message_sync(chat_id: int, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> Optional[dict]:
    """Edit a message using the Telegram HTTP API via subprocess (bypasses async blocking)."""
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _run_telegram_api_sync("editMessageText", payload)


async def initialize_user_chat(
    user_id: int,
    chat_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> bool:
    """Initialize user and chat in database if they don't exist."""
    try:
        async with get_db_session() as session:
            # Check if user exists
            user_result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                )
                session.add(user)
                await session.flush()  # Get the ID
                logger.info(f"Created new user: {user_id} ({username})")

            # Check if chat exists
            chat_result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_record: Optional[Chat] = chat_result.scalar_one_or_none()

            if not chat_record:
                chat_record = Chat(
                    chat_id=chat_id, user_id=user.id, current_mode="default"
                )
                session.add(chat_record)
                logger.info(f"Created new chat: {chat_id}")

            await session.commit()
            return True

    except Exception as e:
        logger.error(f"Error initializing user/chat: {e}")
        return False


# In-memory cache for Claude mode to avoid database deadlocks during message processing
_claude_mode_cache: dict[int, bool] = {}


async def init_claude_mode_cache() -> None:
    """Initialize Claude mode cache from database on startup."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Chat).where(Chat.claude_mode == True)
            )
            chats = result.scalars().all()
            for chat in chats:
                _claude_mode_cache[chat.chat_id] = True
            logger.info(f"Initialized Claude mode cache with {len(chats)} active chats")
    except Exception as e:
        logger.error(f"Error initializing Claude mode cache: {e}")


async def get_claude_mode(chat_id: int) -> bool:
    """Check if a chat is in Claude mode (locked session)."""
    # First check cache
    if chat_id in _claude_mode_cache:
        return _claude_mode_cache[chat_id]

    # Fall back to database
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_record = result.scalar_one_or_none()
            if chat_record:
                mode = getattr(chat_record, "claude_mode", False)
                _claude_mode_cache[chat_id] = mode
                return mode
            return False
    except Exception as e:
        logger.error(f"Error getting claude_mode: {e}")
        return False


async def set_claude_mode(chat_id: int, enabled: bool) -> bool:
    """Set Claude mode (locked session) for a chat."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_record = result.scalar_one_or_none()
            if chat_record:
                chat_record.claude_mode = enabled
                await session.commit()
                # Update cache
                _claude_mode_cache[chat_id] = enabled
                logger.info(f"Set claude_mode={enabled} for chat {chat_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Error setting claude_mode: {e}")
        return False


async def view_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE, note_name: str) -> None:
    """View a note from the Obsidian vault by name."""
    import os
    from pathlib import Path

    vault_path = Path.home() / "Research" / "vault"

    # Try to find the note (could be in root or subdirectories)
    # First try exact match with .md extension
    note_file = vault_path / f"{note_name}.md"

    if not note_file.exists():
        # Try searching recursively
        try:
            import subprocess
            result = subprocess.run(
                ["find", str(vault_path), "-type", "f", "-name", f"{note_name}.md"],
                capture_output=True,
                text=True,
                timeout=5
            )
            matches = result.stdout.strip().split('\n')
            matches = [m for m in matches if m]  # Remove empty lines

            if matches:
                note_file = Path(matches[0])  # Use first match
            else:
                if update.message:
                    await update.message.reply_text(
                        f"❌ Note not found: {note_name}\n\n"
                        f"The note might not exist in your vault."
                    )
                return
        except Exception as e:
            logger.error(f"Error searching for note: {e}")
            if update.message:
                await update.message.reply_text(
                    f"❌ Error searching for note: {str(e)}"
                )
            return

    # Read the note content
    try:
        with open(note_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Format for Telegram (convert to HTML)
        formatted_content = _markdown_to_telegram_html(content)

        # Split if too long (Telegram limit is 4096 chars)
        max_length = 4000
        if len(formatted_content) > max_length:
            chunks = _split_message(formatted_content, max_length)

            # Send first chunk with note title
            if update.message:
                await update.message.reply_text(
                    f"📄 <b>{note_name}</b>\n\n{chunks[0]}\n\n<i>... continued below ...</i>",
                    parse_mode="HTML"
                )

                # Send remaining chunks
                for i, chunk in enumerate(chunks[1:], 2):
                    is_last = i == len(chunks)
                    if is_last:
                        await update.message.reply_text(
                            chunk,
                            parse_mode="HTML"
                        )
                    else:
                        await update.message.reply_text(
                            chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                            parse_mode="HTML"
                        )
        else:
            # Send as single message
            if update.message:
                await update.message.reply_text(
                    f"📄 <b>{note_name}</b>\n\n{formatted_content}",
                    parse_mode="HTML"
                )

    except Exception as e:
        logger.error(f"Error reading note {note_file}: {e}")
        if update.message:
            await update.message.reply_text(
                f"❌ Error reading note: {str(e)}"
            )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    import urllib.parse

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Start command from user {user.id} in chat {chat.id}")

    # Initialize user and chat in database
    success = await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if not success:
        if update.message:
            await update.message.reply_text(
                "Sorry, there was an error initializing your session. Please try again."
            )
        return

    # Check for deep link parameters (e.g., note_NoteName)
    if context.args and len(context.args) > 0:
        param = context.args[0]
        if param.startswith("note_"):
            # Extract and decode note name
            encoded_name = param[5:]  # Remove "note_" prefix
            note_name = urllib.parse.unquote(encoded_name)
            logger.info(f"Deep link request for note: {note_name}")

            # Read and display the note
            await view_note_command(update, context, note_name)
            return

    welcome_msg = """<b>Personal Knowledge Capture</b>

A bridge between fleeting thoughts and your knowledge system.

<b>What I process:</b>

<b>Links</b> — Send any URL. I fetch the full content, extract the essence, and save it to your Obsidian vault. Smart routing learns your preferences.

<b>Images</b> — Photos are analyzed and classified (screenshot, receipt, document, diagram, photo). Each routes to the appropriate folder. Receipts go to expenses, diagrams to research.

<b>Voice</b> — Speak your thoughts. I transcribe via Whisper, detect intent (task, note, quick thought), and append to your daily notes or inbox.

<b>Text</b> — Prefix with <code>inbox:</code>, <code>research:</code>, or <code>task:</code> to route directly.

Everything flows to your Obsidian vault. The system learns from your corrections.

<i>Send something to begin.</i>"""

    # Get reply keyboard for user
    from ..services.keyboard_service import get_keyboard_service

    keyboard_service = get_keyboard_service()
    reply_keyboard = await keyboard_service.build_reply_keyboard(user.id)

    if update.message:
        await update.message.reply_text(
            welcome_msg, parse_mode="HTML", reply_markup=reply_keyboard
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    user = update.effective_user

    logger.info(f"Help command from user {user.id if user else 'unknown'}")

    help_msg = """<b>Commands</b>

<b>Core:</b>
<code>/start</code> — Welcome message
<code>/help</code> — This help
<code>/mode</code> — Show/change analysis mode
<code>/gallery</code> — Browse uploaded images
<code>/note name</code> — View vault note

<b>Mode Shortcuts:</b>
<code>/analyze</code> — Art critique mode
<code>/coach</code> — Photo coaching
<code>/creative</code> — Creative interpretation
<code>/quick</code> — Quick description
<code>/formal</code> — Structured output
<code>/tags</code> — Tag extraction
<code>/coco</code> — COCO categories

<b>Claude Code:</b>
<code>/claude prompt</code> — Execute prompt
<code>/claude:new</code> — New session
<code>/claude:sessions</code> — List sessions
<code>/claude:lock</code> — Lock mode
<code>/claude:unlock</code> — Unlock
<code>/claude:reset</code> — Reset all
<code>/claude:help</code> — Claude help

<b>Tips:</b>
• Send images for analysis
• Voice notes are transcribed
• Links are captured to vault
• Prefix text with <code>inbox:</code> or <code>task:</code>"""

    if update.message:
        await update.message.reply_text(help_msg, parse_mode="HTML")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mode command"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Mode command from user {user.id} in chat {chat.id}")

    # Parse arguments
    args = context.args
    if not args:
        # Show current mode and available options
        await show_mode_help(update, context)
        return

    # Parse mode and preset
    mode_name = args[0].lower()
    preset_name = args[1] if len(args) > 1 else None

    # Validate mode
    mode_manager = ModeManager()
    available_modes = mode_manager.get_available_modes()

    if mode_name not in available_modes:
        if update.message:
            await update.message.reply_text(
                f"❌ Unknown mode: `{mode_name}`\n\n"
                f"Available modes: {', '.join(available_modes)}\n\n"
                f"Use `/mode` without arguments to see detailed options."
            )
        return

    # Validate preset for modes that require presets
    if mode_name in ["artistic", "formal"]:
        if not preset_name:
            presets = mode_manager.get_mode_presets(mode_name)
            preset_list = "\n".join([f"• `{p}`" for p in presets])
            mode_emoji = "🎨" if mode_name == "artistic" else "📋"
            if update.message:
                await update.message.reply_text(
                    f"{mode_emoji} {mode_name.title()} mode requires a preset:\n\n{preset_list}\n\n"
                    f"Example: `/mode {mode_name} {presets[0]}`"
                )
            return

        if not mode_manager.is_valid_preset(mode_name, preset_name):
            presets = mode_manager.get_mode_presets(mode_name)
            if update.message:
                await update.message.reply_text(
                    f"❌ Unknown preset: `{preset_name}`\n\n"
                    f"Available presets: {', '.join(presets)}"
                )
            return

    # Update mode in database
    try:
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_record = result.scalar_one_or_none()

            if not chat_record:
                await initialize_user_chat(user.id, chat.id, user.username)
                result = await session.execute(
                    select(Chat).where(Chat.chat_id == chat.id)
                )
                chat_record = result.scalar_one_or_none()

            if chat_record:
                chat_record.current_mode = mode_name
                chat_record.current_preset = preset_name
                await session.commit()

                # Success message
                if mode_name == "default":
                    if update.message:
                        await update.message.reply_text(
                            "✅ <b>Mode switched to Default</b>\n\n"
                            "📝 Quick descriptions (≤40 words)\n"
                            "📄 Text extraction from images\n"
                            "⚡ Fast processing, no similarity search",
                            parse_mode="HTML",
                        )
                elif mode_name == "formal":
                    if preset_name and update.message:
                        preset_info = mode_manager.get_preset_info(
                            "formal", preset_name
                        )
                        if preset_info:
                            await update.message.reply_text(
                                f"✅ <b>Mode switched to Formal - {preset_name}</b>\n\n"
                                f"📋 <b>Description:</b> {preset_info.get('description', 'Structured analysis')}\n"
                                f"📊 Detailed analysis with object detection\n"
                                f"🔍 Similar image search enabled\n"
                                f"🎯 Vector embeddings for smart matching",
                                parse_mode="HTML",
                            )
                else:  # artistic
                    if preset_name and update.message:
                        preset_info = mode_manager.get_preset_info(
                            "artistic", preset_name
                        )
                        if preset_info:
                            await update.message.reply_text(
                                f"✅ <b>Mode switched to Artistic - {preset_name}</b>\n\n"
                                f"📋 <b>Description:</b> {preset_info.get('description', 'Advanced analysis')}\n"
                                f"📝 Detailed analysis (100-150 words)\n"
                                f"🔍 Similar image search enabled\n"
                                f"🎨 Vector embeddings for smart matching",
                                parse_mode="HTML",
                            )
            else:
                if update.message:
                    await update.message.reply_text(
                        "❌ Error updating mode. Please try again."
                    )

    except Exception as e:
        logger.error(f"Error updating mode for chat {chat.id}: {e}")
        if update.message:
            await update.message.reply_text("❌ Error updating mode. Please try again.")


async def show_mode_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current mode and available options"""
    chat = update.effective_chat

    if not chat:
        return

    try:
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_record = result.scalar_one_or_none()
            current_mode = chat_record.current_mode if chat_record else "default"
            current_preset = chat_record.current_preset if chat_record else None

        # Get mode manager for detailed info
        mode_manager = ModeManager()

        # Current mode info with HTML formatting
        if current_mode == "default":
            current_info = "📝 <b>Current Mode:</b> Default (quick descriptions)"
        elif current_mode == "formal":
            current_info = (
                f"📋 <b>Current Mode:</b> Formal - {current_preset or 'Structured'}"
            )
        else:  # artistic
            current_info = (
                f"🎨 <b>Current Mode:</b> Artistic - {current_preset or 'Critic'}"
            )

        # Available modes with HTML formatting
        modes_info = """
📋 <b>Available Modes:</b>

🔧 <b>Default Mode:</b>
• Command: <code>/mode default</code>
• Quick descriptions (≤40 words)
• Text extraction from images
• Fast processing

📋 <b>Formal Mode:</b>
• <code>/mode formal Structured</code> - Structured YAML output
• <code>/mode formal Tags</code> - Hierarchical tags & entities  
• <code>/mode formal COCO</code> - COCO dataset categories
• Detailed analysis with object detection
• Vector embeddings for similarity search

🎨 <b>Artistic Mode:</b>
• <code>/mode artistic Critic</code> - Art & composition analysis
• <code>/mode artistic Photo-coach</code> - Photography tips
• <code>/mode artistic Creative</code> - Creative interpretation
• Detailed analysis (100-150 words)
• Vector embeddings for similarity search

🚀 <b>Quick Commands:</b>
• <code>/analyze</code> = Artistic Critic
• <code>/coach</code> = Artistic Photo-coach
• <code>/creative</code> = Artistic Creative
• <code>/quick</code> = Default
• <code>/formal</code> = Formal Structured
• <code>/tags</code> = Formal Tags
• <code>/coco</code> = Formal COCO

<b>Example:</b> <code>/mode artistic Critic</code>"""

        # Create comprehensive keyboard showing ALL modes
        from .keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        reply_markup = keyboard_utils.create_comprehensive_mode_keyboard(
            current_mode, current_preset
        )

        response_text = f"{current_info}\n{modes_info}"

        # Always add keyboard with all mode options
        if update.message:
            response_text += "\n\n💡 <i>Use the buttons below to switch modes:</i>"
            await update.message.reply_text(
                response_text, parse_mode="HTML", reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Error showing mode help: {e}")
        if update.message:
            await update.message.reply_text("❌ Error getting mode information.")


# Command aliases
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode artistic Critic"""
    context.args = ["artistic", "Critic"]
    await mode_command(update, context)


async def coach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode artistic Photo-coach"""
    context.args = ["artistic", "Photo-coach"]
    await mode_command(update, context)


async def creative_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode artistic Creative"""
    context.args = ["artistic", "Creative"]
    await mode_command(update, context)


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode default"""
    context.args = ["default"]
    await mode_command(update, context)


async def formal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode formal Structured"""
    context.args = ["formal", "Structured"]
    await mode_command(update, context)


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode formal Tags"""
    context.args = ["formal", "Tags"]
    await mode_command(update, context)


async def coco_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /mode formal COCO"""
    context.args = ["formal", "COCO"]
    await mode_command(update, context)


async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gallery command"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Gallery command from user {user.id} in chat {chat.id}")

    # Parse page number from arguments (default to page 1)
    page = 1
    if context.args:
        try:
            page = max(1, int(context.args[0]))
        except (ValueError, IndexError):
            page = 1

    # Initialize user and chat if needed
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Get gallery service
    from ..services.gallery_service import get_gallery_service

    gallery_service = get_gallery_service()

    try:
        # Get paginated images
        images, total_images, total_pages = (
            await gallery_service.get_user_images_paginated(user_id=user.id, page=page)
        )

        # Format response
        response_text = gallery_service.format_gallery_page(
            images=images, page=page, total_pages=total_pages, total_images=total_images
        )

        # Create navigation keyboard
        from .keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        reply_markup = keyboard_utils.create_gallery_navigation_keyboard(
            images=images, page=page, total_pages=total_pages
        )

        if update.message:
            await update.message.reply_text(
                response_text, parse_mode="HTML", reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Error in gallery command: {e}")
        if update.message:
            await update.message.reply_text(
                "❌ Sorry, there was an error loading your gallery. Please try again later."
            )


# Claude Code commands - unified with :subcommand syntax
# Supported: /claude, /claude:new, /claude:reset, /claude:lock, /claude:unlock, /claude:sessions

async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude command with :subcommand syntax.

    Subcommands:
        /claude:new [prompt]   - Start new session
        /claude:reset          - Reset session and kill stuck processes
        /claude:lock           - Lock mode (all messages go to Claude)
        /claude:unlock         - Unlock mode
        /claude:sessions       - List all sessions
        /claude [prompt]       - Execute prompt (or show status if no prompt)
    """
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # Parse :subcommand from raw message text
    raw_text = update.message.text if update.message else ""
    subcommand = None
    remaining_text = ""

    # Check for /claude:subcommand pattern
    if raw_text.startswith("/claude:"):
        # Extract subcommand and remaining text
        after_claude = raw_text[8:]  # After "/claude:"
        parts = after_claude.split(None, 1)  # Split on first whitespace
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        # Regular /claude with args
        remaining_text = " ".join(context.args) if context.args else ""

    logger.info(f"Claude command from user {user.id}: subcommand={subcommand}, text_len={len(remaining_text)}")

    # Check if user is admin
    from ..services.claude_code_service import (
        get_claude_code_service,
        is_claude_code_admin,
    )

    if not await is_claude_code_admin(chat.id):
        if update.message:
            await update.message.reply_text(
                "You don't have permission to use Claude Code."
            )
        return

    # Route to subcommand handlers
    if subcommand == "new":
        await _claude_new(update, context, remaining_text)
        return
    elif subcommand == "reset":
        await _claude_reset(update, context)
        return
    elif subcommand == "lock":
        await _claude_lock(update, context)
        return
    elif subcommand == "unlock":
        await _claude_unlock(update, context)
        return
    elif subcommand == "sessions":
        await _claude_sessions(update, context)
        return
    elif subcommand == "help":
        await _claude_help(update, context)
        return
    elif subcommand:
        # Unknown subcommand - show help
        if update.message:
            await update.message.reply_text(
                f"Unknown subcommand: <code>:{subcommand}</code>\n\n"
                "Use <code>/claude:help</code> for available commands.",
                parse_mode="HTML",
            )
        return

    # Initialize user and chat if needed
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Get prompt from remaining text
    prompt = remaining_text.strip() if remaining_text else None

    if not prompt:
        # Show help and session options
        service = get_claude_code_service()
        active_session_id = await service.get_active_session(chat.id)

        # Get session details if active
        last_prompt = None
        if active_session_id:
            sessions = await service.get_user_sessions(chat.id, limit=1)
            if sessions:
                last_prompt = sessions[0].last_prompt

        # Check if locked mode is active
        is_locked = await get_claude_mode(chat.id)

        from .keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        reply_markup = keyboard_utils.create_claude_action_keyboard(
            has_active_session=bool(active_session_id),
            is_locked=is_locked,
        )

        if active_session_id:
            session_display = format_session_id(active_session_id)
            prompt_preview = (last_prompt or "No prompt")[:40]
            lock_status = "🔒 Locked" if is_locked else "🔓 Unlocked"
            status_text = (
                f"<b>🤖 Claude Code</b>\n\n"
                f"▶️ Session: <code>{session_display}</code>\n"
                f"Last: <i>{prompt_preview}...</i>\n"
                f"Mode: {lock_status}\n\n"
                f"{'Send any message to continue' if is_locked else 'Send prompt to continue, or:'}"
            )
        else:
            status_text = (
                f"<b>🤖 Claude Code</b>\n\n"
                f"No active session\n"
                f"Work dir: <code>~/Research/vault</code>\n\n"
                f"Send a prompt or tap below:"
            )

        if update.message:
            await update.message.reply_text(
                status_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        return

    # Buffer the prompt to wait for potential follow-up messages
    # This allows users to send multi-part prompts that get combined
    from ..services.message_buffer import get_message_buffer

    buffer = get_message_buffer()
    await buffer.add_claude_command(update, context, prompt)

    logger.info(
        f"Buffered /claude prompt for chat {chat.id}, "
        f"waiting for potential follow-up messages"
    )


async def _claude_new(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str = ""
) -> None:
    """Handle /claude:new - start a new Claude Code session."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude new session for chat {chat.id}")

    from ..services.claude_code_service import get_claude_code_service

    # End current session
    service = get_claude_code_service()
    await service.end_session(chat.id)

    if prompt.strip():
        await execute_claude_prompt(update, context, prompt.strip(), force_new=True)
    else:
        if update.message:
            await update.message.reply_text(
                "✨ New session ready.\n\n"
                "Send: <code>/claude your prompt</code>",
                parse_mode="HTML",
            )


async def _claude_sessions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /claude:sessions - list and manage sessions."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude sessions for chat {chat.id}")

    from ..services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()
    sessions = await service.get_user_sessions(chat.id)
    active_session = await service.get_active_session(chat.id)

    if not sessions:
        if update.message:
            await update.message.reply_text(
                "No sessions found.\n\n"
                "Start with: <code>/claude your prompt</code>",
                parse_mode="HTML",
            )
        return

    from .keyboard_utils import get_keyboard_utils

    keyboard_utils = get_keyboard_utils()
    reply_markup = keyboard_utils.create_claude_sessions_keyboard(
        sessions, active_session
    )

    if update.message:
        await update.message.reply_text(
            f"<b>Sessions</b> ({len(sessions)})\n\n"
            f"Select to resume:",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /note command - view a note from the vault."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Note command from user {user.id} in chat {chat.id}")

    # Get note name from arguments
    if not context.args:
        if update.message:
            await update.message.reply_text(
                "Usage: <code>/note note name</code>\n\n"
                "Example: <code>/note Claude Code</code>",
                parse_mode="HTML",
            )
        return

    note_name = " ".join(context.args)
    await view_note_command(update, context, note_name)


async def _claude_reset(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /claude:reset - reset session and kill stuck processes."""
    import subprocess

    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude reset for chat {chat.id}")

    from ..services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()

    # End current session
    session_ended = await service.end_session(chat.id)

    # Also disable lock mode
    await set_claude_mode(chat.id, False)

    # Kill any stuck Claude processes
    killed_processes = 0
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*--resume"],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                try:
                    subprocess.run(["kill", pid], capture_output=True)
                    killed_processes += 1
                    logger.info(f"Killed stuck Claude process: {pid}")
                except Exception as e:
                    logger.warning(f"Failed to kill process {pid}: {e}")
    except Exception as e:
        logger.warning(f"Error checking for stuck processes: {e}")

    # Build response
    status_parts = []
    if session_ended:
        status_parts.append("Session cleared")
    else:
        status_parts.append("No active session")

    if killed_processes > 0:
        status_parts.append(f"{killed_processes} process(es) killed")

    if update.message:
        await update.message.reply_text(
            f"🔄 <b>Reset</b>\n\n• " + "\n• ".join(status_parts),
            parse_mode="HTML",
        )


async def _claude_lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:lock - enable locked mode."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude lock for chat {chat.id}")

    from ..services.claude_code_service import get_claude_code_service

    # Check if there's an active session
    service = get_claude_code_service()
    session_id = await service.get_active_session(chat.id)

    if not session_id:
        if update.message:
            await update.message.reply_text(
                "No active session.\n\n"
                "Start with: <code>/claude your prompt</code>",
                parse_mode="HTML",
            )
        return

    await set_claude_mode(chat.id, True)

    from .keyboard_utils import get_keyboard_utils
    keyboard_utils = get_keyboard_utils()

    if update.message:
        session_display = format_session_id(session_id)
        await update.message.reply_text(
            f"🔒 <b>Locked</b>\n\n"
            f"Session: <code>{session_display}</code>\n\n"
            "All messages → Claude\n\n"
            "<code>/claude:unlock</code> to exit",
            parse_mode="HTML",
            reply_markup=keyboard_utils.create_claude_locked_keyboard(),
        )
    logger.info(f"Claude mode locked for chat {chat.id}")


async def _claude_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:unlock - disable locked mode."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude unlock for chat {chat.id}")

    await set_claude_mode(chat.id, False)

    if update.message:
        await update.message.reply_text(
            "🔓 <b>Unlocked</b>\n\n"
            "Normal mode restored.",
            parse_mode="HTML",
        )
    logger.info(f"Claude mode unlocked for chat {chat.id}")


async def _claude_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:help - show Claude command help."""
    if update.message:
        await update.message.reply_text(
            "<b>Claude Commands</b>\n\n"
            "<code>/claude prompt</code> — Execute prompt\n"
            "<code>/claude:new prompt</code> — New session\n"
            "<code>/claude:sessions</code> — List sessions\n"
            "<code>/claude:lock</code> — Lock mode (all → Claude)\n"
            "<code>/claude:unlock</code> — Unlock mode\n"
            "<code>/claude:reset</code> — Reset & kill stuck\n"
            "<code>/claude:help</code> — This help\n\n"
            "<i>Work dir: ~/Research/vault</i>",
            parse_mode="HTML",
        )


# ============================================================================
# Collect Mode Commands - batch input accumulation
# ============================================================================


async def collect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect command with :subcommand syntax.

    Usage:
        /collect:start - Start collecting items
        /collect:go [prompt] - Process collected items with Claude
        /collect:stop - Stop collecting without processing
        /collect:status - Show what's been collected
    """
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    # Parse :subcommand from raw message text
    raw_text = update.message.text or ""
    subcommand = None
    remaining_text = ""

    # Check for /collect:subcommand pattern
    if raw_text.startswith("/collect:"):
        after_collect = raw_text[9:]  # After "/collect:"
        parts = after_collect.split(None, 1)  # Split on first whitespace
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        # Regular /collect - show help
        remaining_text = " ".join(context.args) if context.args else ""

    logger.info(
        f"Collect command from user {user.id}: subcommand={subcommand}, "
        f"text_len={len(remaining_text)}"
    )

    # Check if user is admin (same as Claude)
    from ..services.claude_code_service import is_claude_code_admin

    if not await is_claude_code_admin(chat.id):
        await update.message.reply_text(
            "You don't have permission to use collect mode."
        )
        return

    # Route to subcommand handlers
    if subcommand == "start" or subcommand == "on":
        await _collect_start(update, context)
    elif subcommand == "go":
        await _collect_go(update, context, remaining_text)
    elif subcommand == "stop" or subcommand == "off":
        await _collect_stop(update, context)
    elif subcommand == "status" or subcommand == "?":
        await _collect_status(update, context)
    elif subcommand == "clear" or subcommand == "x":
        await _collect_clear(update, context)
    elif subcommand == "help":
        await _collect_help(update, context)
    elif subcommand is None:
        # No subcommand - show help
        await _collect_help(update, context)
    else:
        await update.message.reply_text(
            f"Unknown collect subcommand: <code>{subcommand}</code>\n"
            "Use <code>/collect:help</code> for available commands.",
            parse_mode="HTML",
        )


async def _collect_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /collect:start - begin collecting items."""
    from ..services.collect_service import get_collect_service
    from ..services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    service = get_collect_service()
    await service.start_session(chat.id, user.id)

    # Get collect mode keyboard
    keyboard_service = get_keyboard_service()
    collect_keyboard = keyboard_service.build_collect_keyboard()

    await update.message.reply_text(
        "📥 <b>Collect mode ON</b>\n\n"
        "Send files, voice, images, text — I'll collect them silently.\n\n"
        "When ready, tap <b>▶️ Go</b> or say <i>\"now respond\"</i>",
        parse_mode="HTML",
        reply_markup=collect_keyboard,
    )


async def _collect_go(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str = ""
) -> None:
    """Handle /collect:go - process collected items with Claude."""
    from ..services.collect_service import get_collect_service, CollectItemType
    from ..services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        logger.warning("_collect_go: Missing chat or user")
        return

    message = update.message or update.effective_message
    if not message:
        logger.warning("_collect_go: Missing message, cannot proceed")
        return

    service = get_collect_service()
    session = await service.end_session(chat.id)

    # Restore normal keyboard immediately
    keyboard_service = get_keyboard_service()
    normal_keyboard = await keyboard_service.build_reply_keyboard(user.id)

    if not session or not session.items:
        await message.reply_text(
            "📭 Nothing collected. Use <code>/collect:start</code> first.",
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )
        return

    # Build combined prompt from collected items
    combined_parts = []

    # Add user prompt if provided
    if prompt:
        combined_parts.append(f"User request: {prompt}\n")

    combined_parts.append(f"Collected {session.item_count} items:\n")

    # Process each collected item
    images = []
    voices = []
    documents = []
    texts = []

    for item in session.items:
        if item.type == CollectItemType.TEXT:
            texts.append(item.content)
        elif item.type == CollectItemType.IMAGE:
            images.append(item.content)  # file_id
            if item.caption:
                texts.append(f"[Image caption: {item.caption}]")
        elif item.type == CollectItemType.VOICE:
            voices.append(item.content)  # file_id
            # Include transcription in text if available
            if item.transcription:
                texts.append(f"[Voice message transcription]: {item.transcription}")
        elif item.type == CollectItemType.DOCUMENT:
            documents.append((item.content, item.file_name))
            if item.caption:
                texts.append(f"[Document '{item.file_name}' caption: {item.caption}]")
        elif item.type == CollectItemType.VIDEO:
            # For now, treat like document
            documents.append((item.content, item.file_name or "video"))
            # Include transcription if available
            if item.transcription:
                texts.append(f"[Video transcription]: {item.transcription}")
        elif item.type == CollectItemType.VIDEO_NOTE:
            voices.append(item.content)  # Treat like voice
            # Include transcription if available
            if item.transcription:
                texts.append(f"[Video note transcription]: {item.transcription}")

    # Add text content
    if texts:
        combined_parts.append("\n--- Text content ---\n")
        combined_parts.extend(texts)

    # Summary of media
    if images:
        combined_parts.append(f"\n[{len(images)} images attached]")
    if voices:
        combined_parts.append(f"\n[{len(voices)} voice messages to transcribe]")
    if documents:
        combined_parts.append(f"\n[{len(documents)} documents attached]")

    full_prompt = "\n".join(combined_parts)

    # Store collected files in context for processing
    if hasattr(context, 'user_data') and context.user_data is not None:
        context.user_data["collected_images"] = images
        context.user_data["collected_voices"] = voices
        context.user_data["collected_documents"] = documents

    logger.info(
        f"Processing collected items for chat {chat.id}: "
        f"{len(images)} images, {len(voices)} voices, {len(documents)} docs, "
        f"{len(texts)} texts"
    )

    # Send status
    await message.reply_text(
        f"🚀 Processing {session.summary_text()}...",
        parse_mode="HTML",
    )

    # Execute with Claude (uses existing session if in claude mode)
    logger.info(f"Calling execute_claude_prompt with prompt length: {len(full_prompt)}")
    await execute_claude_prompt(update, context, full_prompt)
    logger.info("execute_claude_prompt completed for collect_go")


async def _collect_stop(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /collect:stop - cancel collecting without processing."""
    from ..services.collect_service import get_collect_service
    from ..services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not update.message:
        return

    service = get_collect_service()
    session = await service.end_session(chat.id)

    # Restore normal keyboard
    keyboard_service = get_keyboard_service()
    normal_keyboard = await keyboard_service.build_reply_keyboard(user.id if user else 0)

    if session:
        await update.message.reply_text(
            f"🚫 Collect mode OFF. Discarded {session.summary_text()}.",
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )
    else:
        await update.message.reply_text(
            "Not in collect mode.",
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )


async def _collect_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /collect:status - show what's been collected."""
    from ..services.collect_service import get_collect_service

    chat = update.effective_chat

    if not chat or not update.message:
        return

    service = get_collect_service()
    status = await service.get_status(chat.id)

    if not status:
        await update.message.reply_text(
            "Not in collect mode. Use <code>/collect:start</code>",
            parse_mode="HTML",
        )
        return

    age_mins = int(status["age_seconds"] / 60)
    await update.message.reply_text(
        f"📦 <b>Collect Queue</b>\n\n"
        f"Items: {status['summary_text'] or 'empty'}\n"
        f"Age: {age_mins} min\n\n"
        f"<code>/collect:go</code> to process\n"
        f"<code>/collect:clear</code> to empty queue",
        parse_mode="HTML",
    )


async def _collect_clear(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /collect:clear - clear queue but stay in collect mode."""
    from ..services.collect_service import get_collect_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    service = get_collect_service()
    old_session = await service.end_session(chat.id)

    if old_session:
        # Start fresh session
        await service.start_session(chat.id, user.id)
        await update.message.reply_text(
            f"🗑 Cleared {old_session.summary_text()}. Still collecting.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "Not in collect mode.",
            parse_mode="HTML",
        )


async def _collect_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /collect:help - show collect command help."""
    if update.message:
        await update.message.reply_text(
            "<b>Collect Mode</b>\n\n"
            "Batch input — send multiple items, process together.\n\n"
            "<code>/collect:start</code> — Begin collecting\n"
            "<code>/collect:go</code> — Process all with Claude\n"
            "<code>/collect:go prompt</code> — Process with prompt\n"
            "<code>/collect:status</code> — Show queue\n"
            "<code>/collect:clear</code> — Empty queue\n"
            "<code>/collect:stop</code> — Cancel\n\n"
            "<i>Trigger words: \"now respond\", \"process this\"</i>",
            parse_mode="HTML",
        )


async def execute_claude_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    force_new: bool = False,
) -> None:
    """Execute a Claude Code prompt with streaming output."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    from ..services.claude_code_service import get_claude_code_service
    from ..services.reply_context import get_reply_context_service
    from .keyboard_utils import get_keyboard_utils

    service = get_claude_code_service()
    reply_context_service = get_reply_context_service()
    keyboard_utils = get_keyboard_utils()

    # Check for forced session ID from reply context
    forced_session = context.user_data.pop("force_session_id", None)

    # Get or skip active session
    if forced_session:
        session_id = forced_session
        logger.info(f"Using forced session from reply: {format_session_id(session_id)}")
    elif force_new:
        session_id = None
    else:
        # Use in-memory cache only to avoid database deadlocks during buffer processing
        session_id = service.active_sessions.get(chat.id)

    # Store prompt for retry functionality
    context.user_data["last_claude_prompt"] = prompt

    # Send initial message with processing keyboard
    if not update.message:
        return

    # Use defaults to avoid database deadlocks during buffer processing
    selected_model = "sonnet"
    user_db_id = user.id

    logger.info(f"Using Claude model: {selected_model} for chat {chat.id}")

    # Model display emojis
    model_emoji = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}.get(selected_model, "🤖")

    # Show detailed processing status
    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_status = f"Resuming {format_session_id(session_id)}" if session_id else "New session"

    # Use sync subprocess to bypass async blocking issues
    logger.info(f"Sending status message via sync subprocess...")
    status_text = (
        f"<b>🤖 Claude Code</b> {model_emoji} <i>{selected_model.title()}</i>\n\n"
        f"<i>{_escape_html(prompt_preview)}</i>\n\n"
        f"⏳ {session_status}\n"
        f"📂 ~/Research/vault"
    )

    # Create processing keyboard with stop button
    from .keyboard_utils import KeyboardUtils
    kb = KeyboardUtils()
    processing_keyboard = kb.create_claude_processing_keyboard()

    result = send_message_sync(
        chat_id=chat.id,
        text=status_text,
        parse_mode="HTML",
        reply_to=update.message.message_id if update.message else None,
        reply_markup=processing_keyboard.to_dict(),
    )

    if not result:
        logger.error("Failed to send Claude status message via sync")
        return

    status_msg_id = result.get("message_id")
    logger.info(f"Status message sent via sync: message_id={status_msg_id}")

    # Store message ID and stop flag for stop functionality
    context.user_data["claude_status_msg_id"] = status_msg_id
    context.user_data["claude_stop_requested"] = False

    # Collect output for streaming
    accumulated_text = ""
    current_tool = ""  # Current tool being used (shown in status, not accumulated)
    last_update_time = 0
    update_interval = 1.0  # Update every 1 second
    new_session_id = None

    import time

    try:
        logger.info(f"Starting Claude execution loop...")
        message_count = 0

        # Create stop check function
        def check_stop():
            return context.user_data.get("claude_stop_requested", False)

        async for msg_type, content, sid in service.execute_prompt(
            prompt=prompt,
            chat_id=chat.id,
            user_id=user_db_id,
            session_id=session_id,
            model=selected_model,
            stop_check=check_stop,
        ):
            # Check if stop was requested
            if context.user_data.get("claude_stop_requested", False):
                logger.info("Stop requested by user, breaking execution loop")
                accumulated_text += "\n\n⏹️ **Stopped by user**"
                break

            message_count += 1
            logger.info(f"Received message {message_count}: type={msg_type}, content_len={len(content) if content else 0}")
            if sid:
                new_session_id = sid

            if msg_type == "text":
                accumulated_text += content
                current_tool = ""  # Clear tool when text arrives
            elif msg_type == "tool":
                current_tool = content  # Update current tool (don't accumulate)
            elif msg_type in ("done", "error"):
                if msg_type == "error":
                    accumulated_text += content
                continue

            # Throttle message updates
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                # Show last portion of text during streaming
                display_text = accumulated_text[-3200:] if len(accumulated_text) > 3200 else accumulated_text
                if len(accumulated_text) > 3200:
                    display_text = "...\n" + display_text

                # Keep prompt visible at top
                prompt_header = f"<b>→</b> <i>{_escape_html(prompt[:80])}{'...' if len(prompt) > 80 else ''}</i>\n\n"

                # Add current tool status at the bottom
                tool_status = f"\n\n<i>{_escape_html(current_tool)}</i>" if current_tool else ""

                try:
                    edit_message_sync(
                        chat_id=chat.id,
                        message_id=status_msg_id,
                        text=prompt_header + _markdown_to_telegram_html(display_text) + tool_status,
                        parse_mode="HTML",
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Failed to update message: {e}")

        # Final update - split long messages instead of truncating
        session_info = f"\n\n<i>Session: {format_session_id(new_session_id)}</i>" if new_session_id else ""

        # Keep prompt visible at top
        prompt_header = f"<b>→</b> <i>{_escape_html(prompt[:100])}{'...' if len(prompt) > 100 else ''}</i>\n\n"

        # Check if locked mode is active
        is_locked = await get_claude_mode(chat.id)
        complete_keyboard = keyboard_utils.create_claude_complete_keyboard(
            is_locked=is_locked, current_model=selected_model
        )

        # Convert keyboard to dict format for API
        keyboard_dict = complete_keyboard.to_dict() if complete_keyboard else None

        # Split into chunks of ~3600 chars (leaving room for header + HTML formatting)
        max_chunk_size = 3600
        full_html = _markdown_to_telegram_html(accumulated_text)

        if len(full_html) + len(prompt_header) <= max_chunk_size:
            # Single message - fits in one
            edit_message_sync(
                chat_id=chat.id,
                message_id=status_msg_id,
                text=prompt_header + full_html + session_info,
                parse_mode="HTML",
                reply_markup=keyboard_dict,
            )
        else:
            # Multiple messages needed - split by paragraphs or newlines
            chunks = _split_message(full_html, max_chunk_size)

            # First chunk includes prompt header (no keyboard here)
            edit_message_sync(
                chat_id=chat.id,
                message_id=status_msg_id,
                text=prompt_header + chunks[0] + "\n\n<i>... continued below ...</i>",
                parse_mode="HTML",
            )

            # Send remaining chunks as new messages
            for i, chunk in enumerate(chunks[1:], 2):
                is_last = i == len(chunks)
                if is_last:
                    # Add keyboard to last message
                    send_message_sync(
                        chat_id=chat.id,
                        text=chunk + session_info,
                        parse_mode="HTML",
                        reply_markup=keyboard_dict,
                    )
                else:
                    send_message_sync(
                        chat_id=chat.id,
                        text=chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                        parse_mode="HTML",
                    )

        # Check for generated files to send
        logger.info(f"Checking for files in output ({len(accumulated_text)} chars): {repr(accumulated_text[:200])}")
        files_to_send = _extract_file_paths(accumulated_text)
        logger.info(f"Found {len(files_to_send)} files to send: {files_to_send}")
        if files_to_send:
            await _send_files(update.message, files_to_send)

        # Send completion reaction (sticker/emoji/gif)
        try:
            await send_completion_reaction(
                bot=context.bot,
                chat_id=chat.id,
                reply_to_message_id=status_msg_id,
            )
        except Exception as e:
            logger.warning(f"Failed to send completion reaction: {e}")

        # Track this response for reply context (enables reply-to-continue)
        if new_session_id:
            reply_context_service.track_claude_response(
                message_id=status_msg_id,
                chat_id=chat.id,
                user_id=user.id,
                session_id=new_session_id,
                prompt=prompt,
                response_text=accumulated_text[:1000],  # Store first 1000 chars
            )
            logger.debug(f"Tracked Claude response for reply context: msg={status_msg_id}")

    except Exception as e:
        logger.error(f"Error executing Claude prompt: {e}")
        edit_message_sync(
            chat_id=chat.id,
            message_id=status_msg_id,
            text=f"❌ Error: {str(e)}",
            parse_mode="HTML",
        )


def _extract_file_paths(text: str) -> list[str]:
    """Extract file paths from Claude output that should be sent to user."""
    import re
    import os

    # File extensions we should send
    sendable_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.mp3', '.mp4',
                          '.wav', '.doc', '.docx', '.xlsx', '.csv', '.zip', '.tar', '.gz'}

    # Strip markdown formatting that might wrap paths (backticks, bold, etc.)
    # Remove backticks but keep content
    clean_text = re.sub(r'`([^`]+)`', r'\1', text)

    # Patterns to find file paths
    # Look for absolute paths or paths starting with ~/
    path_pattern = r'(?:/[^\s<>"|*?`]+|~/[^\s<>"|*?`]+)'

    found_paths = []
    for match in re.finditer(path_pattern, clean_text):
        path = match.group(0)
        # Clean any trailing punctuation
        path = path.rstrip('.,;:!?)')
        # Expand ~ to home directory
        expanded_path = os.path.expanduser(path)

        # Check if file exists and has sendable extension
        ext = os.path.splitext(expanded_path)[1].lower()
        if ext in sendable_extensions and os.path.isfile(expanded_path):
            found_paths.append(expanded_path)

    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for p in found_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    return unique_paths


async def _send_files(message, file_paths: list[str]) -> None:
    """Send files to the user via Telegram."""
    import os

    for file_path in file_paths:
        try:
            filename = os.path.basename(file_path)
            ext = os.path.splitext(file_path)[1].lower()

            with open(file_path, 'rb') as f:
                if ext in {'.png', '.jpg', '.jpeg', '.gif'}:
                    await message.reply_photo(
                        photo=f,
                        caption=f"📎 {filename}"
                    )
                elif ext in {'.mp3', '.wav', '.ogg'}:
                    await message.reply_audio(
                        audio=f,
                        caption=f"🎵 {filename}"
                    )
                elif ext in {'.mp4', '.mov', '.avi'}:
                    await message.reply_video(
                        video=f,
                        caption=f"🎬 {filename}"
                    )
                else:
                    await message.reply_document(
                        document=f,
                        caption=f"📄 {filename}"
                    )
            logger.info(f"Sent file to user: {filename}")

        except Exception as e:
            logger.error(f"Failed to send file {file_path}: {e}")
            await message.reply_text(f"❌ Failed to send file: {os.path.basename(file_path)}")


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _split_message(text: str, max_size: int = 3800) -> list[str]:
    """Split a long message into chunks, trying to break at natural boundaries."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_size:
            chunks.append(remaining)
            break

        # Try to find a good break point (paragraph, newline, or space)
        chunk = remaining[:max_size]

        # Look for paragraph break (double newline)
        break_point = chunk.rfind("\n\n")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 2:]
            continue

        # Look for single newline
        break_point = chunk.rfind("\n")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1:]
            continue

        # Look for space
        break_point = chunk.rfind(" ")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1:]
            continue

        # No good break point, just cut at max_size
        chunks.append(remaining[:max_size])
        remaining = remaining[max_size:]

    return chunks


def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-compatible HTML."""
    import re
    import uuid

    # Generate unique placeholder prefix
    placeholder = f"CODEBLOCK{uuid.uuid4().hex[:8]}"

    # First escape HTML entities
    text = _escape_html(text)

    # Process code blocks first (```code```) - preserve them
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    text = re.sub(r'```(?:\w+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Detect and convert markdown tables to ASCII tables using tabulate
    def convert_table(match):
        try:
            from tabulate import tabulate
            table_text = match.group(0)
            lines = [l.strip() for l in table_text.strip().split('\n') if l.strip()]

            # Parse markdown table
            rows = []
            for line in lines:
                # Skip separator lines (|---|---|)
                if re.match(r'^\|[\s\-:]+\|$', line):
                    continue
                # Split by | and clean up
                cells = [c.strip() for c in line.split('|')]
                # Remove empty first/last from leading/trailing |
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)

            if len(rows) >= 1:
                # First row is header
                headers = rows[0]
                data = rows[1:] if len(rows) > 1 else []
                ascii_table = tabulate(data, headers=headers, tablefmt="simple")
                code_blocks.append(ascii_table)
                return f"{placeholder}{len(code_blocks) - 1}{placeholder}"
        except Exception as e:
            logger.warning(f"Table conversion failed: {e}")
        # Fallback: keep as code block
        code_blocks.append(match.group(0))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    # Match consecutive lines that look like table rows
    table_pattern = r'(?:^\|.+\|$\n?)+'
    text = re.sub(table_pattern, convert_table, text, flags=re.MULTILINE)

    # Inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic (*text* or _text_) - be careful not to match inside words
    text = re.sub(r'(?<![a-zA-Z0-9])\*([^*]+)\*(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # Headers (# Header) -> bold
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Markdown links [text](url) -> <a href="url">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Wikilinks [[Note Name]] or [[@Person]] -> clickable deep link
    def format_wikilink(match):
        import urllib.parse
        note_name = match.group(1)
        # Remove @ prefix if present for display
        display_name = note_name.lstrip('@')
        # URL-encode for deep link parameter (replace spaces with _)
        encoded_name = urllib.parse.quote(display_name, safe='')
        # Telegram deep link: https://t.me/BOT?start=note_ENCODED
        deep_link = f'https://t.me/toolbuildingape_bot?start=note_{encoded_name}'
        return f'<a href="{deep_link}">📄 {display_name}</a>'

    text = re.sub(r'\[\[([^\]]+)\]\]', format_wikilink, text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    return text


# =============================================================================
# Menu and Settings Commands
# =============================================================================


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command - show all available commands by category."""
    user = update.effective_user

    if not user:
        return

    logger.info(f"Menu command from user {user.id}")

    from ..services.keyboard_service import get_keyboard_service

    service = get_keyboard_service()
    categories = service.get_command_categories()

    if not categories:
        # Fallback if config not loaded
        if update.message:
            await update.message.reply_text(
                "Menu not available. Try /help instead.",
                parse_mode="HTML",
            )
        return

    # Build formatted message
    lines = ["<b>📋 Command Menu</b>"]

    for cat_key, category in categories.items():
        emoji = category.get("emoji", "")
        title = category.get("title", cat_key.title())
        lines.append(f"\n{emoji} <b>{title}</b>")

        for cmd in category.get("commands", []):
            command = cmd.get("command", "")
            desc = cmd.get("description", "")
            lines.append(f"  <code>{command}</code> — {desc}")

    # Add reply keyboard
    reply_keyboard = await service.build_reply_keyboard(user.id)

    if update.message:
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_keyboard,
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show keyboard customization menu."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Settings command from user {user.id} in chat {chat.id}")

    from ..services.keyboard_service import get_keyboard_service
    from .keyboard_utils import get_keyboard_utils

    service = get_keyboard_service()
    keyboard_utils = get_keyboard_utils()

    config = await service.get_user_config(user.id)
    enabled = config.get("enabled", True)

    # Create settings inline keyboard
    reply_markup = keyboard_utils.create_settings_keyboard(enabled)

    if update.message:
        await update.message.reply_text(
            "<b>⚙️ Settings</b>\n\n"
            f"Reply Keyboard: {'✅ Enabled' if enabled else '❌ Disabled'}\n\n"
            "Customize your quick-access buttons:",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
