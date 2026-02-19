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

from sqlalchemy import delete, func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core.database import get_db_session
from ...core.i18n import get_user_locale_from_update, t
from ...models.chat import Chat
from ...models.claude_session import ClaudeSession
from ...models.collect_session import CollectSession
from ...models.image import Image
from ...models.message import Message
from ...models.poll_response import PollResponse
from ...models.tracker import CheckIn, Tracker
from ...models.user import User
from ...models.accountability_profile import AccountabilityProfile
from ...models.life_weeks_settings import LifeWeeksSettings
from ...models.privacy_settings import PrivacySettings
from ...models.user_settings import UserSettings
from ...models.voice_settings import VoiceSettings
from ...utils.audit_log import audit_log

logger = logging.getLogger(__name__)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /privacy command - show privacy information."""
    user = update.effective_user
    if not user or not update.message:
        return

    logger.info(f"Privacy command from user {user.id}")

    locale = get_user_locale_from_update(update)

    consent_status = t("privacy.consent_not_given", locale)
    consent_date = t("privacy.consent_date_na", locale)
    data_retention = t("privacy.retention_default", locale)

    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.user_id == user.id))
        user_obj = result.scalar_one_or_none()
        if user_obj:
            if user_obj.consent_given:
                consent_status = t("privacy.consent_given", locale)
                if user_obj.consent_given_at:
                    consent_date = user_obj.consent_given_at.strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )

        # Check privacy settings for retention
        settings_result = await session.execute(
            select(PrivacySettings).where(PrivacySettings.user_id == user.id)
        )
        settings_obj = settings_result.scalar_one_or_none()
        if settings_obj:
            retention_key = {
                "1_month": "retention_1_month",
                "6_months": "retention_6_months",
                "1_year": "retention_1_year",
                "forever": "retention_forever",
            }.get(settings_obj.data_retention)
            if retention_key:
                data_retention = t(f"privacy.{retention_key}", locale)

    privacy_text = (
        f"<b>{t('privacy.title', locale)}</b>\n\n"
        f"<b>{t('privacy.data_we_collect', locale)}</b>\n"
        f"- {t('privacy.collect_user_id', locale)}\n"
        f"- {t('privacy.collect_messages', locale)}\n"
        f"- {t('privacy.collect_voice', locale)}\n"
        f"- {t('privacy.collect_claude', locale)}\n"
        f"- {t('privacy.collect_tracker', locale)}\n\n"
        f"<b>{t('privacy.third_party', locale)}</b>\n"
        f"- {t('privacy.third_anthropic', locale)}\n"
        f"- {t('privacy.third_openai', locale)}\n"
        f"- {t('privacy.third_groq', locale)}\n\n"
        f"<b>{t('privacy.consent_status_label', locale)}</b> {consent_status}\n"
        f"<b>{t('privacy.consent_date_label', locale)}</b> {consent_date}\n"
        f"<b>{t('privacy.data_retention_label', locale)}</b> {data_retention}\n\n"
        f"<b>{t('privacy.your_rights', locale)}</b>\n"
        f"/mydata - {t('privacy.cmd_mydata', locale)}\n"
        f"/deletedata - {t('privacy.cmd_deletedata', locale)}\n"
    )

    await update.message.reply_text(privacy_text, parse_mode="HTML")


async def mydata_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        result = await session.execute(select(User).where(User.user_id == user.id))
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
                    user_obj.created_at.isoformat() if user_obj.created_at else None
                ),
            }

        # Chats
        result = await session.execute(select(Chat).where(Chat.user_id == user.id))
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

        # Messages (count + capped sample to avoid OOM)
        _EXPORT_LIMIT = 10000
        if chat_ids:
            count_result = await session.execute(
                select(func.count())
                .select_from(Message)
                .where(Message.chat_id.in_(chat_ids))
            )
            msg_count = count_result.scalar() or 0
            result = await session.execute(
                select(Message)
                .where(Message.chat_id.in_(chat_ids))
                .order_by(Message.created_at.desc())
                .limit(_EXPORT_LIMIT)
            )
            messages = result.scalars().all()
            export_data["categories"]["messages"] = {
                "count": msg_count,
                "records": [
                    {
                        "chat_id": m.chat_id,
                        "role": m.role,
                        "content_preview": (
                            (m.content[:100] + "...")
                            if m.content and len(m.content) > 100
                            else m.content
                        ),
                        "created_at": (
                            m.created_at.isoformat() if m.created_at else None
                        ),
                    }
                    for m in messages
                ],
            }

        # Images (count + capped sample to avoid OOM)
        img_count_result = await session.execute(
            select(func.count()).select_from(Image).where(Image.user_id == user.id)
        )
        img_count = img_count_result.scalar() or 0
        result = await session.execute(
            select(Image)
            .where(Image.user_id == user.id)
            .order_by(Image.created_at.desc())
            .limit(_EXPORT_LIMIT)
        )
        images = result.scalars().all()
        export_data["categories"]["images"] = {
            "count": img_count,
            "records": [
                {
                    "id": img.id,
                    "file_type": getattr(img, "file_type", None),
                    "created_at": (
                        img.created_at.isoformat() if img.created_at else None
                    ),
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
            caption=t("privacy.mydata_caption", get_user_locale_from_update(update)),
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

    locale = get_user_locale_from_update(update)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("inline.privacy.delete_confirm", locale),
                    callback_data="gdpr_delete_confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    t("inline.privacy.delete_cancel", locale),
                    callback_data="gdpr_delete_cancel",
                ),
            ],
        ]
    )

    await update.message.reply_text(
        f"<b>{t('privacy.deletedata_title', locale)}</b>\n\n"
        f"{t('privacy.deletedata_warning', locale)}\n"
        f"<b>{t('privacy.deletedata_irreversible', locale)}</b>\n\n"
        f"{t('privacy.deletedata_confirm_question', locale)}",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def handle_gdpr_callback(
    query, user_id: int, action: str, locale: str = "en"
) -> None:
    """Handle GDPR-related callback queries."""
    if action == "gdpr_delete_confirm":
        await _execute_data_deletion(query, user_id, locale=locale)
    elif action == "gdpr_delete_cancel":
        await query.edit_message_text(t("privacy.cancel_message", locale))
    elif action == "gdpr_consent_accept":
        await _record_consent(query, user_id, accepted=True, locale=locale)
    elif action == "gdpr_consent_decline":
        await _record_consent(query, user_id, accepted=False, locale=locale)


async def _record_consent(
    query, user_id: int, accepted: bool, locale: str = "en"
) -> None:
    """Record user's consent decision."""
    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user_obj = result.scalar_one_or_none()
        if user_obj:
            user_obj.consent_given = accepted
            user_obj.consent_given_at = datetime.utcnow() if accepted else None
            await session.commit()

    if accepted:
        await query.edit_message_text(t("privacy.consent_accepted", locale))
    else:
        await query.edit_message_text(t("privacy.consent_declined", locale))


