import logging
from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.i18n import t
from ..core.mode_manager import ModeManager
from ..utils.session_emoji import get_session_emoji
from .callback_data_manager import get_callback_data_manager

logger = logging.getLogger(__name__)


class KeyboardUtils:
    """Utility class for creating Telegram inline keyboards"""

    def __init__(self):
        self.mode_manager = ModeManager()
        self.callback_manager = get_callback_data_manager()

    def create_reanalysis_keyboard(
        self,
        file_id: str,
        current_mode: str,
        current_preset: Optional[str] = None,
        local_image_path: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create context-aware keyboard for image reanalysis"""

        buttons = []

        if current_mode == "default":
            # Currently in default mode - show all artistic presets
            artistic_presets = self.mode_manager.get_mode_presets("artistic")

            for preset in artistic_presets:
                # Include local image path in callback data if available
                if local_image_path:
                    logger.info(
                        f"Including local image path in callback data: {local_image_path}"
                    )
                    # Create callback data with mode, preset, and local path
                    callback_data = (
                        f"reanalyze:{file_id}:artistic:{preset}:{local_image_path}"
                    )
                    # Check if it's too long and truncate if necessary
                    if len(callback_data.encode("utf-8")) > 64:
                        logger.warning(
                            "Callback data too long, using callback manager instead"
                        )
                        callback_data = self.callback_manager.create_callback_data(
                            action="reanalyze",
                            file_id=file_id,
                            mode="artistic",
                            preset=preset,
                        )
                else:
                    callback_data = self.callback_manager.create_callback_data(
                        action="reanalyze",
                        file_id=file_id,
                        mode="artistic",
                        preset=preset,
                    )

                # Choose appropriate emoji for each preset
                if preset == "Critic":
                    emoji = "🎨"
                elif preset == "Photo-coach":
                    emoji = "📸"
                elif preset == "Creative":
                    emoji = "✨"
                else:
                    emoji = "🎭"

                button_text = f"{emoji} {preset}"
                buttons.append(
                    InlineKeyboardButton(button_text, callback_data=callback_data)
                )

        else:  # artistic mode
            # Show default mode button
            if local_image_path:
                logger.info(
                    f"Including local image path in callback data for default mode: {local_image_path}"
                )
                # Create callback data with mode, preset, and local path
                callback_data = f"reanalyze:{file_id}:default::{local_image_path}"
                # Check if it's too long and truncate if necessary
                if len(callback_data.encode("utf-8")) > 64:
                    logger.warning(
                        "Callback data too long, using callback manager instead"
                    )
                    callback_data = self.callback_manager.create_callback_data(
                        action="reanalyze", file_id=file_id, mode="default", preset=None
                    )
            else:
                callback_data = self.callback_manager.create_callback_data(
                    action="reanalyze", file_id=file_id, mode="default", preset=None
                )
            buttons.append(
                InlineKeyboardButton(
                    t("inline.mode.quick_analysis", locale),
                    callback_data=callback_data,
                )
            )

            # Show other artistic presets (excluding current one)
            artistic_presets = self.mode_manager.get_mode_presets("artistic")

            for preset in artistic_presets:
                if preset != current_preset:  # Skip current preset
                    if local_image_path:
                        logger.info(
                            f"Including local image path in callback data for preset {preset}: {local_image_path}"
                        )
                        # Create callback data with mode, preset, and local path
                        callback_data = (
                            f"reanalyze:{file_id}:artistic:{preset}:{local_image_path}"
                        )
                        # Check if it's too long and truncate if necessary
                        if len(callback_data.encode("utf-8")) > 64:
                            logger.warning(
                                "Callback data too long, using callback manager instead"
                            )
                            callback_data = self.callback_manager.create_callback_data(
                                action="reanalyze",
                                file_id=file_id,
                                mode="artistic",
                                preset=preset,
                            )
                    else:
                        callback_data = self.callback_manager.create_callback_data(
                            action="reanalyze",
                            file_id=file_id,
                            mode="artistic",
                            preset=preset,
                        )

                    # Choose appropriate emoji for each preset
                    if preset == "Critic":
                        emoji = "🎨"
                    elif preset == "Photo-coach":
                        emoji = "📸"
                    elif preset == "Creative":
                        emoji = "✨"
                    else:
                        emoji = "🎭"

                    button_text = f"{emoji} {preset}"
                    buttons.append(
                        InlineKeyboardButton(button_text, callback_data=callback_data)
                    )

        # Arrange buttons in rows (max 2 buttons per row for better layout)
        keyboard_rows = []
        for i in range(0, len(buttons), 2):
            row = buttons[i : i + 2]
            keyboard_rows.append(row)

        return InlineKeyboardMarkup(keyboard_rows)

    def create_mode_selection_keyboard(
        self,
        current_mode: str = "default",
        current_preset: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard for general mode selection (for /mode command)"""

        buttons = []

        # Default mode button
        if current_mode != "default":
            buttons.append(
                InlineKeyboardButton(
                    t("inline.mode.quick_analysis", locale),
                    callback_data="mode:default:",
                )
            )

        # Artistic mode buttons
        artistic_presets = self.mode_manager.get_mode_presets("artistic")

        for preset in artistic_presets:
            # Skip current preset if in artistic mode
            if current_mode == "artistic" and preset == current_preset:
                continue

            callback_data = f"mode:artistic:{preset}"

            # Choose appropriate label for each preset
            if preset == "Critic":
                text = t("inline.mode.art_critic", locale)
            elif preset == "Photo-coach":
                text = t("inline.mode.photo_coach", locale)
            elif preset == "Creative":
                text = t("inline.mode.creative", locale)
            else:
                emoji = "🎭"
                text = f"{emoji} {preset}"

            buttons.append(InlineKeyboardButton(text, callback_data=callback_data))

        # Arrange buttons in rows (max 2 buttons per row)
        keyboard_rows = []
        for i in range(0, len(buttons), 2):
            row = buttons[i : i + 2]
            keyboard_rows.append(row)

        return InlineKeyboardMarkup(keyboard_rows)

    def create_comprehensive_mode_keyboard(
        self,
        current_mode: str = "default",
        current_preset: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard showing ALL available modes and presets"""

        buttons = []

        # Default mode button
        qa_label = t("inline.mode.quick_analysis", locale)
        if current_mode != "default":
            buttons.append(
                InlineKeyboardButton(qa_label, callback_data="mode:default:")
            )
        else:
            buttons.append(
                InlineKeyboardButton(qa_label + " ✓", callback_data="mode:default:")
            )

        # Formal mode buttons
        formal_presets = self.mode_manager.get_mode_presets("formal")
        for preset in formal_presets:
            is_current = current_mode == "formal" and preset == current_preset

            if preset == "Structured":
                text = t("inline.mode.formal_structured", locale)
            elif preset == "Tags":
                text = t("inline.mode.tags_entities", locale)
            elif preset == "COCO":
                text = t("inline.mode.coco_objects", locale)
            else:
                emoji = "📊"
                text = f"{emoji} {preset}"

            if is_current:
                text += " ✓"

            callback_data = f"mode:formal:{preset}"
            buttons.append(InlineKeyboardButton(text, callback_data=callback_data))

        # Artistic mode buttons
        artistic_presets = self.mode_manager.get_mode_presets("artistic")
        for preset in artistic_presets:
            is_current = current_mode == "artistic" and preset == current_preset

            callback_data = f"mode:artistic:{preset}"

            # Choose appropriate label for each preset
            if preset == "Critic":
                text = t("inline.mode.art_critic", locale)
            elif preset == "Photo-coach":
                text = t("inline.mode.photo_coach", locale)
            elif preset == "Creative":
                text = t("inline.mode.creative", locale)
            else:
                emoji = "🎭"
                text = f"{emoji} {preset}"

            if is_current:
                text += " ✓"

            buttons.append(InlineKeyboardButton(text, callback_data=callback_data))

        # Arrange buttons in rows (max 2 buttons per row)
        keyboard_rows = []
        for i in range(0, len(buttons), 2):
            row = buttons[i : i + 2]
            keyboard_rows.append(row)

        return InlineKeyboardMarkup(keyboard_rows)

    def create_confirmation_keyboard(
        self, action: str, data: str, locale: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create confirmation keyboard for destructive actions"""

        buttons = [
            [
                InlineKeyboardButton(
                    t("inline.common.confirm", locale),
                    callback_data=f"confirm:{action}:{data}",
                ),
                InlineKeyboardButton(
                    t("inline.common.cancel", locale),
                    callback_data=f"cancel:{action}",
                ),
            ]
        ]

        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def parse_callback_data(callback_data: str) -> Tuple[str, List[str]]:
        """Parse callback data into action and parameters"""
        parts = callback_data.split(":", 1)

        if len(parts) < 2:
            return callback_data, []

        action = parts[0]
        params = parts[1].split(":")

        return action, params

    def create_gallery_navigation_keyboard(
        self,
        images: List[Dict],
        page: int,
        total_pages: int,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard for gallery navigation and image actions"""

        buttons = []

        # Image action buttons (View Full Analysis for each image)
        for i, image in enumerate(images, 1):
            image_id = image["id"]
            button_text = t("inline.gallery.view_image", locale, n=(page - 1) * 10 + i)
            callback_data = f"gallery:view:{image_id}"
            buttons.append(
                InlineKeyboardButton(button_text, callback_data=callback_data)
            )

        # Arrange image buttons in rows (2 per row)
        keyboard_rows = []
        for i in range(0, len(buttons), 2):
            row = buttons[i : i + 2]
            keyboard_rows.append(row)

        # Navigation row
        nav_buttons = []

        # Previous button
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    t("inline.gallery.previous", locale),
                    callback_data=f"gallery:page:{page-1}",
                )
            )

        # Page indicator (non-clickable)
        nav_buttons.append(
            InlineKeyboardButton(
                t(
                    "inline.gallery.page_indicator",
                    locale,
                    page=page,
                    total=total_pages,
                ),
                callback_data="gallery:noop",
            )
        )

        # Next button
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    t("inline.gallery.next", locale),
                    callback_data=f"gallery:page:{page+1}",
                )
            )

        if nav_buttons:
            keyboard_rows.append(nav_buttons)

        # Back to menu button
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    t("inline.common.main_menu", locale),
                    callback_data="gallery:menu",
                )
            ]
        )

        return InlineKeyboardMarkup(keyboard_rows)

    def create_image_detail_keyboard(
        self,
        image_id: int,
        current_mode: str,
        current_preset: Optional[str],
        page: int,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard for individual image detail view"""

        buttons = []

        # Reanalysis options (show other modes)
        if current_mode == "default":
            # Show artistic presets
            artistic_presets = self.mode_manager.get_mode_presets("artistic")
            for preset in artistic_presets:
                emoji = (
                    "🎨"
                    if preset == "Critic"
                    else "📸" if preset == "Photo-coach" else "✨"
                )
                button_text = f"{emoji} {preset}"
                callback_data = f"gallery:reanalyze:{image_id}:artistic:{preset}"
                buttons.append(
                    InlineKeyboardButton(button_text, callback_data=callback_data)
                )
        else:
            # Show default mode and other artistic presets
            buttons.append(
                InlineKeyboardButton(
                    t("inline.mode.quick_analysis", locale),
                    callback_data=f"gallery:reanalyze:{image_id}:default:",
                )
            )

            artistic_presets = self.mode_manager.get_mode_presets("artistic")
            for preset in artistic_presets:
                if preset != current_preset:
                    emoji = (
                        "🎨"
                        if preset == "Critic"
                        else "📸" if preset == "Photo-coach" else "✨"
                    )
                    button_text = f"{emoji} {preset}"
                    callback_data = f"gallery:reanalyze:{image_id}:artistic:{preset}"
                    buttons.append(
                        InlineKeyboardButton(button_text, callback_data=callback_data)
                    )

        # Arrange reanalysis buttons in rows (2 per row)
        keyboard_rows = []
        for i in range(0, len(buttons), 2):
            row = buttons[i : i + 2]
            keyboard_rows.append(row)

        # Navigation buttons
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    t("inline.gallery.back_to_gallery", locale),
                    callback_data=f"gallery:page:{page}",
                ),
                InlineKeyboardButton(
                    t("inline.common.main_menu", locale),
                    callback_data="gallery:menu",
                ),
            ]
        )

        return InlineKeyboardMarkup(keyboard_rows)

    @staticmethod
    def create_simple_keyboard(
        buttons_data: List[Tuple[str, str]], max_per_row: int = 2
    ) -> InlineKeyboardMarkup:
        """Create a simple keyboard from button data tuples (text, callback_data)"""

        buttons = [
            InlineKeyboardButton(text, callback_data=data)
            for text, data in buttons_data
        ]

        # Arrange in rows
        keyboard_rows = []
        for i in range(0, len(buttons), max_per_row):
            row = buttons[i : i + max_per_row]
            keyboard_rows.append(row)

        return InlineKeyboardMarkup(keyboard_rows)

    def create_claude_action_keyboard(
        self,
        has_active_session: bool = False,
        session_id: str = None,
        last_prompt: str = None,
        is_locked: bool = False,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard for Claude Code session actions."""
        buttons = []

        if is_locked:
            # When locked, only show unlock
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.unlock", locale),
                        callback_data="claude:unlock",
                    ),
                    InlineKeyboardButton(
                        t("inline.claude.new_session", locale),
                        callback_data="claude:new",
                    ),
                ]
            )
        elif has_active_session:
            # Continue now auto-locks the session
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.continue", locale),
                        callback_data="claude:continue",
                    ),
                    InlineKeyboardButton(
                        t("inline.claude.new", locale),
                        callback_data="claude:new",
                    ),
                ]
            )
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.sessions", locale),
                        callback_data="claude:list",
                    ),
                    InlineKeyboardButton(
                        t("inline.claude.end", locale),
                        callback_data="claude:end",
                    ),
                ]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.new_session", locale),
                        callback_data="claude:new",
                    ),
                    InlineKeyboardButton(
                        t("inline.claude.sessions", locale),
                        callback_data="claude:list",
                    ),
                ]
            )

        return InlineKeyboardMarkup(buttons)

    def create_claude_processing_keyboard(
        self, locale: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create keyboard shown during Claude Code execution."""
        buttons = [
            [
                InlineKeyboardButton(
                    t("inline.claude.stop", locale), callback_data="claude:stop"
                )
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    def create_claude_complete_keyboard(
        self,
        has_session: bool = True,
        is_locked: bool = False,
        current_model: str = "sonnet",
        session_id: Optional[str] = None,
        voice_url: Optional[str] = None,
        note_paths: Optional[List[str]] = None,
        show_model_buttons: bool = True,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard shown after Claude Code completion.

        Args:
            note_paths: List of vault-relative paths to markdown notes for view buttons
            show_model_buttons: Whether to show model selection buttons (from user settings)
        """
        buttons = []

        # Add note view buttons first (up to 3 notes, 1 per row)
        if note_paths:
            for note_path in note_paths[:3]:
                # Extract filename for display
                note_name = note_path.rsplit("/", 1)[-1]
                if note_name.endswith(".md"):
                    note_name = note_name[:-3]
                # Truncate long names
                if len(note_name) > 28:
                    note_name = note_name[:25] + "…"

                # Build callback data; truncate rather than delegating to callback manager for tests
                callback_data = f"note:view:{note_path}"
                if len(callback_data.encode("utf-8")) > 64:
                    callback_data = callback_data.encode("utf-8")[:64].decode(
                        "utf-8", errors="ignore"
                    )

                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"👁 {note_name}", callback_data=callback_data
                        )
                    ]
                )

        # Action buttons row
        buttons.append(
            [
                InlineKeyboardButton(
                    t("inline.claude.retry", locale), callback_data="claude:retry"
                ),
                InlineKeyboardButton(
                    t("inline.claude.more", locale), callback_data="claude:continue"
                ),
                InlineKeyboardButton(
                    t("inline.claude.new", locale), callback_data="claude:new"
                ),
            ]
        )

        # Model selection row (only if enabled in settings)
        if show_model_buttons:
            model_buttons = []
            models = [("haiku", "⚡"), ("sonnet", "🎵"), ("opus", "🎭")]
            for model_name, emoji in models:
                is_current = current_model == model_name
                label = f"{emoji} {model_name.title()}" + (" ✓" if is_current else "")
                model_buttons.append(
                    InlineKeyboardButton(
                        label, callback_data=f"claude:model:{model_name}"
                    )
                )
            buttons.append(model_buttons)

        # Add lock/unlock button
        if is_locked:
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.unlock_mode", locale),
                        callback_data="claude:unlock",
                    ),
                ]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton(
                        t("inline.claude.lock_mode", locale),
                        callback_data="claude:lock",
                    ),
                ]
            )

        # Voice button hidden for now
        # if voice_url:
        #     buttons.append(
        #         [
        #             InlineKeyboardButton(
        #                 t("inline.claude.continue_voice", locale), url=voice_url
        #             )
        #         ]
        #     )

        return InlineKeyboardMarkup(buttons)

    def create_claude_locked_keyboard(
        self, locale: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create keyboard for locked Claude mode - shows unlock option."""
        buttons = [
            [
                InlineKeyboardButton(
                    t("inline.claude.unlock", locale),
                    callback_data="claude:unlock",
                ),
                InlineKeyboardButton(
                    t("inline.claude.new_session", locale),
                    callback_data="claude:new",
                ),
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    def create_claude_sessions_keyboard(
        self,
        sessions: list,
        current_session_id: str = None,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create keyboard for listing Claude Code sessions."""
        buttons = []

        for session in sessions[:5]:  # Limit to 5 sessions
            session_id = session.session_id
            emoji = get_session_emoji(session_id)

            # Show session name if available, otherwise show prompt preview
            name = getattr(session, "name", None)
            if name:
                display_text = str(name)[:30]  # Limit to 30 chars
            else:
                prompt_preview = (
                    getattr(session, "last_prompt", "No prompt") or "No prompt"
                )
                display_text = str(prompt_preview)[:20]

            is_current = session_id == current_session_id

            prefix = "▶️" if is_current else emoji
            label = f"{prefix} {display_text}"

            # Add session buttons in a row: [Select] [Delete]
            row = [
                InlineKeyboardButton(
                    label, callback_data=f"claude:select:{session_id[:16]}"
                ),
                InlineKeyboardButton(
                    "🗑️", callback_data=f"claude:delete:{session_id[:16]}"
                ),
            ]
            buttons.append(row)

        # Add action buttons
        buttons.append(
            [
                InlineKeyboardButton(
                    t("inline.claude.new", locale), callback_data="claude:new"
                ),
                InlineKeyboardButton(
                    t("inline.claude.back", locale), callback_data="claude:back"
                ),
            ]
        )

        return InlineKeyboardMarkup(buttons)

    def create_claude_confirm_keyboard(
        self, action: str, session_id: str = None, locale: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create confirmation keyboard for Claude actions."""
        data = f"claude:confirm_{action}"
        if session_id:
            data += f":{session_id[:16]}"

        buttons = [
            [
                InlineKeyboardButton(
                    t("inline.common.confirm", locale), callback_data=data
                ),
                InlineKeyboardButton(
                    t("inline.common.cancel", locale),
                    callback_data="claude:cancel",
                ),
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    # =========================================================================
    # Settings Keyboards
    # =========================================================================

    def create_settings_keyboard(
        self,
        keyboard_enabled: bool,
        auto_forward_voice: bool = True,
        transcript_correction_level: str = "vocabulary",
        show_model_buttons: bool = False,
        default_model: str = "sonnet",
        show_transcript: bool = True,
        whisper_use_locale: bool = False,
        locale: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        """Create settings menu inline keyboard."""
        # Correction level display
        correction_keys = {
            "none": "inline.settings.corrections_off",
            "vocabulary": "inline.settings.corrections_terms",
            "full": "inline.settings.corrections_full",
        }
        correction_key = correction_keys.get(
            transcript_correction_level, "inline.settings.corrections_terms"
        )
        correction_label = t(correction_key, locale)

        # Model display
        model_emojis = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}
        model_emoji = model_emojis.get(default_model, "🎵")

        buttons = [
            [
                InlineKeyboardButton(
                    (
                        t("inline.settings.disable_keyboard", locale)
                        if keyboard_enabled
                        else t("inline.settings.enable_keyboard", locale)
                    ),
                    callback_data="settings:toggle_keyboard",
                )
            ],
            [
                InlineKeyboardButton(
                    (
                        t("inline.settings.voice_claude_on", locale)
                        if auto_forward_voice
                        else t("inline.settings.voice_claude_off", locale)
                    ),
                    callback_data="settings:toggle_voice_forward",
                )
            ],
            [
                InlineKeyboardButton(
                    correction_label,
                    callback_data="settings:cycle_correction_level",
                )
            ],
            [
                InlineKeyboardButton(
                    (
                        t("inline.settings.transcripts_on", locale)
                        if show_transcript
                        else t("inline.settings.transcripts_off", locale)
                    ),
                    callback_data="settings:toggle_transcript",
                )
            ],
            [
                InlineKeyboardButton(
                    (
                        t("inline.settings.model_buttons_on", locale)
                        if show_model_buttons
                        else t("inline.settings.model_buttons_off", locale)
                    ),
                    callback_data="settings:toggle_model_buttons",
                )
            ],
            [
                InlineKeyboardButton(
                    t(
                        "inline.settings.default_model",
                        locale,
                        emoji=model_emoji,
                        model=default_model.title(),
                    ),
                    callback_data="settings:cycle_default_model",
                )
            ],
            [
                InlineKeyboardButton(
                    (
                        t("inline.settings.whisper_locale_on", locale)
                        if whisper_use_locale
                        else t("inline.settings.whisper_locale_off", locale)
                    ),
                    callback_data="settings:toggle_whisper_locale",
                )
            ],
            [
                InlineKeyboardButton(
                    t("inline.settings.customize_layout", locale),
                    callback_data="settings:customize",
                )
            ],
            [
                InlineKeyboardButton(
                    t("inline.settings.reset_default", locale),
                    callback_data="settings:reset",
                )
            ],
            [
                InlineKeyboardButton(
                    t("inline.common.back_to_settings", locale),
                    callback_data="settings:back",
                )
            ],
        ]
        return InlineKeyboardMarkup(buttons)

    def create_keyboard_customize_menu(
        self, available_buttons: Dict[str, dict], locale: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create button selection menu for customization."""
        buttons: List[List[InlineKeyboardButton]] = []

        for key, btn in available_buttons.items():
            emoji = btn.get("emoji", "")
            label = btn.get("label", key)
            desc = btn.get("description", "")
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{emoji} {label} - {desc}",
                        callback_data=f"settings:add_btn:{key}",
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    t("inline.claude.back", locale), callback_data="settings:back"
                )
            ]
        )
        return InlineKeyboardMarkup(buttons)


# Global instance
_keyboard_utils: Optional[KeyboardUtils] = None


def get_keyboard_utils() -> KeyboardUtils:
    """Get the global keyboard utils instance"""
    global _keyboard_utils
    if _keyboard_utils is None:
        _keyboard_utils = KeyboardUtils()
    return _keyboard_utils
