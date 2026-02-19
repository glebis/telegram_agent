import asyncio
import json
import logging
import os
import re
import traceback
from typing import List, Optional, Tuple

import litellm
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from ..core.config import get_settings
from ..core.database import get_db_session
from ..core.error_messages import sanitize_error
from ..core.i18n import get_user_locale_from_update, t
from ..core.vector_db import get_vector_db
from ..models.chat import Chat
from ..models.image import Image
from ..services.cache_service import get_cache_service
from ..services.image_classifier import get_image_classifier
from ..services.image_service import get_image_service
from ..services.link_service import get_link_service, track_capture
from ..services.llm_service import get_llm_service
from ..services.routing_memory import get_routing_memory
from ..services.similarity_service import get_similarity_service
from ..services.voice_service import get_voice_service
from ..utils.logging import (
    get_image_logger,
    log_image_processing_error,
)

# URL regex pattern
URL_PATTERN = re.compile(
    r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*", re.IGNORECASE
)

logger = logging.getLogger(__name__)
image_logger = get_image_logger("message_handlers")


def _is_debug_mode() -> bool:
    """Check debug mode from settings, with env-var fallback."""
    try:
        return get_settings().debug
    except Exception:
        return os.getenv("DEBUG", "false").lower() == "true"


async def handle_image_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle image messages from users"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    if not user or not chat or not message:
        return

    logger.info(f"Image message from user {user.id} in chat {chat.id}")

    # Get the largest photo or document
    photo = None
    file_id = None

    if message.photo:
        # Get the largest photo
        photo = message.photo[-1]
        file_id = photo.file_id
        logger.info(f"Photo received: {file_id}, size: {photo.width}x{photo.height}")
    elif message.document and message.document.mime_type:
        mime = message.document.mime_type
        # Validate MIME type against allowed image types
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if mime not in allowed:
            logger.warning("Rejected document with MIME %s (not in allowed set)", mime)
            await message.reply_text(
                "❌ Unsupported image format. " "Please send JPEG, PNG, WebP, or GIF."
            )
            return
        file_id = message.document.file_id
        logger.info(
            f"Image document received: {file_id}, "
            f"mime={mime}, size: {message.document.file_size}"
        )

    if not file_id:
        await message.reply_text(
            "❌ No image found in your message. Please send a photo."
        )
        return

    # Check file size (Telegram limit is 20MB for photos, 50MB for documents)
    max_size_mb = 10  # Our processing limit

    if hasattr(message, "document") and message.document and message.document.file_size:
        file_size_mb = message.document.file_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            await message.reply_text(
                f"❌ Image is too large ({file_size_mb:.1f}MB). "
                f"Please send images smaller than {max_size_mb}MB."
            )
            return

    # Check if in Claude locked mode - route images to Claude
    from ..services.claude_code_service import is_claude_code_admin
    from .handlers import execute_claude_prompt, get_claude_mode

    if await get_claude_mode(chat.id) and await is_claude_code_admin(chat.id):
        logger.info(f"Claude mode active, routing image to Claude: {file_id}")

        # Download the image to a temp location Claude can access
        try:
            from pathlib import Path

            # Create temp directory in Claude's work area
            temp_dir = Path(get_settings().vault_temp_images_dir).expanduser()
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Download from Telegram via subprocess isolation
            import os
            import uuid

            from src.utils.subprocess_helper import download_telegram_file

            ext = ".jpg"  # Default to jpg for photos
            if message.document and message.document.file_name:
                ext = Path(message.document.file_name).suffix or ".jpg"

            image_filename = f"telegram_{uuid.uuid4().hex[:8]}{ext}"
            image_path = temp_dir / image_filename

            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            dl_result = download_telegram_file(
                file_id=file_id,
                bot_token=bot_token,
                output_path=image_path,
            )
            if not dl_result.success:
                raise RuntimeError(f"Download failed: {dl_result.error}")
            logger.info(f"Downloaded image for Claude to: {image_path}")

            # Build prompt with image path and caption
            caption = message.caption or ""
            if caption:
                prompt = (
                    f"Look at this image I'm sending you: {image_path}\n\n{caption}"
                )
            else:
                prompt = (
                    f"Look at this image I'm sending you and analyze it: {image_path}"
                )

            # Show a brief processing message
            processing_msg = await message.reply_text("📷 Sending image to Claude...")

            # Execute Claude prompt with the image
            await execute_claude_prompt(update, context, prompt)

            # Delete the processing message
            try:
                await processing_msg.delete()
            except Exception:
                pass

            return

        except Exception as e:
            logger.error(f"Error downloading image for Claude: {e}", exc_info=True)
            await message.reply_text(
                f"❌ {sanitize_error(e, context='preparing image for Claude')}"
            )
            return

    # Get current mode for this chat
    current_mode = "default"
    current_preset = None

    try:
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_record = result.scalar_one_or_none()
            if chat_record:
                current_mode = chat_record.current_mode
                current_preset = chat_record.current_preset
    except Exception as e:
        logger.error(f"Error getting chat mode: {e}")

    # Send processing message
    processing_msg = await message.reply_text(
        f"🔄 Processing your image...\n"
        f"📋 Mode: {current_mode.title()}"
        f"{f' - {current_preset}' if current_preset else ''}\n"
        f"⏳ This may take a few seconds..."
    )

    # Resolve locale for i18n
    locale = get_user_locale_from_update(update)

    # Process image with real LLM analysis
    try:
        await process_image_with_llm(
            file_id=file_id,
            chat_id=chat.id,
            user_id=user.id,
            mode=current_mode,
            preset=current_preset,
            message=message,
            processing_msg=processing_msg,
            locale=locale,
        )

    except Exception as e:
        # Log comprehensive error details
        error_context = {
            "user_id": user.id,
            "chat_id": chat.id,
            "file_id": file_id,
            "mode": current_mode,
            "preset": current_preset,
            "username": user.username,
            "operation": "handle_image_message",
        }

        log_image_processing_error(e, error_context, image_logger)
        logger.error(f"Error processing image for user {user.id}: {e}", exc_info=True)

        # Build user-facing error message (never expose raw exception)
        if _is_debug_mode():
            error_type = type(e).__name__
            user_error = f"❌ Error: {error_type}\n\n{str(e)[:500]}"
        else:
            user_error = f"❌ {sanitize_error(e, context='processing your image')}"

        await processing_msg.edit_text(user_error)