async def _execute_data_deletion(query, user_id: int, locale: str = "en") -> None:
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
                    delete(CollectSession).where(CollectSession.chat_id.in_(chat_ids))
                )
                deleted_counts["collect_sessions"] = result.rowcount

            # Delete images and their files (batched to limit memory)
            _DELETE_BATCH = 500
            while True:
                img_result = await session.execute(
                    select(Image).where(Image.user_id == user_id).limit(_DELETE_BATCH)
                )
                images = img_result.scalars().all()
                if not images:
                    break
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

            # Delete user settings (both legacy and split tables)
            result = await session.execute(
                delete(UserSettings).where(UserSettings.user_id == user_id)
            )
            deleted_counts["user_settings"] = result.rowcount

            for model, name in [
                (VoiceSettings, "voice_settings"),
                (AccountabilityProfile, "accountability_profiles"),
                (PrivacySettings, "privacy_settings"),
                (LifeWeeksSettings, "life_weeks_settings"),
            ]:
                try:
                    result = await session.execute(
                        delete(model).where(model.user_id == user_id)
                    )
                    deleted_counts[name] = result.rowcount
                except Exception:
                    pass  # table may not exist yet

            # Delete chats (cascades keyboard_config)
            result = await session.execute(delete(Chat).where(Chat.user_id == user_id))
            deleted_counts["chats"] = result.rowcount

            # Delete user record last
            result = await session.execute(delete(User).where(User.user_id == user_id))
            deleted_counts["user"] = result.rowcount

            await session.commit()

        # Clear in-memory caches
        _clear_user_caches(user_id, chat_ids)

        logger.info(f"Data deletion completed for user {user_id}: {deleted_counts}")

        summary = "\n".join(
            f"- {k}: {v} records" for k, v in deleted_counts.items() if v > 0
        )
        await query.edit_message_text(
            f"{t('privacy.deletion_complete', locale)}\n\n"
            f"<b>{t('privacy.deletion_deleted_label', locale)}</b>\n"
            f"{summary}\n\n"
            f"{t('privacy.deletion_restart_hint', locale)}",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Data deletion failed for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text(t("privacy.deletion_error", locale))


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
                keys_to_remove = [k for k in reply_ctx._cache if str(chat_id) in str(k)]
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
