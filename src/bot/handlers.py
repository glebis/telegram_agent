import logging
from typing import Optional
from sqlalchemy import select

from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import get_db_session
from ..core.mode_manager import ModeManager
from ..models.user import User
from ..models.chat import Chat

logger = logging.getLogger(__name__)


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


async def get_claude_mode(chat_id: int) -> bool:
    """Check if a chat is in Claude mode (locked session)."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_record = result.scalar_one_or_none()
            if chat_record:
                return getattr(chat_record, "claude_mode", False)
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
                logger.info(f"Set claude_mode={enabled} for chat {chat_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Error setting claude_mode: {e}")
        return False


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

            # Execute claude command to view the note
            context.args = ["view", "note", f'"{note_name}"']
            await claude_command(update, context)
            return

    welcome_msg = f"""<b>Personal Knowledge Capture</b>

A bridge between fleeting thoughts and your knowledge system.

<b>What I process:</b>

<b>Links</b> — Send any URL. I fetch the full content, extract the essence, and save it to your Obsidian vault. Smart routing learns your preferences.

<b>Images</b> — Photos are analyzed and classified (screenshot, receipt, document, diagram, photo). Each routes to the appropriate folder. Receipts go to expenses, diagrams to research.

<b>Voice</b> — Speak your thoughts. I transcribe via Whisper, detect intent (task, note, quick thought), and append to your daily notes or inbox.

<b>Text</b> — Prefix with <code>inbox:</code>, <code>research:</code>, or <code>task:</code> to route directly.

Everything flows to your Obsidian vault. The system learns from your corrections.

<i>Send something to begin.</i>"""

    if update.message:
        await update.message.reply_text(welcome_msg, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    user = update.effective_user

    logger.info(f"Help command from user {user.id if user else 'unknown'}")

    help_msg = """📚 **Telegram Agent Help**

🖼️ **Image Analysis:**
Send any image and I'll analyze it based on your current mode.

🔧 **Mode System:**
• **Default Mode** - Quick descriptions (≤40 words) + text extraction
• **Artistic Mode** - In-depth analysis with similarity search

📋 **Available Commands:**

**Mode Commands:**
• `/mode default` - Switch to quick description mode
• `/mode artistic Critic` - Art-historical & compositional analysis
• `/mode artistic Photo-coach` - Photography improvement advice
• `/mode artistic Creative` - Creative interpretation & storytelling

**Quick Aliases:**
• `/analyze` = `/mode artistic Critic`
• `/coach` = `/mode artistic Photo-coach`
• `/creative` = `/mode artistic Creative`

