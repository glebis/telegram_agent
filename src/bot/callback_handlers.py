import json
import logging
import os
import traceback
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import get_db_session
from ..core.mode_manager import ModeManager
from ..models.chat import Chat
from ..services.image_service import get_image_service
from ..services.llm_service import get_llm_service
from ..services.cache_service import get_cache_service
from ..services.similarity_service import get_similarity_service
from ..core.vector_db import get_vector_db
from .callback_data_manager import get_callback_data_manager
from .keyboard_utils import get_keyboard_utils

logger = logging.getLogger(__name__)

# Check if we're in debug mode
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle all callback queries from inline keyboards"""

    query = update.callback_query
    if not query:
        return

    # Always answer callback query to remove loading state
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat or not query.data:
        return

    logger.info(f"Callback query from user {user.id}: {query.data}")

    # Parse callback data using the callback data manager
    callback_manager = get_callback_data_manager()
    keyboard_utils = get_keyboard_utils()

    # Try new callback data format first
    action, file_id, params = callback_manager.parse_callback_data(query.data)

    # If file_id is None, fall back to old format for compatibility
    if file_id is None:
        action, old_params = keyboard_utils.parse_callback_data(query.data)
        params = old_params
        file_id = params[0] if params else None

    try:
        if action == "reanalyze":
            await handle_reanalyze_callback(query, file_id, params)
        elif action == "mode":
            await handle_mode_callback(query, params)
        elif action == "confirm":
            await handle_confirm_callback(query, params)
        elif action == "cancel":
            await handle_cancel_callback(query, params)
        elif action == "gallery":
            await handle_gallery_callback(query, user.id, params)
        else:
            logger.warning(f"Unknown callback action: {action}")
            await query.edit_message_text("❌ Unknown action. Please try again.")

    except Exception as e:
        logger.error(f"Error handling callback query {action}: {e}")
        await query.edit_message_text(
            "❌ Sorry, there was an error processing your request."
        )


async def handle_reanalyze_callback(query, file_id, params) -> None:
    """Handle image reanalysis with different mode"""

    if not file_id or len(params) < 2:
        await query.edit_message_text("❌ Invalid reanalysis request.")
        return

    new_mode = params[0]
    new_preset = params[1] if len(params) > 1 and params[1] else None

    chat = query.message.chat
    user = query.from_user

    logger.info(
        f"Reanalyzing image {file_id} with mode: {new_mode}, preset: {new_preset}"
    )

    try:
        # Get services
        cache_service = get_cache_service()
        llm_service = get_llm_service()

        # Check cache first
        cached_analysis = await cache_service.get_cached_analysis(
            file_id, new_mode, new_preset
        )
        if cached_analysis:
            logger.info(
                f"Using cached reanalysis for file_id={file_id}, mode={new_mode}, preset={new_preset}"
            )

            # Format cached response
            response_text, reply_markup = llm_service.format_telegram_response(
                cached_analysis, include_keyboard=True
            )

            # Send new message with cached results
            await query.message.reply_text(
                f"💾 {response_text}",  # Add cache indicator
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

            # Update the original message to show it was processed
            await query.edit_message_text(
                "✅ Analysis completed! Check the new message above.", parse_mode="HTML"
            )
            return

        # Update mode in database first
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_record = result.scalar_one_or_none()

            if chat_record:
                chat_record.current_mode = new_mode
                chat_record.current_preset = new_preset
                await session.commit()

        # Show processing message
        mode_display = new_mode.title()
        if new_preset:
            mode_display += f" - {new_preset}"

        processing_text = f"🔄 Re-analyzing with <b>{mode_display}</b> mode...\n⏳ This may take a few seconds..."
        await query.edit_message_text(processing_text, parse_mode="HTML")

        # Get bot instance for downloading images
        from ..bot.bot import get_bot

        bot_instance = get_bot()
        bot = bot_instance.application.bot

        # Get services
        image_service = get_image_service()
        similarity_service = get_similarity_service()
        vector_db = get_vector_db()

        import time

        start_time = time.time()

        # Download and process image
        image_info = await image_service.process_image(bot, file_id)

        # Analyze image with LLM
        # Read the image data from the file
        with open(image_info["processed_path"], "rb") as f:
            image_data = f.read()

        analysis = await llm_service.analyze_image(
            image_data=image_data, mode=new_mode, preset=new_preset
        )

        # Add metadata
        analysis["file_id"] = file_id
        analysis["mode"] = new_mode
        analysis["preset"] = new_preset
        analysis["processing_time"] = time.time() - start_time
        analysis["cached"] = False

        # Search for similar images if in artistic mode
        if new_mode == "artistic" and analysis.get("embedding_bytes"):
            similar_images = await similarity_service.find_similar_images(
                embedding_bytes=analysis["embedding_bytes"],
                user_id=user.id,
                scope="user",
                limit=5,
                similarity_threshold=0.7,
            )
            analysis["similar_count"] = len(similar_images)
            analysis["similar_images"] = similar_images
        else:
            analysis["similar_count"] = 0

        # Format response with keyboard for further reanalysis
        response_text, reply_markup = llm_service.format_telegram_response(
            analysis, include_keyboard=True
        )

        # Send new message with results
        await query.message.reply_text(
            response_text, parse_mode="HTML", reply_markup=reply_markup
        )

        # Update the original message to show it was processed
        await query.edit_message_text(
            "✅ Re-analysis completed! Check the new message above.", parse_mode="HTML"
        )

        # Save new analysis to database
        from ..models.image import Image

        try:
            async with get_db_session() as session:
                # Get embedding bytes if available
                embedding_bytes = analysis.get("embedding_bytes")

                image_record = Image(
                    chat_id=chat.id,
                    file_id=file_id,
                    file_unique_id=analysis.get("telegram_file_info", {}).get(
                        "file_unique_id", f"unique_{file_id}"
                    ),
                    file_path=analysis.get("processed_path"),
                    width=analysis.get("dimensions", {}).get("processed", [0, 0])[0],
                    height=analysis.get("dimensions", {}).get("processed", [0, 0])[1],
                    embedding=embedding_bytes,  # Store embedding
                    analysis=json.dumps(analysis),  # Store as proper JSON string
                    mode_used=new_mode,
                    preset_used=new_preset,
                    processing_status="completed",
                )
                session.add(image_record)
                await session.commit()

                # Get the saved image ID for vector database
                await session.refresh(image_record)
                saved_image_id = image_record.id

                logger.info(
                    f"Saved reanalysis for file_id: {file_id}, image_id: {saved_image_id}"
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

        except Exception as e:
            logger.error(f"Error saving reanalysis: {e}")
            # Don't fail the process if database save fails

    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_msg = str(e)
        stack_trace = traceback.format_exc()

        # Log detailed error
        logger.error(f"Error reanalyzing image: {error_type}: {error_msg}")
        logger.error(f"Stack trace: {stack_trace}")

        # Prepare user-facing message
        if DEBUG_MODE:
            # In debug mode, show more detailed error
            error_message = (
                f"❌ Error re-analyzing image: {error_type}\n\n"
                f"Message: {error_msg}\n\n"
                f"This detailed error is shown because DEBUG=true"
            )
            # Also print to console for immediate visibility
            print(
                f"\n{'='*50}\nIMAGE REANALYSIS ERROR (DEBUG MODE):\n{error_type}: {error_msg}\n{'='*50}\n"
            )
        else:
            # In production, show generic message
            error_message = "❌ Sorry, there was an error re-analyzing your image."

        # Send error message
        await query.edit_message_text(error_message)


async def handle_mode_callback(query, params) -> None:
    """Handle mode change from inline keyboard"""

    if len(params) < 2:
        await query.edit_message_text("❌ Invalid mode selection.")
        return

    new_mode = params[0]
    new_preset = params[1] if params[1] else None

    chat = query.message.chat
    user = query.from_user

    logger.info(f"Mode change via callback: {new_mode}, preset: {new_preset}")

    try:
        # Update mode in database
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
            chat_record = result.scalar_one_or_none()

            if not chat_record:
                # Initialize user/chat if not exists
                from .handlers import initialize_user_chat

                await initialize_user_chat(user.id, chat.id, user.username)
                result = await session.execute(
                    select(Chat).where(Chat.chat_id == chat.id)
                )
                chat_record = result.scalar_one_or_none()

            if chat_record:
                chat_record.current_mode = new_mode
                chat_record.current_preset = new_preset
                await session.commit()

                # Success message
                mode_manager = ModeManager()

                if new_mode == "default":
                    response_text = (
                        "✅ <b>Mode switched to Default</b>\n\n"
                        "📝 Quick descriptions (≤40 words)\n"
                        "📄 Text extraction from images\n"
                        "⚡ Fast processing, no similarity search"
                    )
                else:  # artistic
                    preset_info = mode_manager.get_preset_info("artistic", new_preset)
                    response_text = (
                        f"✅ <b>Mode switched to Artistic - {new_preset}</b>\n\n"
                        f"📋 <b>Description:</b> {preset_info.get('description', 'Advanced analysis')}\n"
                        f"📝 Detailed analysis (100-150 words)\n"
                        f"🔍 Similar image search enabled\n"
                        f"🎨 Vector embeddings for smart matching"
                    )

                # Create keyboard for additional mode changes
                keyboard_utils = get_keyboard_utils()
                reply_markup = keyboard_utils.create_mode_selection_keyboard(
                    new_mode, new_preset
                )

                await query.edit_message_text(
                    response_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup if reply_markup.inline_keyboard else None,
                )
            else:
                await query.edit_message_text(
                    "❌ Error updating mode. Please try again."
                )

    except Exception as e:
        logger.error(f"Error updating mode via callback: {e}")
        await query.edit_message_text("❌ Error updating mode. Please try again.")


async def handle_confirm_callback(query, params) -> None:
    """Handle confirmation callbacks"""

    if len(params) < 2:
        await query.edit_message_text("❌ Invalid confirmation request.")
        return

    action = params[0]
    data = params[1]

    # Handle different confirmation actions
    if action == "delete_chat":
        # Placeholder for future implementation
        await query.edit_message_text("✅ Action confirmed.")
    else:
        await query.edit_message_text("❌ Unknown confirmation action.")

    logger.info(f"Confirmed action: {action} with data: {data}")


async def handle_cancel_callback(query, params) -> None:
    """Handle cancellation callbacks"""

    action = params[0] if params else "unknown"

    await query.edit_message_text("❌ Action cancelled.")
    logger.info(f"Cancelled action: {action}")


async def handle_gallery_callback(query, user_id: int, params: List[str]) -> None:
    """Handle gallery-related callbacks"""

    if not params:
        await query.edit_message_text("❌ Invalid gallery action.")
        return

    gallery_action = params[0]

    try:
        from ..services.gallery_service import get_gallery_service

        gallery_service = get_gallery_service()
        keyboard_utils = get_keyboard_utils()

        if gallery_action == "page":
            # Navigate to a specific page
            if len(params) < 2:
                await query.edit_message_text("❌ Invalid page number.")
                return

            try:
                page = int(params[1])
            except ValueError:
                await query.edit_message_text("❌ Invalid page number.")
                return

            # Get paginated images
            images, total_images, total_pages = (
                await gallery_service.get_user_images_paginated(
                    user_id=user_id, page=page
                )
            )

            # Format response
            response_text = gallery_service.format_gallery_page(
                images=images,
                page=page,
                total_pages=total_pages,
                total_images=total_images,
            )

            # Create navigation keyboard
            reply_markup = keyboard_utils.create_gallery_navigation_keyboard(
                images=images, page=page, total_pages=total_pages
            )

            await query.edit_message_text(
                response_text, parse_mode="HTML", reply_markup=reply_markup
            )

        elif gallery_action == "view":
            # View individual image details
            if len(params) < 2:
                await query.edit_message_text("❌ Invalid image ID.")
                return

            try:
                image_id = int(params[1])
            except ValueError:
                await query.edit_message_text("❌ Invalid image ID.")
                return

            # Get image details
            image_data = await gallery_service.get_image_by_id(image_id, user_id)

            if not image_data:
                await query.edit_message_text("❌ Image not found or access denied.")
                return

            # Format detailed response
            response_text = gallery_service.format_image_details(image_data)

            # Create detail keyboard with reanalysis options
            # Try to get page from query message (fallback to page 1)
            page = 1
            reply_markup = keyboard_utils.create_image_detail_keyboard(
                image_id=image_id,
                current_mode=image_data["mode_used"],
                current_preset=image_data["preset_used"],
                page=page,
            )

            await query.edit_message_text(
                response_text, parse_mode="HTML", reply_markup=reply_markup
            )

        elif gallery_action == "reanalyze":
            # Reanalyze image with different mode
            if len(params) < 4:
                await query.edit_message_text("❌ Invalid reanalysis parameters.")
                return

            try:
                image_id = int(params[1])
                new_mode = params[2]
                new_preset = params[3] if params[3] else None
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Invalid reanalysis parameters.")
                return

            # Get the image data to get file_id
            image_data = await gallery_service.get_image_by_id(image_id, user_id)
            if not image_data:
                await query.edit_message_text("❌ Image not found or access denied.")
                return

            # Send processing message
            await query.edit_message_text(
                f"🔄 Reanalyzing image with {new_mode.title()}"
                f"{f' - {new_preset}' if new_preset else ''} mode...\n"
                f"⏳ This may take a few seconds..."
            )

            # Trigger reanalysis using the existing reanalysis logic
            await handle_reanalyze_callback(
                query, image_data["file_id"], [new_mode, new_preset or ""]
            )

        elif gallery_action == "menu":
            # Return to main menu (show help or start message)
            await query.edit_message_text(
                "🏠 <b>Main Menu</b>\n\n"
                "• Send me an image to analyze\n"
                "• Use /gallery to browse your images\n"
                "• Use /mode to change analysis modes\n"
                "• Use /help for detailed information",
                parse_mode="HTML",
            )

        elif gallery_action == "noop":
            # No-op for non-clickable buttons (like page indicator)
            pass

        else:
            await query.edit_message_text(
                f"❌ Unknown gallery action: {gallery_action}"
            )

    except Exception as e:
        logger.error(f"Error handling gallery callback {gallery_action}: {e}")
        await query.edit_message_text(
            "❌ Sorry, there was an error processing your gallery request."
        )