async def process_image_with_llm(
    file_id: str,
    chat_id: int,
    user_id: int,
    mode: str,
    preset: Optional[str],
    message: Message,
    processing_msg: Message,
    locale: Optional[str] = None,
) -> None:
    """Process image with real LLM analysis"""

    try:
        # Get services
        cache_service = get_cache_service()

        # Check cache first
        cached_analysis = await cache_service.get_cached_analysis(file_id, mode, preset)
        if cached_analysis:
            logger.info(
                f"Using cached analysis for file_id={file_id}, mode={mode}, preset={preset}"
            )

            # Format cached response
            response_text, reply_markup = get_llm_service().format_telegram_response(
                cached_analysis, include_keyboard=True
            )

            # Delete processing message
            await processing_msg.delete()

            # Send new message with cached results
            await message.reply_text(
                f"💾 {response_text}",  # Add cache indicator
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return

        # Get bot instance for downloading images
        from ..bot.bot import get_bot

        bot_instance = get_bot()
        if not bot_instance or not bot_instance.application:
            raise RuntimeError("Bot instance not initialized")
        bot = bot_instance.application.bot

        # Get services
        image_service = get_image_service()
        llm_service = get_llm_service()
        similarity_service = get_similarity_service()
        vector_db = get_vector_db()

        # Download and process image
        analysis = await image_service.process_image(bot, file_id, mode, preset)

        # Classify image for smart routing
        classifier = get_image_classifier()
        processed_path = analysis.get("processed_path")
        classification = None
        if processed_path:
            try:
                classification = await classifier.classify(processed_path)
                analysis["classification"] = classification
                logger.info(f"Image classified: {classification}")
            except Exception as e:
                logger.error(f"Image classification failed: {e}")
                classification = {
                    "category": "other",
                    "destination": "inbox",
                    "provider": "default",
                }
                analysis["classification"] = classification

        # Add metadata
        analysis["cached"] = False

        # Similarity search will be handled after saving to database
        analysis["similar_count"] = 0

        # Format response for Telegram with keyboard
        response_text, _ = llm_service.format_telegram_response(
            analysis, include_keyboard=False  # We'll use routing buttons instead
        )

        # Validate response format
        if not isinstance(response_text, str):
            logger.error(f"Invalid response_text type: {type(response_text)}")
            raise ValueError(f"Expected string, got {type(response_text)}")

        # Add classification info to response
        if classification:
            category = classification.get("category", "other")
            destination = classification.get("destination", "inbox")
            classification.get("provider", "default")
            response_text += f"\n\n<i>Type: {category} | Route: {destination}</i>"

        # Delete processing message
        await processing_msg.delete()

        # Send new message with results first (we need the message_id for buttons)
        result_msg = await message.reply_text(response_text, parse_mode="HTML")

        # Create routing buttons using result_msg.message_id (so callback can find tracked info)
        routing_keyboard = [
            [
                InlineKeyboardButton(
                    t("inline.route.inbox", locale),
                    callback_data=f"img_route:inbox:{result_msg.message_id}",
                ),
                InlineKeyboardButton(
                    t("inline.route.media", locale),
                    callback_data=f"img_route:media:{result_msg.message_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    t("inline.route.expenses", locale),
                    callback_data=f"img_route:expenses:{result_msg.message_id}",
                ),
                InlineKeyboardButton(
                    t("inline.route.research", locale),
                    callback_data=f"img_route:research:{result_msg.message_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    t("inline.route.done", locale),
                    callback_data=f"img_route:done:{result_msg.message_id}",
                ),
            ],
        ]
        routing_markup = InlineKeyboardMarkup(routing_keyboard)

        # Edit message to add buttons
        await result_msg.edit_reply_markup(reply_markup=routing_markup)

        # Track image for routing callback using result_msg.message_id
        track_capture(
            result_msg.message_id,
            {
                "path": processed_path,
                "original_path": analysis.get("original_path"),
                "category": (
                    classification.get("category", "other")
                    if classification
                    else "other"
                ),
                "destination": (
                    classification.get("destination", "inbox")
                    if classification
                    else "inbox"
                ),
                "file_id": file_id,
            },
        )

        # Track for reply context (enables "reply to ask more about this image")
        from ..services.reply_context import get_reply_context_service

        reply_context_service = get_reply_context_service()
        reply_context_service.track_image_analysis(
            message_id=result_msg.message_id,
            chat_id=chat_id,
            user_id=user_id,
            image_path=processed_path,
            image_file_id=file_id,
            analysis=analysis,
        )

        # Save to database
        try:
            async with get_db_session() as session:
                # Get embedding bytes if available
                embedding_bytes = analysis.get("embedding_bytes")

                # Get file info from analysis
                file_info = analysis.get("telegram_file_info", {})
                file_unique_id = file_info.get("file_unique_id", f"unique_{file_id}")

                # Get dimensions safely
                dimensions = analysis.get("dimensions", {})
                processed_dims = dimensions.get("processed", [0, 0])
                width = (
                    processed_dims[0]
                    if isinstance(processed_dims, list) and len(processed_dims) >= 2
                    else 0
                )
                height = (
                    processed_dims[1]
                    if isinstance(processed_dims, list) and len(processed_dims) >= 2
                    else 0
                )

                # Get file paths
                original_path = analysis.get("original_path")
                processed_path = analysis.get("processed_path")

                # Log what we're storing
                logger.info(
                    f"Storing image in database: file_id={file_id}, unique_id={file_unique_id}"
                )
                logger.info(
                    f"Image dimensions: {width}x{height}, mode={mode}, preset={preset or 'None'}"
                )
                logger.info(
                    f"Paths: original={original_path}, processed={processed_path}"
                )

                # First, get the chat record to ensure it exists
                from sqlalchemy import select

                chat_query = select(Chat).where(Chat.chat_id == chat_id)
                chat_result = await session.execute(chat_query)
                chat_record = chat_result.scalar_one_or_none()

                if not chat_record:
                    logger.warning(
                        f"Chat record not found for chat_id {chat_id}, creating new record"
                    )
                    # Create a new chat record if it doesn't exist
                    chat_record = Chat(
                        chat_id=chat_id,
                        user_id=user_id,
                        username=(
                            message.from_user.username if message.from_user else None
                        ),
                        first_name=(
                            message.from_user.first_name
                            if message.from_user
                            else "Unknown"
                        ),
                        last_name=(
                            message.from_user.last_name if message.from_user else None
                        ),
                        current_mode=mode,
                        current_preset=preset,
                    )
                    session.add(chat_record)
                    await session.commit()
                    await session.refresh(chat_record)

                # Prepare analysis data for JSON storage (remove bytes objects)
                analysis_for_db = analysis.copy()
                # Remove embedding_bytes before JSON serialization
                analysis_for_db.pop("embedding_bytes", None)

                # Create image record with proper chat_id from the database record
                image_record = Image(
                    chat_id=chat_record.id,  # Use the database ID, not the Telegram chat_id
                    file_id=file_id,
                    file_unique_id=file_unique_id,
                    original_path=original_path,
                    compressed_path=processed_path,
                    file_size=analysis.get(
                        "file_size", 0
                    ),  # Default to 0 if not available
                    width=width if width else 800,  # Default width if not available
                    height=height if height else 600,  # Default height if not available
                    format="jpg",  # Default to jpg for now
                    embedding=embedding_bytes,  # Store embedding
                    analysis=json.dumps(
                        analysis_for_db
                    ),  # Store as proper JSON string without bytes
                    mode_used=mode,
                    preset_used=preset,
                    processing_status="completed",
                    embedding_model=analysis.get("embedding_model"),
                )

                # Add to session and commit
                session.add(image_record)
                await session.commit()

                # Get the saved image ID for vector database
                await session.refresh(image_record)
                saved_image_id = image_record.id

                logger.info(
                    f"Saved image analysis for file_id: {file_id}, image_id: {saved_image_id}"
                )

                # Store embedding in vector database for efficient similarity search
                if embedding_bytes:
                    try:
                        success = await vector_db.store_embedding(
                            saved_image_id, embedding_bytes
                        )
                        if success:
                            logger.info(
                                f"Stored embedding in vector database for image {saved_image_id}"
                            )
                        else:
                            logger.warning(
                                f"Failed to store embedding in vector database for image {saved_image_id}"
                            )
                            # Update the analysis to indicate embedding storage failed
                            analysis["embedding_status"] = "storage_failed"
                    except Exception as e:
                        logger.error(f"Error storing embedding in vector database: {e}")
                        logger.error(
                            f"Vector DB storage error: {traceback.format_exc()}"
                        )
                        # Update the analysis to indicate embedding storage failed with error
                        analysis["embedding_status"] = "storage_error"
                else:
                    logger.warning(
                        f"No embedding bytes available for image {saved_image_id}"
                    )
                    analysis["embedding_status"] = "generation_failed"

                # Search for similar images for all modes
                # All images should be added to the gallery with similarity search support
                if embedding_bytes:
                    try:
                        similar_images = await similarity_service.find_similar_images(
                            image_id=saved_image_id,
                            user_id=user_id,
                            scope="user",
                            limit=5,
                            similarity_threshold=0.7,
                        )
                        analysis["similar_count"] = len(similar_images)
                        analysis["similar_images"] = similar_images

                        # Re-format response with updated similarity info
                        response_text, reply_markup = (
                            llm_service.format_telegram_response(
                                analysis, include_keyboard=True
                            )
                        )
                        logger.info(f"Found {len(similar_images)} similar images")

                    except Exception as e:
                        logger.error(f"Error finding similar images: {e}")
                        logger.error(
                            f"Similarity search error: {traceback.format_exc()}"
                        )
                        analysis["similar_count"] = 0
                        analysis["similar_images"] = []
                        analysis["embedding_status"] = "similarity_search_failed"

        except Exception as e:
            logger.error(f"Error saving image analysis to database: {e}")
            logger.error(f"Database error details: {traceback.format_exc()}")
            # Update processing message to indicate database error
            await processing_msg.edit_text(
                "⚠️ Image was analyzed but couldn't be saved to your gallery.\n"
                "The analysis results are shown below, but won't appear in your gallery."
            )
            # Don't fail the whole process if database save fails

    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_msg = str(e)
        stack_trace = traceback.format_exc()

        # Log comprehensive error details to file
        error_context = {
            "user_id": user_id,
            "chat_id": chat_id,
            "file_id": file_id,
            "mode": mode,
            "preset": preset,
            "operation": "process_image_with_llm",
            "error_type": error_type,
            "stack_trace": stack_trace,
        }

        log_image_processing_error(e, error_context, image_logger)

        # Also log to standard logger for immediate visibility
        logger.error(
            f"Error in LLM image processing: {error_type}: {error_msg}", exc_info=True
        )

        # Prepare user-facing message
        if _is_debug_mode():
            # In debug mode, show more detailed error
            error_message = (
                f"❌ Error processing image: {error_type}\n\n"
                f"Message: {error_msg}\n\n"
                f"This detailed error is shown because DEBUG=true"
            )
            # Also print to console for immediate visibility
            print(
                f"\n{'=' * 50}\nIMAGE PROCESSING ERROR (DEBUG MODE):\n{error_type}: {error_msg}\n{'=' * 50}\n"
            )
        else:
            # In production, show generic message
            error_message = "❌ Sorry, there was an error analyzing your image. Please try again later."

        # Send error message
        await processing_msg.edit_text(error_message)
        raise


def extract_urls(text: str) -> List[str]:
    """Extract URLs from text"""
    return URL_PATTERN.findall(text)


def parse_prefix_command(text: str) -> Tuple[Optional[str], str]:
    """
    Parse prefix command from text (e.g., 'inbox: some content')

    Returns:
        Tuple of (prefix, remaining_text)
    """
    prefixes = ["task:", "note:", "inbox:", "research:", "expense:", "agent:"]
    text_lower = text.lower().strip()

    for prefix in prefixes:
        if text_lower.startswith(prefix):
            return prefix.rstrip(":"), text[len(prefix) :].strip()

    return None, text


async def handle_link_message(
    message: Message,
    urls: List[str],
    destination: Optional[str] = None,
    locale: Optional[str] = None,
) -> None:
    """Handle messages containing URLs - capture and save to Obsidian"""
    link_service = get_link_service()
    routing_memory = get_routing_memory()

    # Process only the first URL for now
    url = urls[0]

    # Get suggested destination from routing memory if not explicitly set
    if destination is None:
        destination = routing_memory.get_suggested_destination(
            url=url, content_type="links"
        )
        logger.info(f"Using learned destination for {url}: {destination}")

    # Send processing message
    processing_msg = await message.reply_text(
        f"Capturing link...\n"
        f"{url[:60]}{'...' if len(url) > 60 else ''}\n"
        f"Fetching page content..."
    )

    try:
        success, result = await link_service.capture_link(url, destination)

        if success:
            # Track the capture for re-routing (use processing_msg.message_id as key)
            # Store path, url, and title for the callback
            track_capture(
                processing_msg.message_id,
                {
                    "path": result["path"],
                    "url": url,
                    "title": result["title"],
                    "destination": destination,
                },
            )

            # Record the initial route (will be updated if user changes it)
            routing_memory.record_route(
                destination=destination,
                content_type="links",
                url=url,
                title=result["title"],
            )

            # Create routing buttons - include message_id for tracking
            msg_id = processing_msg.message_id
            keyboard = [
                [
                    InlineKeyboardButton(
                        t("inline.route.inbox", locale),
                        callback_data=f"route:inbox:{msg_id}",
                    ),
                    InlineKeyboardButton(
                        t("inline.route.daily", locale),
                        callback_data=f"route:daily:{msg_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        t("inline.route.research", locale),
                        callback_data=f"route:research:{msg_id}",
                    ),
                    InlineKeyboardButton(
                        t("inline.route.done", locale),
                        callback_data=f"route:done:{msg_id}",
                    ),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await processing_msg.edit_text(
                f"<b>Link captured</b>\n\n"
                f"<b>{result['title'][:80]}</b>\n"
                f"{url}\n"
                f"Saved to: <code>{destination}</code>\n\n"
                f"<i>Move to different folder:</i>",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

            # Track for reply context
            from ..services.reply_context import get_reply_context_service

            reply_context_service = get_reply_context_service()
            reply_context_service.track_link_capture(
                message_id=processing_msg.message_id,
                chat_id=message.chat_id,
                user_id=message.from_user.id if message.from_user else 0,
                url=url,
                title=result["title"],
                path=result["path"],
            )
        else:
            await processing_msg.edit_text(
                f"❌ <b>Failed to capture link</b>\n\n"
                f"🔗 {url}\n"
                f"Error: {result.get('error', 'Unknown error')}\n\n"
                f"<i>Try again or check if the URL is accessible</i>",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Error capturing link {url}: {e}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ <b>Error capturing link</b>\n\n"
            f"🔗 {url}\n"
            f"{sanitize_error(e)}\n\n"
            f"<i>Please try again later</i>",
            parse_mode="HTML",
        )


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle text messages from users"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    if not user or not chat or not message or not message.text:
        return

    text = message.text.strip()
    logger.info(f"Text message from user {user.id}: {text[:50]}...")

    # Check if in Claude locked mode - route all messages to Claude
    from ..services.claude_code_service import is_claude_code_admin
    from .handlers import execute_claude_prompt, get_claude_mode

    if await get_claude_mode(chat.id) and await is_claude_code_admin(chat.id):
        # Check for pending auto-forward first (after "New" button - needs force_new)
        if os.getenv("ENVIRONMENT") != "test":
            from sqlalchemy import select
            from sqlalchemy import update as sa_update

            async with get_db_session() as session:
                result = await session.execute(
                    select(Chat).where(Chat.chat_id == chat.id)
                )
                chat_obj = result.scalar_one_or_none()

                if chat_obj and chat_obj.pending_auto_forward_claude:
                    logger.info(
                        f"New session pending, routing first message to Claude: {text[:30]}..."
                    )
                    # Clear the pending flag
                    await session.execute(
                        sa_update(Chat)
                        .where(Chat.chat_id == chat.id)
                        .values(pending_auto_forward_claude=False)
                    )
                    await session.commit()
                    # Forward to Claude with force_new=True to start fresh session
                    await execute_claude_prompt(update, context, text, force_new=True)
                    return

        logger.info(f"Claude mode active, routing message to Claude: {text[:30]}...")
        await execute_claude_prompt(update, context, text)
        return

    # Check for prefix commands
    prefix, content = parse_prefix_command(text)

    # Check for URLs in message
    urls = extract_urls(text)

    if urls:
        # Message contains URLs - handle as link capture
        destination = "inbox"

        # Map prefix to destination
        if prefix:
            prefix_to_dest = {
                "inbox": "inbox",
                "research": "research",
                "note": "inbox",
                "task": "daily",
            }
            destination = prefix_to_dest.get(prefix, "inbox")

        logger.info(f"Found {len(urls)} URL(s) in message, capturing to {destination}")
        locale = get_user_locale_from_update(update)
        await handle_link_message(message, urls, destination, locale=locale)
        return

    # Handle prefix commands without URLs
    if prefix == "agent":
        await message.reply_text(
            "🤖 <b>Agent Mode</b>\n\n"
            "Agent invocation requires specific content to process.\n"
            "Send a link, image, or voice message with the agent: prefix.",
            parse_mode="HTML",
        )
        return

    # Standalone "help" → redirect to /help command
    text_lower = text.lower().strip()
    if text_lower == "help":
        from .handlers.core_commands import help_command

        await help_command(update, context)
        return

    # Conversational fallback: use LLM for all other plain text
    await _handle_conversational_text(message, text, chat.id)


async def _handle_conversational_text(
    message: Message, text: str, chat_id: int
) -> None:
    """Generate a conversational LLM response for plain text messages."""
    processing_msg = await message.reply_text("...")

    try:
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        system_prompt = (
            "You are a Telegram bot assistant. You can capture links to Obsidian, "
            "analyze images, transcribe voice messages, and manage notes. "
            "Keep responses concise (2-4 sentences). "
            "If the user seems to want a specific feature, mention the "
            "relevant command (e.g. /help, /claude, /mode, /track). "
            "Respond in the same language the user writes in."
        )

        # Include chat memory if available
        from ..services.workspace_service import get_memory

        memory = get_memory(chat_id)
        if memory:
            system_prompt += f"\n\nUser context:\n{memory[:500]}"

        response = await asyncio.to_thread(
            litellm.completion,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=300,
            temperature=0.7,
        )

        reply = response.choices[0].message.content.strip()
        await processing_msg.edit_text(reply)

    except Exception as e:
        logger.error(f"Conversational LLM error: {e}")
        # Fallback to a brief static response
        await processing_msg.edit_text(
            "I can help with images, links, voice, and more. "
            "Try /help to see all commands."
        )


async def handle_contact_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle contact messages - create person note and launch research"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    if not user or not chat or not message or not message.contact:
        return

    contact = message.contact
    logger.info(
        f"Contact received from user {user.id}: {contact.first_name} {contact.last_name or ''}"
    )

    # Send processing message
    processing_msg = await message.reply_text("📇 Processing contact...")

    try:
        # Build full name
        full_name = contact.first_name
        if contact.last_name:
            full_name += f" {contact.last_name}"

        # Prepare note filename (People/@Name.md format)
        # Sanitize contact name to prevent path traversal (CWE-22)
        safe_name = (
            full_name.strip().replace("/", "_").replace("\\", "_").replace("..", "_")
        )
        note_name = f"@{safe_name}"
        settings = get_settings()
        os.path.expanduser(settings.vault_path)
        people_folder = os.path.expanduser(settings.vault_people_dir)
        note_path = os.path.join(people_folder, f"{note_name}.md")

        # Validate resolved path stays within people folder
        from pathlib import Path

        if not Path(note_path).resolve().is_relative_to(Path(people_folder).resolve()):
            logger.warning(f"Path traversal attempt in contact name: {full_name}")
            await processing_msg.edit_text("⚠️ Invalid contact name.")
            return

        # Ensure People folder exists
        os.makedirs(people_folder, exist_ok=True)

        # Get current date for metadata
        from datetime import datetime

        today = datetime.now().strftime("%Y%m%d")

        # Check if note already exists
        note_exists = os.path.isfile(note_path)

        if note_exists:
            # Update existing note with Telegram handle
            logger.info(f"Updating existing note: {note_path}")
            with open(note_path, "r") as f:
                content = f.read()

            # Check if frontmatter exists
            if content.startswith("---\n"):
                # Parse existing frontmatter
                import yaml

                parts = content.split("---\n", 2)
                if len(parts) >= 3:
                    frontmatter_text = parts[1]
                    body = parts[2]
                    frontmatter = yaml.safe_load(frontmatter_text) or {}

                    # Update telegram info (Contact has: phone_number, first_name, last_name, user_id, vcard)
                    if contact.user_id:
                        frontmatter["telegram_id"] = contact.user_id
                    if contact.phone_number:
                        frontmatter["phone"] = contact.phone_number

                    # Write updated content
                    new_frontmatter = yaml.dump(
                        frontmatter, default_flow_style=False, allow_unicode=True
                    )
                    new_content = f"---\n{new_frontmatter}---\n{body}"

                    with open(note_path, "w") as f:
                        f.write(new_content)

                    action_text = "Updated"
                else:
                    action_text = "Note exists (no frontmatter to update)"
            else:
                # No frontmatter, add one
                frontmatter = {
                    "created_date": f"[[{today}]]",
                }
                if contact.user_id:
                    frontmatter["telegram_id"] = contact.user_id
                if contact.phone_number:
                    frontmatter["phone"] = contact.phone_number

                import yaml

                frontmatter_text = yaml.dump(
                    frontmatter, default_flow_style=False, allow_unicode=True
                )
                new_content = f"---\n{frontmatter_text}---\n\n{content}"

                with open(note_path, "w") as f:
                    f.write(new_content)

                action_text = "Updated"
        else:
            # Create new note
            logger.info(f"Creating new note: {note_path}")

            frontmatter = {
                "created_date": f"[[{today}]]",
                "type": "person",
            }
            if contact.user_id:
                frontmatter["telegram_id"] = contact.user_id
            if contact.phone_number:
                frontmatter["phone"] = contact.phone_number

            import yaml

            frontmatter_text = yaml.dump(
                frontmatter, default_flow_style=False, allow_unicode=True
            )

            note_content = f"""---
{frontmatter_text}---

# {full_name}

## Research

Research will be added automatically...

## Notes

"""

            with open(note_path, "w") as f:
                f.write(note_content)

            action_text = "Created"

        # Update processing message with success
        await processing_msg.edit_text(
            f"✅ {action_text} person note: {note_name}\n\n" f"🔍 Launching research..."
        )

        # Offer research via inline keyboard instead of auto-launching
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from ..services.claude_code_service import is_claude_code_admin

        if await is_claude_code_admin(chat.id):
            locale = get_user_locale_from_update(update)
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            t("inline.route.research", locale),
                            callback_data=f"contact_research:{message.message_id}",
                        ),
                        InlineKeyboardButton(
                            t("inline.route.skip", locale),
                            callback_data="contact_research:skip",
                        ),
                    ]
                ]
            )
            await message.reply_text(
                f"✅ {action_text} person note: {note_name}\n\n"
                f"Would you like to research {full_name} online?",
                reply_markup=keyboard,
            )
        else:
            await message.reply_text(
                f"✅ {action_text} person note: {note_name}\n\n"
                f"📝 Location: People/{note_name}.md"
            )

    except Exception as e:
        logger.error(f"Contact processing error: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ Sorry, I couldn't process this contact. Please try again."
        )


