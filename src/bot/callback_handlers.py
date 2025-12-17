import json
import logging
import os
import traceback
from typing import List

from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import (
    get_db_session,
    get_user_by_telegram_id,
    get_chat_by_telegram_id,
)
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
        elif action == "route":
            await handle_route_callback(query, params)
        elif action == "img_route":
            await handle_image_route_callback(query, params)
        elif action == "voice":
            await handle_voice_callback(query, params)
        elif action == "claude":
            await handle_claude_callback(query, user.id, chat.id, params)
        else:
            logger.warning(f"Unknown callback action: {action}")
            await query.message.reply_text("❌ Unknown action. Please try again.")

    except Exception as e:
        logger.error(f"Error handling callback query {action}: {e}")
        import traceback

        logger.error(f"Callback error details: {traceback.format_exc()}")
        await query.message.reply_text(
            "❌ Sorry, there was an error processing your request."
        )


async def handle_reanalyze_callback(query, file_id, params) -> None:
    """Handle image reanalysis with different mode"""
    logger.info(
        f"Starting reanalysis callback with file_id: {file_id}, params: {params}"
    )

    # Validate parameters
    if not file_id:
        logger.error("Reanalysis failed: Missing file_id")
        await query.message.reply_text(
            "❌ Invalid reanalysis request: Missing file ID."
        )
        return

    # Extract mode and preset from params
    new_mode = params[0] if len(params) > 0 else "default"
    new_preset = params[1] if len(params) > 1 else None

    # Extract local image path if provided in params
    local_image_path = params[2] if len(params) > 2 else None

    # Log detailed callback data parsing
    logger.info(
        f"Reanalysis request: file_id={file_id[:20] if file_id else 'None'}..., mode={new_mode}, preset={new_preset}"
    )
    logger.info(f"Local image path from callback: {local_image_path}")

    # Validate file_id format
    if file_id and len(file_id) < 10:
        logger.warning(
            f"Suspiciously short file_id: {file_id}, might be a hash instead of actual file_id"
        )
        # Try to get the real file_id from the callback manager
        original_file_id = callback_manager.get_file_id(file_id)
        if original_file_id:
            logger.info(
                f"Retrieved original file_id from hash: {original_file_id[:20]}..."
            )
            file_id = original_file_id

    logger.info(
        f"Reanalysis parameters: mode={new_mode}, preset={new_preset}, local_path={local_image_path or 'None'}"
    )
    if local_image_path:
        logger.info(
            f"Using provided local image path for reanalysis: {local_image_path}"
        )

    chat = query.message.chat
    user = query.from_user

    logger.info(
        f"Reanalyzing image {file_id} with mode: {new_mode}, preset: {new_preset}"
    )

    try:
        # Get services
        cache_service = get_cache_service()
        llm_service = get_llm_service()

        # Check if we have this analysis in cache
        logger.info(
            f"Checking cache for file_id={file_id}, mode={new_mode}, preset={new_preset}"
        )
        cached_analysis = await cache_service.get_cached_analysis(
            file_id, new_mode, new_preset
        )
        if cached_analysis:
            logger.info("Cache hit! Using cached analysis")
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
            return

        # Update mode in database first
        from sqlalchemy import select

        async with get_db_session() as session:
            try:
                user = await get_user_by_telegram_id(session, query.from_user.id)
                chat = await get_chat_by_telegram_id(session, query.message.chat.id)

                if not user or not chat:
                    logger.error(
                        f"User or chat not found in database. User ID: {query.from_user.id}, Chat ID: {query.message.chat.id}"
                    )
                    await query.message.reply_text(
                        "❌ User or chat not found in database."
                    )
                    return

                logger.info(f"Found user {user.id} and chat {chat.id} in database")

                # Update chat mode in database
                try:
                    chat.current_mode = new_mode
                    chat.current_preset = new_preset
                    await session.commit()
                    logger.info(
                        f"Updated chat {chat.id} mode to {new_mode} and preset to {new_preset}"
                    )
                except Exception as db_error:
                    logger.error(f"Error updating chat mode: {db_error}")
                    # Continue processing even if update fails
            except Exception as db_lookup_error:
                logger.error(
                    f"Database error during user/chat lookup: {db_lookup_error}"
                )
                import traceback

                logger.error(f"Database error details: {traceback.format_exc()}")
                await query.message.reply_text(
                    "❌ Database error. Please try again later."
                )
                return

        # Send new processing message instead of editing original
        mode_display = new_mode.title()
        if new_preset:
            mode_display += f" - {new_preset}"

        processing_text = f"🔄 Re-analyzing with <b>{mode_display}</b> mode...\n⏳ This may take a few seconds..."
        processing_message = await query.message.reply_text(
            processing_text, parse_mode="HTML"
        )

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

        # Get local image path if available from the database
        db_local_image_path = None
        try:
            async with get_db_session() as session:
                from ..models.image import Image

                # Query for image record
                logger.info(f"Searching for image record with file_id: {file_id}")
                result = await session.execute(
                    select(Image).where(Image.file_id == file_id)
                )
                image_record = result.scalar_one_or_none()

                if image_record:
                    logger.info(f"Found image record with ID: {image_record.id}")

                    # Check compressed path first
                    if image_record.compressed_path:
                        if os.path.exists(image_record.compressed_path):
                            db_local_image_path = image_record.compressed_path
                            logger.info(
                                f"Using compressed image path: {db_local_image_path}"
                            )
                        else:
                            logger.warning(
                                f"Compressed path exists in DB but file not found: {image_record.compressed_path}"
                            )

                    # Fall back to original path if compressed not available
                    if not db_local_image_path and image_record.original_path:
                        if os.path.exists(image_record.original_path):
                            db_local_image_path = image_record.original_path
                            logger.info(
                                f"Using original image path: {db_local_image_path}"
                            )
                        else:
                            logger.warning(
                                f"Original path exists in DB but file not found: {image_record.original_path}"
                            )

                    # Log if no valid paths found
                    if not db_local_image_path:
                        logger.warning(
                            f"No valid image paths found in database for file_id: {file_id}"
                        )
                else:
                    logger.warning(
                        f"No image record found in database for file_id: {file_id}"
                    )
        except Exception as db_error:
            logger.error(f"Error retrieving image paths from database: {db_error}")
            import traceback

            logger.error(f"Database lookup error details: {traceback.format_exc()}")

        # Process image with local path as fallback
        # Use the local_image_path from function parameters if available, otherwise use the one from database
        image_path_to_use = local_image_path or db_local_image_path

        try:
            # Log the path we're trying to use
            logger.info(
                f"Attempting to process image with path: {image_path_to_use or 'None (using file_id only)'}"
            )

            # Check if file_id is valid (not just a hash)
            if len(file_id) < 10:
                logger.warning(
                    f"Suspiciously short file_id: {file_id}, might be a hash instead of actual file_id"
                )

            # Make sure we have either a valid file_id or a local path
            if not file_id and not image_path_to_use:
                logger.error("No valid file_id or local image path available")
                await processing_message.edit_text(
                    "❌ Sorry, there was an error processing your request.\n\n"
                    "Could not find the original image. Please try sending the image again.",
                    parse_mode="HTML",
                )
                return

            # Pass mode and preset to process_image
            try:
                image_info = await image_service.process_image(
                    bot,
                    file_id,
                    mode=new_mode,
                    preset=new_preset,
                    local_image_path=image_path_to_use,
                )
                logger.info(f"Image processed successfully, info: {image_info.keys()}")
            except Exception as process_error:
                logger.error(f"Error in image_service.process_image: {process_error}")
                import traceback

                logger.error(
                    f"Image processing error details: {traceback.format_exc()}"
                )
                await processing_message.edit_text(
                    "❌ Sorry, there was an error processing your request.\n\n"
                    "Could not process the image. Please try sending the image again.",
                    parse_mode="HTML",
                )
                return

            # Verify the processed path exists
            if not image_info.get("processed_path") or not os.path.exists(
                image_info["processed_path"]
            ):
                logger.error(
                    f"Processed image path does not exist: {image_info.get('processed_path')}"
                )
                await processing_message.edit_text(
                    "❌ Sorry, there was an error processing your request.\n\n"
                    "The processed image file was not found. Please try sending the image again.",
                    parse_mode="HTML",
                )
                return

            # Analyze image with LLM
            # Read the image data from the file
            try:
                with open(image_info["processed_path"], "rb") as f:
                    image_data = f.read()

                # Log successful file reading
                logger.info(f"Successfully read image data: {len(image_data)} bytes")

                if len(image_data) == 0:
                    logger.error("Image data is empty")
                    await processing_message.edit_text(
                        "❌ Sorry, there was an error processing your request.\n\n"
                        "The image file is empty. Please try sending the image again.",
                        parse_mode="HTML",
                    )
                    return
            except Exception as file_error:
                logger.error(f"Error reading image file: {file_error}")
                import traceback

                logger.error(f"File reading error details: {traceback.format_exc()}")
                await processing_message.edit_text(
                    "❌ Sorry, there was an error processing your request.\n\n"
                    "Could not read the image file. Please try sending the image again.",
                    parse_mode="HTML",
                )
                return

        except FileNotFoundError as e:
            logger.error(f"File not found error: {e}")

            await processing_message.edit_text(
                "❌ Sorry, there was an error processing your request.\n\n"
                "The image file could not be found. Please try sending the image again.",
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.error(f"Error during image processing: {e}")

            await processing_message.edit_text(
                "❌ Sorry, there was an error processing your request.",
                parse_mode="HTML",
            )
            return

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

        # Edit the processing message to show completion
        await processing_message.edit_text(
            "✅ Re-analysis completed! Check the new message above.", parse_mode="HTML"
        )

        # Save new analysis to database
        from ..models.image import Image

        try:
            async with get_db_session() as session:
                # Get embedding bytes if available
                embedding_bytes = analysis.get("embedding_bytes")

                # Remove embedding_bytes from analysis before JSON serialization
                analysis_for_db = analysis.copy()
                analysis_for_db.pop("embedding_bytes", None)

                image_record = Image(
                    chat_id=chat.id,
                    file_id=file_id,
                    file_unique_id=analysis.get("telegram_file_info", {}).get(
                        "file_unique_id", f"unique_{file_id}"
                    ),
                    compressed_path=analysis.get("processed_path"),
                    width=analysis.get("dimensions", {}).get("processed", [0, 0])[0],
                    height=analysis.get("dimensions", {}).get("processed", [0, 0])[1],
                    embedding=embedding_bytes,  # Store embedding
                    analysis=json.dumps(
                        analysis_for_db
                    ),  # Store as proper JSON string without bytes
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

        # Send error message as new message instead of editing original
        await query.message.reply_text(error_message)


async def handle_mode_callback(query, params) -> None:
    """Handle mode change from inline keyboard"""

    if len(params) < 2:
        await query.message.reply_text("❌ Invalid mode selection.")
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
                elif new_mode == "formal":
                    preset_info = mode_manager.get_preset_info("formal", new_preset)
                    response_text = (
                        f"✅ <b>Mode switched to Formal - {new_preset}</b>\n\n"
                        f"📋 <b>Description:</b> {preset_info.get('description', 'Structured analysis')}\n"
                        f"📊 Detailed analysis with object detection\n"
                        f"🔍 Similar image search enabled\n"
                        f"🎯 Vector embeddings for smart matching"
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

                # Send new message instead of editing original
                await query.message.reply_text(
                    response_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup if reply_markup.inline_keyboard else None,
                )
            else:
                await query.message.reply_text(
                    "❌ Error updating mode. Please try again."
                )

    except Exception as e:
        logger.error(f"Error updating mode via callback: {e}")
        await query.message.reply_text("❌ Error updating mode. Please try again.")


async def handle_confirm_callback(query, params) -> None:
    """Handle confirmation callbacks"""

    if len(params) < 2:
        await query.message.reply_text("❌ Invalid confirmation request.")
        return

    action = params[0]
    data = params[1]

    # Handle different confirmation actions
    if action == "delete_chat":
        # Placeholder for future implementation
        await query.message.reply_text("✅ Action confirmed.")
    else:
        await query.message.reply_text("❌ Unknown confirmation action.")

    logger.info(f"Confirmed action: {action} with data: {data}")


async def handle_cancel_callback(query, params) -> None:
    """Handle cancellation callbacks"""

    action = params[0] if params else "unknown"

    await query.message.reply_text("❌ Action cancelled.")
    logger.info(f"Cancelled action: {action}")


async def handle_gallery_callback(query, user_id: int, params: List[str]) -> None:
    """Handle gallery-related callbacks"""

    if not params:
        await query.message.reply_text("❌ Invalid gallery action.")
        return

    gallery_action = params[0]

    try:
        from ..services.gallery_service import get_gallery_service

        gallery_service = get_gallery_service()
        keyboard_utils = get_keyboard_utils()

        if gallery_action == "page":
            # Navigate to a specific page
            if len(params) < 2:
                await query.message.reply_text("❌ Invalid page number.")
                return

            try:
                page = int(params[1])
            except ValueError:
                await query.message.reply_text("❌ Invalid page number.")
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
                await query.message.reply_text("❌ Invalid image ID.")
                return

            try:
                image_id = int(params[1])
            except ValueError:
                await query.message.reply_text("❌ Invalid image ID.")
                return

            # Get image details
            image_data = await gallery_service.get_image_by_id(image_id, user_id)

            if not image_data:
                await query.message.reply_text("❌ Image not found or access denied.")
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
                await query.message.reply_text("❌ Invalid reanalysis parameters.")
                return

            try:
                image_id = int(params[1])
                new_mode = params[2]
                new_preset = params[3] if params[3] else None
            except (ValueError, IndexError):
                await query.message.reply_text("❌ Invalid reanalysis parameters.")
                return

            # Get the image data to get file_id
            image_data = await gallery_service.get_image_by_id(image_id, user_id)
            if not image_data:
                await query.message.reply_text("❌ Image not found or access denied.")
                return

            # Send new processing message
            try:
                processing_message = await query.message.reply_text(
                    f"♻ Re-analyzing with {new_mode.capitalize()}{' - ' + new_preset if new_preset else ''} mode...\n\n"
                    "⌛ This may take a few seconds...",
                    parse_mode="HTML",
                )
                logger.info("Sent processing message")
            except Exception as msg_error:
                logger.error(f"Error sending processing message: {msg_error}")
                import traceback

                logger.error(f"Message error details: {traceback.format_exc()}")
                await query.answer("Error sending message. Please try again.")
                return

            # Get local image path if available
            local_image_path = None
            if image_data.get("compressed_path") and os.path.exists(
                image_data["compressed_path"]
            ):
                local_image_path = image_data["compressed_path"]
                local_image_path = image_data["original_path"]

            logger.info(
                f"Re-analyzing image from gallery with local path: {local_image_path}"
            )

            # Trigger reanalysis using the existing reanalysis logic
            # Pass the local image path as an additional parameter
            params = [new_mode, new_preset or "", local_image_path or ""]
            await handle_reanalyze_callback(query, image_data["file_id"], params)

        elif gallery_action == "menu":
            # Return to main menu (show help or start message) - send new message
            await query.message.reply_text(
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
            await query.message.reply_text(
                f"❌ Unknown gallery action: {gallery_action}"
            )

    except Exception as e:
        logger.error(f"Error handling gallery callback {gallery_action}: {e}")
        await query.message.reply_text(
            "❌ Sorry, there was an error processing your gallery request."
        )


async def handle_route_callback(query, params) -> None:
    """Handle routing callbacks for captured links/content"""
    from ..services.link_service import get_link_service, get_tracked_capture
    from ..services.routing_memory import get_routing_memory

    if not params:
        await query.message.reply_text("Invalid routing action.")
        return

    route_action = params[0]
    message_id = int(params[1]) if len(params) > 1 and params[1].isdigit() else None

    logger.info(f"Route callback: action={route_action}, message_id={message_id}")

    try:
        if route_action == "done":
            # User confirmed current routing - just acknowledge
            await query.edit_message_reply_markup(reply_markup=None)
            return

        # Route actions: inbox, daily, research
        destination = route_action

        valid_destinations = ["inbox", "daily", "research", "expenses", "media"]

        if destination not in valid_destinations:
            await query.message.reply_text(f"Unknown destination: {destination}")
            return

        destination_labels = {
            "inbox": "Inbox",
            "daily": "Daily",
            "research": "Research",
            "expenses": "Expenses",
            "media": "Media"
        }
        label = destination_labels.get(destination, destination)

        # Get tracked capture info and move file
        if message_id:
            capture_info = get_tracked_capture(message_id)
            if capture_info:
                # capture_info is now a dict: {path, url, title, destination}
                if isinstance(capture_info, dict):
                    file_path = capture_info.get("path")
                    url = capture_info.get("url")
                    title = capture_info.get("title")
                else:
                    # Backwards compatibility: old format was just a string path
                    file_path = capture_info
                    url = None
                    title = None

                if file_path:
                    link_service = get_link_service()
                    success, result = await link_service.move_to_destination(
                        file_path, destination
                    )

                    if success:
                        # Record user's routing choice to learn from it
                        routing_memory = get_routing_memory()
                        routing_memory.record_route(
                            destination=destination,
                            content_type="links",
                            url=url,
                            title=title
                        )
                        await query.edit_message_reply_markup(reply_markup=None)
                        await query.message.reply_text(f"Moved to {label}.")
                        logger.info(f"Moved {file_path} to {destination}, recorded route")
                    else:
                        await query.message.reply_text(f"Move failed: {result}")
                        logger.error(f"Move failed: {result}")
                else:
                    await query.edit_message_reply_markup(reply_markup=None)
                    await query.message.reply_text(f"Routed to {label}.")
            else:
                # File not tracked, just acknowledge
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(f"Routed to {label}.")
        else:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"Routed to {label}.")

        logger.info(f"Content routed to {destination}")

    except Exception as e:
        logger.error(f"Error handling route callback: {e}")
        await query.message.reply_text("Error processing routing request.")


async def handle_voice_callback(query, params) -> None:
    """Handle voice transcription routing callbacks"""
    from ..services.link_service import get_tracked_capture
    from datetime import datetime
    from pathlib import Path
    import yaml

    if not params:
        await query.message.reply_text("Invalid voice action.")
        return

    action = params[0]
    message_id = int(params[1]) if len(params) > 1 and params[1].isdigit() else None

    logger.info(f"Voice callback: action={action}, message_id={message_id}")

    try:
        if action == "done":
            await query.edit_message_reply_markup(reply_markup=None)
            return

        # Get formatted transcription
        formatted_text = get_tracked_capture(message_id) if message_id else None

        if not formatted_text:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("Transcription not found.")
            return

        # Load config for paths
        config_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except Exception:
            config = {"obsidian": {"vault_path": "~/Research/vault"}}

        vault_path = Path(config.get("obsidian", {}).get("vault_path", "~/Research/vault")).expanduser()

        # Handle task conversion
        if action == "task":
            # Convert to task format if not already
            if not formatted_text.startswith("- [ ]"):
                text = formatted_text.lstrip("- ").split(" ", 1)[-1] if formatted_text.startswith("- ") else formatted_text
                formatted_text = f"- [ ] {text}"

        # Determine destination file
        if action in ["daily", "task"]:
            # Append to daily note
            today = datetime.now().strftime("%Y%m%d")
            daily_path = vault_path / "Daily" / f"{today}.md"

            if daily_path.exists():
                # Append to log section
                with open(daily_path, "a", encoding="utf-8") as f:
                    f.write(f"\n{formatted_text}")
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(f"Added to daily note.")
            else:
                await query.message.reply_text(f"Daily note not found: {today}.md")

        elif action == "inbox":
            # Save as new note in inbox
            inbox_path = vault_path / "inbox"
            inbox_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            note_path = inbox_path / f"Voice_{timestamp}.md"

            content = f"""---
captured: "{datetime.now().isoformat()}"
source: telegram_voice
tags: [voice, capture]
---

{formatted_text}
"""
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(content)

            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"Saved to inbox.")

        else:
            await query.message.reply_text(f"Unknown action: {action}")

    except Exception as e:
        logger.error(f"Error handling voice callback: {e}")
        await query.message.reply_text("Error saving transcription.")


async def handle_image_route_callback(query, params) -> None:
    """Handle image routing callbacks - move image to Obsidian vault folders"""
    from ..services.link_service import get_tracked_capture
    from ..services.routing_memory import get_routing_memory
    from datetime import datetime
    from pathlib import Path
    import yaml
    import shutil

    if not params:
        await query.message.reply_text("Invalid image route action.")
        return

    action = params[0]
    message_id = int(params[1]) if len(params) > 1 and params[1].isdigit() else None

    logger.info(f"Image route callback: action={action}, message_id={message_id}")

    try:
        if action == "done":
            await query.edit_message_reply_markup(reply_markup=None)
            return

        # Get tracked image info
        image_info = get_tracked_capture(message_id) if message_id else None

        if not image_info or not isinstance(image_info, dict):
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("Image info not found.")
            return

        # Load config for paths
        config_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except Exception:
            config = {"obsidian": {"vault_path": "~/Research/vault"}}

        vault_path = Path(config.get("obsidian", {}).get("vault_path", "~/Research/vault")).expanduser()

        # Map action to destination folder
        destination_map = {
            "inbox": "inbox",
            "media": "media",
            "expenses": "expenses",
            "research": "research",
        }

        destination = destination_map.get(action)
        if not destination:
            await query.message.reply_text(f"Unknown destination: {action}")
            return

        # Get source image path
        source_path = image_info.get("path") or image_info.get("original_path")
        if not source_path or not Path(source_path).exists():
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("Image file not found.")
            return

        # Create destination directory
        dest_dir = vault_path / destination / "images"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        category = image_info.get("category", "image")
        source_file = Path(source_path)
        dest_filename = f"{category}_{timestamp}{source_file.suffix}"
        dest_path = dest_dir / dest_filename

        # Copy image to destination
        shutil.copy2(source_path, dest_path)

        # Record routing choice for learning
        routing_memory = get_routing_memory()
        routing_memory.record_route(
            destination=destination,
            content_type="images",
            url=None,
            title=f"{category} image"
        )

        logger.info(f"Image routed: {source_path} -> {dest_path}")

        # Update message
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"Image saved to {destination}/images/{dest_filename}"
        )

    except Exception as e:
        logger.error(f"Error handling image route callback: {e}")
        await query.message.reply_text("Error routing image.")


async def handle_claude_callback(query, user_id: int, chat_id: int, params) -> None:
    """Handle Claude Code session callbacks."""
    from ..services.claude_code_service import (
        get_claude_code_service,
        is_claude_code_admin,
    )

    if not params:
        await query.message.reply_text("Invalid Claude action.")
        return

    action = params[0]
    logger.info(f"Claude callback: action={action}, user={user_id}, chat={chat_id}")

    # Check admin permission
    if not await is_claude_code_admin(chat_id):
        await query.message.reply_text("You don't have permission to use Claude Code.")
        return

    service = get_claude_code_service()
    keyboard_utils = get_keyboard_utils()

    try:
        if action == "new":
            # End current session and prepare for new one
            await service.end_session(chat_id)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "New session ready. Send a prompt with:\n"
                "<code>/claude &lt;your prompt&gt;</code>",
                parse_mode="HTML",
            )

        elif action == "continue":
            # Show current session info
            session_id = await service.get_active_session(chat_id)
            if session_id:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(
                    f"Continuing session {session_id[:8]}...\n\n"
                    "Send your next prompt with:\n"
                    "<code>/claude &lt;your prompt&gt;</code>",
                    parse_mode="HTML",
                )
            else:
                await query.message.reply_text(
                    "No active session. Start a new one with:\n"
                    "<code>/claude &lt;your prompt&gt;</code>",
                    parse_mode="HTML",
                )

        elif action == "list":
            # Show session list
            sessions = await service.get_user_sessions(chat_id)
            active_session = await service.get_active_session(chat_id)

            if not sessions:
                await query.edit_message_text(
                    "<b>📋 Session History</b>\n\n"
                    "No sessions found.\n\n"
                    "Start one with:\n"
                    "<code>/claude &lt;your prompt&gt;</code>",
                    parse_mode="HTML",
                    reply_markup=keyboard_utils.create_claude_action_keyboard(False),
                )
                return

            reply_markup = keyboard_utils.create_claude_sessions_keyboard(
                sessions, active_session
            )
            await query.edit_message_text(
                f"<b>📋 Session History</b>\n\n"
                f"Select session to resume:",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        elif action == "end":
            # End current session
            ended = await service.end_session(chat_id)
            await query.edit_message_reply_markup(reply_markup=None)
            if ended:
                await query.message.reply_text("Session ended.")
            else:
                await query.message.reply_text("No active session to end.")

        elif action.startswith("select:"):
            # Select/resume a session
            session_id_prefix = action.split(":", 1)[1]

            # Find full session ID
            sessions = await service.get_user_sessions(chat_id)
            matching_session = None
            for s in sessions:
                if s.session_id.startswith(session_id_prefix):
                    matching_session = s
                    break

            if matching_session:
                await service.set_active_session(chat_id, matching_session.session_id)
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(
                    f"Switched to session {matching_session.session_id[:8]}...\n\n"
                    f"Last prompt: {(matching_session.last_prompt or 'None')[:50]}...\n\n"
                    "Continue with:\n"
                    "<code>/claude &lt;your prompt&gt;</code>",
                    parse_mode="HTML",
                )
            else:
                await query.message.reply_text("Session not found.")

        elif action == "cancel":
            await query.edit_message_reply_markup(reply_markup=None)

        elif action == "back":
            # Go back to main Claude menu
            active_session = await service.get_active_session(chat_id)
            last_prompt = None
            if active_session:
                sessions = await service.get_user_sessions(chat_id, limit=1)
                if sessions:
                    last_prompt = sessions[0].last_prompt

            reply_markup = keyboard_utils.create_claude_action_keyboard(
                has_active_session=bool(active_session)
            )

            if active_session:
                short_id = active_session[:8]
                prompt_preview = (last_prompt or "No prompt")[:40]
                status_text = (
                    f"<b>🤖 Claude Code</b>\n\n"
                    f"▶️ Session: <code>{short_id}...</code>\n"
                    f"Last: <i>{prompt_preview}...</i>\n\n"
                    f"Send prompt to continue, or:"
                )
            else:
                status_text = (
                    f"<b>🤖 Claude Code</b>\n\n"
                    f"No active session\n"
                    f"Work dir: <code>~/Research/vault</code>\n\n"
                    f"Send a prompt or tap below:"
                )

            await query.edit_message_text(
                status_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        elif action == "retry":
            # Retry last prompt
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "To retry, send the prompt again or use:\n"
                "<code>/claude &lt;your prompt&gt;</code>",
                parse_mode="HTML",
            )

        elif action == "stop":
            # Note: Actually stopping execution is complex - would need async task management
            # For now, just acknowledge and remove keyboard
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("⏹️ Stop requested. The process may continue in background.")

        else:
            logger.warning(f"Unknown Claude action: {action}")
            await query.message.reply_text(f"Unknown action: {action}")

    except Exception as e:
        logger.error(f"Error handling Claude callback {action}: {e}")
        await query.message.reply_text("Error processing Claude action.")