**Other Commands:**
• `/start` - Show welcome message
• `/gallery` - Browse your uploaded images (10 per page)
• `/help` - Show this help (you're here!)

🎨 **Artistic Mode Features:**
- Detailed analysis (100-150 words)
- Composition, color theory, lighting analysis
- Art-historical references
- Similar image suggestions from your uploads
- Vector embeddings for smart similarity search

💡 **Tips:**
- Send high-quality images for better analysis
- Try different modes to see various perspectives
- In artistic mode, I remember your images for similarity search
- Text visible in images will be extracted and quoted

Need more help? Just ask! 🤖"""

    if update.message:
        await update.message.reply_text(help_msg)


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


# Claude Code commands
async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude command - execute Claude Code prompts."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Claude command from user {user.id} in chat {chat.id}")

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

    # Initialize user and chat if needed
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Get prompt from arguments
    prompt = " ".join(context.args) if context.args else None

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
            short_id = active_session_id[:8]
            prompt_preview = (last_prompt or "No prompt")[:40]
            lock_status = "🔒 Locked" if is_locked else "🔓 Unlocked"
            status_text = (
                f"<b>🤖 Claude Code</b>\n\n"
                f"▶️ Session: <code>{short_id}...</code>\n"
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

    # Execute prompt
    await execute_claude_prompt(update, context, prompt)


async def claude_new_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /claude_new command - start a new Claude Code session."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Claude new session command from user {user.id}")

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

    # End current session
    service = get_claude_code_service()
    await service.end_session(chat.id)

    # Get prompt from arguments
    prompt = " ".join(context.args) if context.args else None

    if prompt:
        await execute_claude_prompt(update, context, prompt, force_new=True)
    else:
        if update.message:
            await update.message.reply_text(
                "New session ready. Send a prompt with:\n"
                "<code>/claude &lt;your prompt&gt;</code>",
                parse_mode="HTML",
            )


async def claude_sessions_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /claude_sessions command - list and manage sessions."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Claude sessions command from user {user.id}")

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

    service = get_claude_code_service()
    sessions = await service.get_user_sessions(chat.id)
    active_session = await service.get_active_session(chat.id)

    if not sessions:
        if update.message:
            await update.message.reply_text(
                "No Claude Code sessions found.\n\n"
                "Start a new session with:\n"
                "<code>/claude &lt;your prompt&gt;</code>",
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
            f"<b>Claude Code Sessions</b>\n\n"
            f"Found {len(sessions)} session(s).\n"
            f"Select one to resume:",
            parse_mode="HTML",
            reply_markup=reply_markup,
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
    from .keyboard_utils import get_keyboard_utils

    service = get_claude_code_service()
    keyboard_utils = get_keyboard_utils()

    # Get or skip active session
    session_id = None if force_new else await service.get_active_session(chat.id)

    # Store prompt for retry functionality
    context.user_data["last_claude_prompt"] = prompt

    # Send initial message with processing keyboard
    if not update.message:
        return

    processing_keyboard = keyboard_utils.create_claude_processing_keyboard()

    # Show detailed processing status
    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_status = f"Resuming {session_id[:8]}..." if session_id else "New session"
    status_msg = await update.message.reply_text(
        f"<b>🤖 Claude Code</b>\n\n"
        f"<i>{_escape_html(prompt_preview)}</i>\n\n"
        f"⏳ {session_status}\n"
        f"📂 ~/Research/vault",
        parse_mode="HTML",
        reply_markup=processing_keyboard,
    )

    # Store message ID for stop functionality
    context.user_data["claude_status_msg_id"] = status_msg.message_id

    # Get user's database ID
    from sqlalchemy import select

    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.user_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await status_msg.edit_text("Error: User not found in database.")
            return
        user_db_id = db_user.id

    # Collect output for streaming
    accumulated_text = ""
    last_update_time = 0
    update_interval = 1.0  # Update every 1 second
    new_session_id = None

    import time

    try:
        async for chunk, sid in service.execute_prompt(
            prompt=prompt,
            chat_id=chat.id,
            user_id=user_db_id,
            session_id=session_id,
        ):
            if sid:
                new_session_id = sid

            accumulated_text += chunk

            # Throttle message updates
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                # Truncate if too long for Telegram
                display_text = accumulated_text[-3600:] if len(accumulated_text) > 3600 else accumulated_text
                if len(accumulated_text) > 3600:
                    display_text = "...(truncated)\n" + display_text

                try:
                    await status_msg.edit_text(
                        _markdown_to_telegram_html(display_text),
                        parse_mode="HTML",
                        reply_markup=processing_keyboard,
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Failed to update message: {e}")

        # Final update - split long messages instead of truncating
        session_info = f"\n\n<i>Session: {new_session_id[:8]}...</i>" if new_session_id else ""

        # Check if locked mode is active
        is_locked = await get_claude_mode(chat.id)
        complete_keyboard = keyboard_utils.create_claude_complete_keyboard(is_locked=is_locked)

        # Split into chunks of ~3800 chars (leaving room for HTML formatting)
        max_chunk_size = 3800
        full_html = _markdown_to_telegram_html(accumulated_text)

        if len(full_html) <= max_chunk_size:
            # Single message - fits in one
            await status_msg.edit_text(
                full_html + session_info,
                parse_mode="HTML",
                reply_markup=complete_keyboard,
            )
        else:
            # Multiple messages needed - split by paragraphs or newlines
            chunks = _split_message(full_html, max_chunk_size)

            # First chunk replaces status message (no keyboard)
            await status_msg.edit_text(
                chunks[0] + "\n\n<i>... continued below ...</i>",
                parse_mode="HTML",
            )

            # Send remaining chunks as new messages
            for i, chunk in enumerate(chunks[1:], 2):
                is_last = i == len(chunks)
                if is_last:
                    await update.message.reply_text(
                        chunk + session_info,
                        parse_mode="HTML",
                        reply_markup=complete_keyboard,
                    )
                else:
                    await update.message.reply_text(
                        chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                        parse_mode="HTML",
                    )

    except Exception as e:
        logger.error(f"Error executing Claude prompt: {e}")
        await status_msg.edit_text(
            f"❌ Error: {str(e)}",
            reply_markup=keyboard_utils.create_claude_complete_keyboard(),
        )


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

    # Detect and wrap markdown tables in code blocks
    # Table pattern: lines starting with | and containing |
    def save_table(match):
        code_blocks.append(match.group(0))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    # Match consecutive lines that look like table rows
    table_pattern = r'(?:^\|.+\|$\n?)+'
    text = re.sub(table_pattern, save_table, text, flags=re.MULTILINE)

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
