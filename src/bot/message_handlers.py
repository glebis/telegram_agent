import json
import logging
import os
import re
import traceback
from typing import Optional, List, Tuple
from telegram import Message, InlineKeyboardButton, InlineKeyboardMarkup

from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.image import Image
from ..services.image_service import get_image_service
from ..services.llm_service import get_llm_service
from ..services.similarity_service import get_similarity_service
from ..services.cache_service import get_cache_service
from ..services.link_service import get_link_service, track_capture
from ..services.voice_service import get_voice_service
from ..services.routing_memory import get_routing_memory
from ..services.image_classifier import get_image_classifier
from ..core.vector_db import get_vector_db
from ..utils.logging import (
    get_image_logger,
    log_image_processing_error,
    ImageProcessingLogContext,
)

# URL regex pattern
URL_PATTERN = re.compile(
    r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
    re.IGNORECASE
)

logger = logging.getLogger(__name__)
image_logger = get_image_logger("message_handlers")

# Check if we're in debug mode
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


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
    elif (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("image/")
    ):
        # Handle image documents
        file_id = message.document.file_id
        logger.info(
            f"Image document received: {file_id}, size: {message.document.file_size}"
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

        # Build explicit error message
        error_type = type(e).__name__
        error_msg = str(e)

        # Categorize errors for user-friendly messages
        if "AuthenticationError" in error_type or "api_key" in error_msg.lower():
            user_error = f"❌ API Authentication Error\n\nThe OpenAI API key is invalid or expired.\n\nDetails: {error_msg[:200]}"
        elif "RateLimitError" in error_type or "rate_limit" in error_msg.lower():
            user_error = "❌ Rate Limit Exceeded\n\nToo many requests. Please wait a minute and try again."
        elif "Timeout" in error_type or "timeout" in error_msg.lower():
            user_error = "❌ Request Timeout\n\nThe AI service took too long to respond. Please try again."
        elif "ConnectionError" in error_type or "connection" in error_msg.lower():
            user_error = "❌ Connection Error\n\nCouldn't connect to the AI service. Please check your internet connection."
        elif DEBUG_MODE:
            user_error = f"❌ Error: {error_type}\n\n{error_msg[:500]}"
        else:
            user_error = f"❌ Processing Error: {error_type}\n\nPlease try again or contact support if the issue persists."

        await processing_msg.edit_text(user_error)


async def process_image_with_llm(
    file_id: str,
    chat_id: int,
    user_id: int,
    mode: str,
    preset: Optional[str],
    message: Message,
    processing_msg: Message,
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
                classification = {"category": "other", "destination": "inbox", "provider": "default"}
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
            provider = classification.get("provider", "default")
            response_text += f"\n\n<i>Type: {category} | Route: {destination}</i>"

        # Delete processing message
        await processing_msg.delete()

        # Send new message with results first (we need the message_id for buttons)
        result_msg = await message.reply_text(
            response_text, parse_mode="HTML"
        )

        # Create routing buttons using result_msg.message_id (so callback can find tracked info)
        routing_keyboard = [
            [
                InlineKeyboardButton("Inbox", callback_data=f"img_route:inbox:{result_msg.message_id}"),
                InlineKeyboardButton("Media", callback_data=f"img_route:media:{result_msg.message_id}"),
            ],
            [
                InlineKeyboardButton("Expenses", callback_data=f"img_route:expenses:{result_msg.message_id}"),
                InlineKeyboardButton("Research", callback_data=f"img_route:research:{result_msg.message_id}"),
            ],
            [
                InlineKeyboardButton("Done", callback_data=f"img_route:done:{result_msg.message_id}"),
            ],
        ]
        routing_markup = InlineKeyboardMarkup(routing_keyboard)

        # Edit message to add buttons
        await result_msg.edit_reply_markup(reply_markup=routing_markup)

        # Track image for routing callback using result_msg.message_id
        track_capture(result_msg.message_id, {
            "path": processed_path,
            "original_path": analysis.get("original_path"),
            "category": classification.get("category", "other") if classification else "other",
            "destination": classification.get("destination", "inbox") if classification else "inbox",
            "file_id": file_id,
        })

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
                    if embedding_bytes:
                        try:
                            similar_images = (
                                await similarity_service.find_similar_images(
                                    image_id=saved_image_id,
                                    user_id=user_id,
                                    scope="user",
                                    limit=5,
                                    similarity_threshold=0.7,
                                )
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
                            # Update the analysis to indicate similarity search failed
                            analysis["similar_count"] = 0
                            analysis["similar_images"] = []
                            analysis["embedding_status"] = "similarity_search_failed"
                    else:
                        # No embedding available for similarity search
                        analysis["similar_count"] = 0
                        analysis["similar_images"] = []
                        analysis["embedding_status"] = "embedding_unavailable"

                        # Send a follow-up message about embedding failure
                        await message.reply_text(
                            "⚠️ Similar Images: Embedding generation failed - similarity search unavailable",
                            parse_mode="HTML",
                        )

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
        if DEBUG_MODE:
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
            return prefix.rstrip(":"), text[len(prefix):].strip()

    return None, text


async def handle_link_message(
    message: Message,
    urls: List[str],
    destination: Optional[str] = None,
) -> None:
    """Handle messages containing URLs - capture and save to Obsidian"""
    link_service = get_link_service()
    routing_memory = get_routing_memory()

    # Process only the first URL for now
    url = urls[0]

    # Get suggested destination from routing memory if not explicitly set
    if destination is None:
        destination = routing_memory.get_suggested_destination(url=url, content_type="links")
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
            track_capture(processing_msg.message_id, {
                "path": result['path'],
                "url": url,
                "title": result['title'],
                "destination": destination,
            })

            # Record the initial route (will be updated if user changes it)
            routing_memory.record_route(
                destination=destination,
                content_type="links",
                url=url,
                title=result['title']
            )

            # Create routing buttons - include message_id for tracking
            msg_id = processing_msg.message_id
            keyboard = [
                [
                    InlineKeyboardButton("Inbox", callback_data=f"route:inbox:{msg_id}"),
                    InlineKeyboardButton("Daily", callback_data=f"route:daily:{msg_id}"),
                ],
                [
                    InlineKeyboardButton("Research", callback_data=f"route:research:{msg_id}"),
                    InlineKeyboardButton("Done", callback_data=f"route:done:{msg_id}"),
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
            f"Error: {str(e)[:200]}\n\n"
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
        await handle_link_message(message, urls, destination)
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

    # Provide helpful responses for common queries
    text_lower = text.lower()

    if any(word in text_lower for word in ["help", "how", "what", "commands"]):
        await message.reply_text(
            "🤖 <b>Need help?</b>\n\n"
            "📸 <b>Images:</b> Send any image for AI analysis\n"
            "🔗 <b>Links:</b> Send a URL to capture the page\n"
            "🎤 <b>Voice:</b> Send voice message for transcription\n\n"
            "<b>Commands:</b>\n"
            "• <code>/help</code> - Detailed help\n"
            "• <code>/mode</code> - Change analysis mode\n\n"
            "<b>Prefixes:</b>\n"
            "• <code>inbox:</code> - Save to inbox\n"
            "• <code>research:</code> - Save to research folder\n"
            "• <code>task:</code> - Add as task\n",
            parse_mode="HTML",
        )

    elif any(word in text_lower for word in ["mode", "setting", "config"]):
        await message.reply_text(
            "⚙️ <b>Mode Information</b>\n\n"
            "Use <code>/mode</code> to see current mode and options.\n\n"
            "<b>Quick commands:</b>\n"
            "• <code>/mode default</code> - Quick descriptions\n"
            "• <code>/analyze</code> - Art analysis\n"
            "• <code>/coach</code> - Photography tips\n"
            "• <code>/creative</code> - Creative interpretation",
            parse_mode="HTML",
        )

    elif any(word in text_lower for word in ["image", "photo", "picture", "analyze"]):
        await message.reply_text(
            "📸 <b>Ready for image analysis!</b>\n\n"
            "Just send me any photo and I'll analyze it based on your current mode.\n\n"
            "Supported formats: JPG, PNG, WebP\n"
            "Max size: 10MB\n\n"
            "I can analyze photos, screenshots, artwork, diagrams, and more!",
            parse_mode="HTML",
        )

    elif any(word in text_lower for word in ["link", "url", "capture", "save"]):
        await message.reply_text(
            "🔗 <b>Link Capture</b>\n\n"
            "Send me any URL and I'll capture the full page content to your Obsidian vault.\n\n"
            "<b>Prefixes:</b>\n"
            "• Just send URL - saves to inbox\n"
            "• <code>research: URL</code> - saves to research folder\n"
            "• <code>inbox: URL</code> - saves to inbox\n",
            parse_mode="HTML",
        )

    else:
        # Generic response for other text
        await message.reply_text(
            "<b>I can help with:</b>\n\n"
            "<b>Images</b> - Send a photo for AI analysis\n"
            "<b>Links</b> - Send a URL to capture content\n"
            "<b>Voice</b> - Send voice message for transcription\n\n"
            "Type 'help' for more options",
            parse_mode="HTML",
        )


async def handle_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle voice messages - transcribe and route to Obsidian"""
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

    # Send processing message
    processing_msg = await message.reply_text(
        "Transcribing voice message..."
    )

    try:
        # Download voice file
        from ..bot.bot import get_bot

        bot_instance = get_bot()
        if not bot_instance or not bot_instance.application:
            raise RuntimeError("Bot instance not initialized")
        bot = bot_instance.application.bot

        file = await bot.get_file(voice.file_id)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            audio_path = tmp.name

        # Process voice message
        voice_service = get_voice_service()
        success, result = await voice_service.process_voice_message(audio_path)

        # Clean up temp file
        import os
        os.unlink(audio_path)

        if success:
            text = result["text"]
            intent = result["intent"]
            formatted = result["formatted_text"]
            destination = result["destination"]

            # Create routing buttons
            msg_id = processing_msg.message_id
            keyboard = [
                [
                    InlineKeyboardButton("Daily", callback_data=f"voice:daily:{msg_id}"),
                    InlineKeyboardButton("Inbox", callback_data=f"voice:inbox:{msg_id}"),
                ],
                [
                    InlineKeyboardButton("Task", callback_data=f"voice:task:{msg_id}"),
                    InlineKeyboardButton("Done", callback_data=f"voice:done:{msg_id}"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            intent_display = intent.get("intent", "quick").title()
            if intent.get("matched_keyword"):
                intent_display += f" ({intent['matched_keyword']})"

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

        else:
            error = result.get("error", "Unknown error")
            await processing_msg.edit_text(
                f"Transcription failed: {error}"
            )

    except Exception as e:
        logger.error(f"Voice message error: {e}", exc_info=True)
        await processing_msg.edit_text(
            f"Error processing voice message: {str(e)[:200]}"
        )
