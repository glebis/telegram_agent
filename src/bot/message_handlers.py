import json
import logging
import os
import traceback
from typing import Optional
from telegram import Message

from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.image import Image
from ..services.image_service import get_image_service
from ..services.llm_service import get_llm_service
from ..services.similarity_service import get_similarity_service
from ..services.cache_service import get_cache_service
from ..core.vector_db import get_vector_db

logger = logging.getLogger(__name__)

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
        logger.error(f"Error processing image: {e}")
        await processing_msg.edit_text(
            "❌ Sorry, there was an error processing your image. Please try again later."
        )


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

        # Add metadata
        analysis["cached"] = False

        # Similarity search will be handled after saving to database
        analysis["similar_count"] = 0

        # Format response for Telegram with keyboard
        response_text, reply_markup = llm_service.format_telegram_response(
            analysis, include_keyboard=True
        )

        # Validate response format
        if not isinstance(response_text, str):
            logger.error(f"Invalid response_text type: {type(response_text)}")
            raise ValueError(f"Expected string, got {type(response_text)}")

        # Delete processing message
        await processing_msg.delete()

        # Send new message with results and keyboard
        await message.reply_text(
            response_text, parse_mode="HTML", reply_markup=reply_markup
        )

        # Save to database
        try:
            async with get_db_session() as session:
                # Get embedding bytes if available
                embedding_bytes = analysis.get("embedding_bytes")

                image_record = Image(
                    chat_id=chat_id,
                    file_id=file_id,
                    file_unique_id=analysis.get("telegram_file_info", {}).get(
                        "file_unique_id", f"unique_{file_id}"
                    ),
                    file_path=analysis.get("processed_path"),
                    width=analysis.get("dimensions", {}).get("processed", [0, 0])[0],
                    height=analysis.get("dimensions", {}).get("processed", [0, 0])[1],
                    embedding=embedding_bytes,  # Store embedding
                    analysis=json.dumps(analysis),  # Store as proper JSON string
                    mode_used=mode,
                    preset_used=preset,
                    processing_status="completed",
                )
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
                    except Exception as e:
                        logger.error(f"Error storing embedding in vector database: {e}")

                # Search for similar images if in artistic mode
                if mode == "artistic" and embedding_bytes:
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
                        # Keep the original response if similarity search fails

        except Exception as e:
            logger.error(f"Error saving image analysis: {e}")
            # Don't fail the whole process if database save fails

    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_msg = str(e)
        stack_trace = traceback.format_exc()

        # Log detailed error
        logger.error(f"Error in LLM image processing: {error_type}: {error_msg}")
        logger.error(f"Stack trace: {stack_trace}")

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

    # Provide helpful responses for common queries
    text_lower = text.lower()

    if any(word in text_lower for word in ["help", "how", "what", "commands"]):
        await message.reply_text(
            "🤖 **Need help?**\n\n"
            "• Send me any image and I'll analyze it!\n"
            "• Use `/help` for detailed command information\n"
            "• Use `/mode` to change analysis modes\n"
            "• Try `/analyze`, `/coach`, or `/creative` for quick mode switching\n\n"
            "What would you like to know more about?"
        )

    elif any(word in text_lower for word in ["mode", "setting", "config"]):
        await message.reply_text(
            "⚙️ **Mode Information**\n\n"
            "Use `/mode` to see your current mode and available options.\n\n"
            "Quick commands:\n"
            "• `/mode default` - Quick descriptions\n"
            "• `/analyze` - Art analysis\n"
            "• `/coach` - Photography tips\n"
            "• `/creative` - Creative interpretation"
        )

    elif any(word in text_lower for word in ["image", "photo", "picture", "analyze"]):
        await message.reply_text(
            "📸 **Ready for image analysis!**\n\n"
            "Just send me any photo and I'll analyze it based on your current mode.\n\n"
            "Supported formats: JPG, PNG, WebP\n"
            "Max size: 10MB\n\n"
            "I can analyze photos, screenshots, artwork, diagrams, and more!"
        )

    else:
        # Generic response for other text
        await message.reply_text(
            "💬 Thanks for your message! I'm specialized in image analysis.\n\n"
            "📸 Send me an image to analyze\n"
            "❓ Type 'help' for assistance\n"
            "⚙️ Use `/mode` to change settings"
        )
