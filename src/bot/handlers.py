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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
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

    welcome_msg = f"""🤖 <b>Welcome to Telegram Agent, {user.first_name or 'there'}!</b>

I analyze images using AI vision models. Send me any photo for instant analysis!

🎯 <b>Current Mode:</b> Default (quick descriptions)

📸 <i>Send me an image to get started, or use the buttons below to switch modes!</i>

💡 <i>Tip: Artistic modes include similarity search with your previous uploads.</i>"""

    # Create mode selection keyboard
    from .keyboard_utils import get_keyboard_utils

    keyboard_utils = get_keyboard_utils()
    reply_markup = keyboard_utils.create_mode_selection_keyboard("default", None)

    if update.message:
        await update.message.reply_text(
            welcome_msg, parse_mode="HTML", reply_markup=reply_markup
        )


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
