"""
Privacy and GDPR compliance commands.

Contains:
- /privacy - Show privacy information and consent status
- /mydata - Export all user data (GDPR data portability)
- /deletedata - Delete all user data (GDPR right to erasure)
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core.database import get_db_session
from ...models.chat import Chat
from ...models.claude_session import ClaudeSession
from ...models.collect_session import CollectSession
from ...models.image import Image
from ...models.message import Message
from ...models.poll_response import PollResponse
from ...models.tracker import CheckIn, Tracker
from ...models.user import User
from ...models.user_settings import UserSettings
from ...utils.audit_log import audit_log

logger = logging.getLogger(__name__)


async def privacy_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /privacy command - show privacy information."""
    user = update.effective_user
    if not user or not update.message:
        return

    logger.info(f"Privacy command from user {user.id}")

    consent_status = "Not given"
    consent_date = "N/A"
    data_retention = "1 year (default)"

    async with get_db_session() as session:
        result = await session.execute(
            select(User).where(User.user_id == user.id)
        )
        user_obj = result.scalar_one_or_none()
        if user_obj:
            if user_obj.consent_given:
                consent_status = "Given"
                if user_obj.consent_given_at:
                    consent_date = user_obj.consent_given_at.strftime("%Y-%m-%d %H:%M UTC")

        # Check user settings for retention
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings_obj = settings_result.scalar_one_or_none()
        if settings_obj:
            retention_map = {
                "1_month": "1 month",
                "6_months": "6 months",
                "1_year": "1 year",
                "forever": "No limit",
            }
            data_retention = retention_map.get(settings_obj.data_retention, settings_obj.data_retention)

    privacy_text = (
        "<b>Privacy Information</b>\n\n"
        "<b>Data We Collect:</b>\n"
        "- Telegram user ID, username, name\n"
        "- Messages and media you send to the bot\n"
        "- Voice transcriptions\n"
        "- Claude session history\n"
        "- Tracker and check-in data\n\n"
        "<b>Third-Party Services:</b>\n"
        "- Anthropic (Claude) - AI processing\n"
        "- OpenAI - LLM analysis\n"
        "- Groq - Voice transcription\n\n"
        f"<b>Consent Status:</b> {consent_status}\n"
        f"<b>Consent Date:</b> {consent_date}\n"
        f"<b>Data Retention:</b> {data_retention}\n\n"
        "<b>Your Rights:</b>\n"
        "/mydata - Export all your data\n"
        "/deletedata - Delete all your data\n"
    )

    await update.message.reply_text(privacy_text, parse_mode="HTML")


