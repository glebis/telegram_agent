import logging
from typing import Optional

from fastapi import BackgroundTasks
from telegram import Update
from telegram.ext import ContextTypes

from ..core.database import get_db_session
from ..core.mode_manager import ModeManager
from ..models.chat import Chat
from ..models.image import Image

logger = logging.getLogger(__name__)


async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        # Handle image documents
        file_id = message.document.file_id
        logger.info(f"Image document received: {file_id}, size: {message.document.file_size}")
    
    if not file_id:
        await message.reply_text("❌ No image found in your message. Please send a photo.")
        return
    
    # Check file size (Telegram limit is 20MB for photos, 50MB for documents)
    mode_manager = ModeManager()
    max_size_mb = 10  # Our processing limit
    
    if hasattr(message, 'document') and message.document and message.document.file_size:
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
        async with get_db_session() as session:
            chat_record = await session.get(Chat, chat.id)
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
    
    # Queue background image processing
    # For now, we'll simulate the processing
    try:
        # This is where we would queue the actual image processing
        # For now, let's create a placeholder response
        await simulate_image_processing(
            file_id=file_id,
            chat_id=chat.id,
            user_id=user.id,
            mode=current_mode,
            preset=current_preset,
            message=message,
            processing_msg=processing_msg
        )
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        await processing_msg.edit_text(
            "❌ Sorry, there was an error processing your image. Please try again later."
        )


async def simulate_image_processing(
    file_id: str,
    chat_id: int,
    user_id: int,
    mode: str,
    preset: Optional[str],
    message,
    processing_msg
) -> None:
    """Simulate image processing (placeholder for actual implementation)"""
    
    mode_manager = ModeManager()
    
    # Get the appropriate prompt
    prompt = mode_manager.get_mode_prompt(mode, preset)
    
    # Simulate analysis based on mode
    if mode == "default":
        analysis = {
            "description": "A beautiful landscape photo showing mountains and sky. Clear composition with good lighting.",
            "text_extracted": None,
            "mode": mode,
            "processing_time": 2.3
        }
        
        response = f"📸 **Image Analysis (Default Mode)**\n\n"
        response += f"**Description:** {analysis['description']}\n\n"
        if analysis['text_extracted']:
            response += f"**Text found:** \"{analysis['text_extracted']}\"\n\n"
        response += f"⚡ Processed in {analysis['processing_time']}s"
        
    else:  # artistic mode
        if preset == "Critic":
            analysis = {
                "description": "This landscape demonstrates strong compositional principles with the rule of thirds effectively applied. The foreground mountains create leading lines that draw the eye toward the dramatic sky. The color palette transitions beautifully from warm earth tones to cool blues, creating visual depth. The lighting appears to be during golden hour, adding warmth and dimensionality. This composition shows influences of romantic landscape painting traditions, particularly reminiscent of Caspar David Friedrich's approach to sublime natural scenes.",
                "mode": mode,
                "preset": preset,
                "processing_time": 4.7,
                "similar_count": 0
            }
        elif preset == "Photo-coach":
            analysis = {
                "description": "Strong composition with good use of foreground elements! The exposure captures detail in both shadows and highlights effectively. Consider experimenting with a slightly lower viewpoint to emphasize the foreground rocks more dramatically. The depth of field works well here. For future shots, try capturing during blue hour for more dramatic sky colors, or use graduated filters to balance the exposure between sky and land even better.",
                "mode": mode,
                "preset": preset,
                "processing_time": 4.2,
                "similar_count": 0
            }
        else:  # Creative
            analysis = {
                "description": "This image whispers stories of ancient time and patient stone. The mountains stand like silent guardians, holding secrets of millennia within their rocky embrace. What if this landscape could speak? It might tell tales of changing seasons, of wildlife that calls these peaks home, of storms weathered and sunrises witnessed. This scene could inspire a story about a traveler's journey of self-discovery, or serve as the perfect backdrop for a meditation app focused on finding inner peace through nature's grandeur.",
                "mode": mode,
                "preset": preset,
                "processing_time": 3.8,
                "similar_count": 0
            }
        
        response = f"🎨 **Image Analysis (Artistic - {preset})**\n\n"
        response += f"**Analysis:** {analysis['description']}\n\n"
        
        if analysis['similar_count'] > 0:
            response += f"🔍 **Similar Images:** Found {analysis['similar_count']} similar images in your collection\n\n"
        else:
            response += f"🔍 **Similar Images:** No similar images found yet. Keep uploading!\n\n"
        
        response += f"⚡ Processed in {analysis['processing_time']}s • 🎯 Vector embeddings enabled"
    
    # Update the processing message with results
    await processing_msg.edit_text(response)
    
    # Save to database (placeholder)
    try:
        async with get_db_session() as session:
            image_record = Image(
                chat_id=chat_id,
                file_id=file_id,
                file_unique_id=f"unique_{file_id}",  # Placeholder
                analysis=str(analysis),  # In real implementation, this would be JSON
                mode_used=mode,
                preset_used=preset,
                processing_status="completed"
            )
            session.add(image_record)
            await session.commit()
            logger.info(f"Saved image analysis for file_id: {file_id}")
            
    except Exception as e:
        logger.error(f"Error saving image analysis: {e}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    if any(word in text_lower for word in ['help', 'how', 'what', 'commands']):
        await message.reply_text(
            "🤖 **Need help?**\n\n"
            "• Send me any image and I'll analyze it!\n"
            "• Use `/help` for detailed command information\n"
            "• Use `/mode` to change analysis modes\n"
            "• Try `/analyze`, `/coach`, or `/creative` for quick mode switching\n\n"
            "What would you like to know more about?"
        )
    
    elif any(word in text_lower for word in ['mode', 'setting', 'config']):
        await message.reply_text(
            "⚙️ **Mode Information**\n\n"
            "Use `/mode` to see your current mode and available options.\n\n"
            "Quick commands:\n"
            "• `/mode default` - Quick descriptions\n"
            "• `/analyze` - Art analysis\n"
            "• `/coach` - Photography tips\n"
            "• `/creative` - Creative interpretation"
        )
    
    elif any(word in text_lower for word in ['image', 'photo', 'picture', 'analyze']):
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