async def handle_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle voice messages - transcribe and route to Obsidian or Claude"""
    import tempfile

    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    if not user or not chat or not message:
        return

    voice = message.voice
    if not voice:
        return

    logger.info(f"Voice message from user {user.id}, duration: {voice.duration}s")

    # Check duration limit (2 min max for reasonable transcription)
    if voice.duration > 120:
        await message.reply_text(
            "Voice message too long. Maximum duration is 2 minutes."
        )
        return

    # Check if in Claude locked mode
    from ..services.claude_code_service import is_claude_code_admin
    from .handlers import execute_claude_prompt, get_claude_mode

    is_claude_mode = await get_claude_mode(chat.id) and await is_claude_code_admin(
        chat.id
    )

    # Send processing message
    processing_msg = await message.reply_text(
        "🎤 Transcribing voice message..." + (" → Claude" if is_claude_mode else "")
    )

    try:
        # Download voice file via subprocess isolation
        import os
        from pathlib import Path

        from src.utils.subprocess_helper import download_telegram_file

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            audio_path = tmp.name

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        dl_result = download_telegram_file(
            file_id=voice.file_id,
            bot_token=bot_token,
            output_path=Path(audio_path),
        )
        if not dl_result.success:
            raise RuntimeError(f"Voice download failed: {dl_result.error}")

        # Transcribe voice message
        voice_service = get_voice_service()
        success, transcribe_result = await voice_service.transcribe(audio_path)

        # Clean up temp file
        import os

        os.unlink(audio_path)

        if not success:
            error = transcribe_result.get("error", "Unknown error")
            await processing_msg.edit_text(f"❌ Transcription failed: {error}")
            return

        text = transcribe_result["text"]

        # Apply transcript corrections (#12)
        from ..services.keyboard_service import get_transcript_correction_level
        from ..services.transcript_corrector import get_transcript_corrector

        correction_level = await get_transcript_correction_level(chat.id)
        if correction_level != "none":
            corrector = get_transcript_corrector()
            text, correction_stats = corrector.correct_text_with_stats(
                text, level=correction_level
            )
            if correction_stats["corrections_count"] > 0:
                logger.info(
                    f"Applied {correction_stats['corrections_count']} transcript corrections "
                    f"(level={correction_level}) for chat {chat.id}"
                )

        # If in Claude mode, send transcription to Claude
        if is_claude_mode:
            # Check for pending auto-forward (after "New" button - needs force_new)
            force_new = False
            if os.getenv("ENVIRONMENT") != "test":
                from sqlalchemy import select
                from sqlalchemy import update as sa_update

                async with get_db_session() as session:
                    result = await session.execute(
                        select(Chat).where(Chat.chat_id == chat.id)
                    )
                    chat_obj = result.scalar_one_or_none()
                    if chat_obj and chat_obj.pending_auto_forward_claude:
                        force_new = True
                        await session.execute(
                            sa_update(Chat)
                            .where(Chat.chat_id == chat.id)
                            .values(pending_auto_forward_claude=False)
                        )
                        await session.commit()
                        logger.info(
                            f"New session pending, routing voice to Claude with force_new for chat {chat.id}"
                        )

            await processing_msg.edit_text(
                f"🎤 <i>{text[:100]}{'...' if len(text) > 100 else ''}</i>\n\n"
                f"Sending to Claude...",
                parse_mode="HTML",
            )
            # Delete the processing message and execute Claude prompt
            await processing_msg.delete()
            if force_new:
                await execute_claude_prompt(update, context, text, force_new=True)
            else:
                await execute_claude_prompt(update, context, text)
            return

        # Check if should auto-forward to Claude (when NOT in Claude mode)
        from sqlalchemy import select
        from sqlalchemy import update as sa_update

        from ..services.keyboard_service import get_auto_forward_voice

        should_auto_forward = await get_auto_forward_voice(chat.id)
        is_admin = await is_claude_code_admin(chat.id)

        # Check for pending auto-forward (after "New Session" button)
        pending_auto_forward = False
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_obj = result.scalar_one_or_none()
            if chat_obj and chat_obj.pending_auto_forward_claude:
                pending_auto_forward = True
                # Clear the pending flag
                await session.execute(
                    sa_update(Chat)
                    .where(Chat.chat_id == chat.id)
                    .values(pending_auto_forward_claude=False)
                )
                await session.commit()
                from .handlers import set_claude_mode

                await set_claude_mode(chat.id, True)
                logger.info(
                    f"Pending auto-forward cleared for voice message in chat {chat.id}, claude_mode enabled"
                )

        if (should_auto_forward or pending_auto_forward) and is_admin:
            # Auto-forward to Claude Code
            logger.info(
                f"Auto-forwarding voice to Claude for chat {chat.id} (pending={pending_auto_forward})"
            )

            # Send transcription to user first
            transcription_msg = await processing_msg.edit_text(
                f"🎤 <i>{text}</i>",
                parse_mode="HTML",
            )

            # Import and call forward function
            from .handlers.claude_commands import forward_voice_to_claude

            await forward_voice_to_claude(
                chat_id=chat.id,
                user_id=user.id,
                transcription=text,
                transcription_msg_id=transcription_msg.message_id,
                context=context,
                force_new=pending_auto_forward,  # Force new session if pending flag was set
            )
            return

        # Normal flow: detect intent and route to Obsidian
        intent_info = voice_service.detect_intent(text)
        formatted = voice_service.format_for_obsidian(text, intent_info)
        destination = intent_info.get("destination", "daily")

        # Create routing buttons
        locale = get_user_locale_from_update(update)
        msg_id = processing_msg.message_id
        keyboard = [
            [
                InlineKeyboardButton(
                    t("inline.route.daily", locale),
                    callback_data=f"voice:daily:{msg_id}",
                ),
                InlineKeyboardButton(
                    t("inline.route.inbox", locale),
                    callback_data=f"voice:inbox:{msg_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    t("inline.route.task", locale),
                    callback_data=f"voice:task:{msg_id}",
                ),
                InlineKeyboardButton(
                    t("inline.route.done", locale),
                    callback_data=f"voice:done:{msg_id}",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        intent_display = intent_info.get("intent", "quick").title()
        if intent_info.get("matched_keyword"):
            intent_display += f" ({intent_info['matched_keyword']})"

        await processing_msg.edit_text(
            f"<b>Transcription</b>\n\n"
            f"{text}\n\n"
            f"<i>Detected: {intent_display}</i>\n"
            f"<i>Will save to: {destination}</i>",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

        # Store transcription for routing callback
        track_capture(msg_id, formatted)

        # Track for reply context
        from ..services.reply_context import get_reply_context_service

        reply_context_service = get_reply_context_service()
        reply_context_service.track_voice_transcription(
            message_id=processing_msg.message_id,
            chat_id=chat.id,
            user_id=user.id,
            transcription=text,
            voice_file_id=voice.file_id,
        )

    except Exception as e:
        logger.error(f"Voice message error: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ Sorry, I couldn't process your voice message. Please try again."
        )


# TODO(#123): Add handlers for stickers, animations, and polls to give users
# a friendly "unsupported media type" response instead of silently dropping them.