async def mydata_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /mydata command - export all user data as JSON."""
    user = update.effective_user
    if not user or not update.message:
        return

    logger.info(f"Data export requested by user {user.id}")
    audit_log("data_export", user_id=user.id)

    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "user_id": user.id,
        "categories": {},
    }

    async with get_db_session() as session:
        # User profile
        result = await session.execute(
            select(User).where(User.user_id == user.id)
        )
        user_obj = result.scalar_one_or_none()
        if user_obj:
            export_data["categories"]["profile"] = {
                "username": user_obj.username,
                "first_name": user_obj.first_name,
                "last_name": user_obj.last_name,
                "language_code": user_obj.language_code,
                "consent_given": user_obj.consent_given,
                "consent_given_at": (
                    user_obj.consent_given_at.isoformat()
                    if user_obj.consent_given_at
                    else None
                ),
                "created_at": (
                    user_obj.created_at.isoformat()
                    if user_obj.created_at
                    else None
                ),
            }

        # Chats
        result = await session.execute(
            select(Chat).where(Chat.user_id == user.id)
        )
        chats = result.scalars().all()
        chat_ids = [c.chat_id for c in chats]
        export_data["categories"]["chats"] = {
            "count": len(chats),
            "records": [
                {
                    "chat_id": c.chat_id,
                    "claude_mode": c.claude_mode,
                    "claude_model": c.claude_model,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in chats
            ],
        }

        # Messages
        if chat_ids:
            result = await session.execute(
                select(Message).where(Message.chat_id.in_(chat_ids))
            )
            messages = result.scalars().all()
            export_data["categories"]["messages"] = {
                "count": len(messages),
                "records": [
                    {
                        "chat_id": m.chat_id,
                        "role": m.role,
                        "content_preview": (m.content[:100] + "...") if m.content and len(m.content) > 100 else m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
            }

        # Images
        result = await session.execute(
            select(Image).where(Image.user_id == user.id)
        )
        images = result.scalars().all()
        export_data["categories"]["images"] = {
            "count": len(images),
            "records": [
                {
                    "id": img.id,
                    "file_type": getattr(img, "file_type", None),
                    "created_at": img.created_at.isoformat() if img.created_at else None,
                }
                for img in images
            ],
        }

        # Claude sessions
        result = await session.execute(
            select(ClaudeSession).where(ClaudeSession.user_id == user.id)
        )
        sessions = result.scalars().all()
        export_data["categories"]["claude_sessions"] = {
            "count": len(sessions),
            "records": [
                {
                    "session_id": s.session_id,
                    "is_active": s.is_active,
                    "last_used": s.last_used.isoformat() if s.last_used else None,
                }
                for s in sessions
            ],
        }

        # Trackers
        result = await session.execute(
            select(Tracker).where(Tracker.user_id == user.id)
        )
        trackers = result.scalars().all()
        export_data["categories"]["trackers"] = {
            "count": len(trackers),
            "records": [
                {
                    "id": t.id,
                    "type": t.type,
                    "name": t.name,
                    "active": t.active,
                }
                for t in trackers
            ],
        }

        # Check-ins
        result = await session.execute(
            select(CheckIn).where(CheckIn.user_id == user.id)
        )
        checkins = result.scalars().all()
        export_data["categories"]["check_ins"] = {
            "count": len(checkins),
            "records": [
                {
                    "id": ci.id,
                    "tracker_id": ci.tracker_id,
                    "status": ci.status,
                    "created_at": ci.created_at.isoformat() if ci.created_at else None,
                }
                for ci in checkins
            ],
        }

        # User settings
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        if settings:
            export_data["categories"]["settings"] = {
                "voice_enabled": settings.voice_enabled,
                "voice_model": settings.voice_model,
                "response_mode": settings.response_mode,
                "privacy_level": settings.privacy_level,
                "data_retention": settings.data_retention,
                "timezone": settings.timezone,
            }

        # Poll responses
        if chat_ids:
            result = await session.execute(
                select(PollResponse).where(PollResponse.chat_id.in_(chat_ids))
            )
            polls = result.scalars().all()
            export_data["categories"]["poll_responses"] = {
                "count": len(polls),
            }

    # Record counts summary
    export_data["summary"] = {
        category: data.get("count", 1) if isinstance(data, dict) else 1
        for category, data in export_data["categories"].items()
    }

    # Send as JSON file
    json_content = json.dumps(export_data, indent=2, ensure_ascii=False)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="mydata_", delete=False
    ) as f:
        f.write(json_content)
        tmp_path = f.name

    try:
        await update.message.reply_document(
            document=open(tmp_path, "rb"),
            filename=f"mydata_{user.id}_{datetime.utcnow().strftime('%Y%m%d')}.json",
            caption="Your data export. This contains all data we store about you.",
        )
    finally:
        os.unlink(tmp_path)


async def deletedata_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /deletedata command - show confirmation before deletion."""
    user = update.effective_user
    if not user or not update.message:
        return

    logger.info(f"Data deletion requested by user {user.id}")
    audit_log("data_deletion_requested", user_id=user.id)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes, delete all my data",
                    callback_data="gdpr_delete_confirm",
                ),
            ],
            [
                InlineKeyboardButton("Cancel", callback_data="gdpr_delete_cancel"),
            ],
        ]
    )

    await update.message.reply_text(
        "<b>Delete All Your Data</b>\n\n"
        "This will permanently delete:\n"
        "- Your user profile\n"
        "- All chat history and messages\n"
        "- All images and analyses\n"
        "- Claude sessions\n"
        "- Trackers and check-ins\n"
        "- Poll responses\n"
        "- All settings and preferences\n\n"
        "<b>This action cannot be undone.</b>\n\n"
        "Are you sure?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def handle_gdpr_callback(
    query, user_id: int, action: str
) -> None:
    """Handle GDPR-related callback queries."""
    if action == "gdpr_delete_confirm":
        await _execute_data_deletion(query, user_id)
    elif action == "gdpr_delete_cancel":
        await query.edit_message_text("Data deletion cancelled.")
    elif action == "gdpr_consent_accept":
        await _record_consent(query, user_id, accepted=True)
    elif action == "gdpr_consent_decline":
        await _record_consent(query, user_id, accepted=False)


async def _record_consent(query, user_id: int, accepted: bool) -> None:
    """Record user's consent decision."""
    async with get_db_session() as session:
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user_obj = result.scalar_one_or_none()
        if user_obj:
            user_obj.consent_given = accepted
            user_obj.consent_given_at = datetime.utcnow() if accepted else None
            await session.commit()

    if accepted:
        await query.edit_message_text(
            "Thank you. Your consent has been recorded. You can manage your privacy settings anytime with /privacy."
        )
    else:
        await query.edit_message_text(
            "You have declined consent. Some features may be limited. "
            "You can change this decision anytime with /privacy."
        )


async def _execute_data_deletion(query, user_id: int) -> None:
    """Execute full data deletion for a user."""
    logger.info(f"Executing data deletion for user {user_id}")
    audit_log("data_deletion_executed", user_id=user_id)

    deleted_counts = {}

    try:
        async with get_db_session() as session:
            # Get user's chat IDs first
            result = await session.execute(
                select(Chat.chat_id).where(Chat.user_id == user_id)
            )
            chat_ids = [row[0] for row in result.fetchall()]

            # Delete check-ins
            result = await session.execute(
                delete(CheckIn).where(CheckIn.user_id == user_id)
            )
            deleted_counts["check_ins"] = result.rowcount

            # Delete trackers
            result = await session.execute(
                delete(Tracker).where(Tracker.user_id == user_id)
            )
            deleted_counts["trackers"] = result.rowcount

            # Delete poll responses
            if chat_ids:
                result = await session.execute(
                    delete(PollResponse).where(PollResponse.chat_id.in_(chat_ids))
                )
                deleted_counts["poll_responses"] = result.rowcount

            # Delete messages
            if chat_ids:
                result = await session.execute(
                    delete(Message).where(Message.chat_id.in_(chat_ids))
                )
                deleted_counts["messages"] = result.rowcount

            # Delete collect sessions
            if chat_ids:
                result = await session.execute(
                    delete(CollectSession).where(
                        CollectSession.chat_id.in_(chat_ids)
                    )
                )
                deleted_counts["collect_sessions"] = result.rowcount

            # Delete images and their files
            img_result = await session.execute(
                select(Image).where(Image.user_id == user_id)
            )
            images = img_result.scalars().all()
            for img in images:
                _delete_image_files(img)
            result = await session.execute(
                delete(Image).where(Image.user_id == user_id)
            )
            deleted_counts["images"] = result.rowcount

            # Delete Claude sessions
            result = await session.execute(
                delete(ClaudeSession).where(ClaudeSession.user_id == user_id)
            )
            deleted_counts["claude_sessions"] = result.rowcount

            # Delete user settings
            result = await session.execute(
                delete(UserSettings).where(UserSettings.user_id == user_id)
            )
            deleted_counts["user_settings"] = result.rowcount

            # Delete chats (cascades keyboard_config)
            result = await session.execute(
                delete(Chat).where(Chat.user_id == user_id)
            )
            deleted_counts["chats"] = result.rowcount

            # Delete user record last
            result = await session.execute(
                delete(User).where(User.user_id == user_id)
            )
            deleted_counts["user"] = result.rowcount

            await session.commit()

        # Clear in-memory caches
        _clear_user_caches(user_id, chat_ids)

        logger.info(f"Data deletion completed for user {user_id}: {deleted_counts}")

        summary = "\n".join(
            f"- {k}: {v} records" for k, v in deleted_counts.items() if v > 0
        )
        await query.edit_message_text(
            f"All your data has been deleted.\n\n"
            f"<b>Deleted:</b>\n{summary}\n\n"
            f"You can start fresh anytime with /start.",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Data deletion failed for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text(
            "An error occurred during data deletion. Please try again or contact support."
        )


def _delete_image_files(image) -> None:
    """Delete image files from filesystem."""
    for attr in ["original_path", "compressed_path"]:
        path = getattr(image, attr, None)
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError as e:
                logger.warning(f"Failed to delete image file {path}: {e}")


def _clear_user_caches(user_id: int, chat_ids: list) -> None:
    """Clear in-memory caches for a deleted user."""
    try:
        from ...services.reply_context import get_reply_context_service
        reply_ctx = get_reply_context_service()
        if reply_ctx:
            # Remove any cached contexts for the user's chats
            for chat_id in chat_ids:
                keys_to_remove = [
                    k for k in reply_ctx._cache
                    if str(chat_id) in str(k)
                ]
                for key in keys_to_remove:
                    del reply_ctx._cache[key]
    except Exception as e:
        logger.warning(f"Cache cleanup error: {e}")

    try:
        from ...services.claude_code_service import _admin_cache
        for chat_id in chat_ids:
            _admin_cache.pop(chat_id, None)
    except Exception as e:
        logger.warning(f"Admin cache cleanup error: {e}")
