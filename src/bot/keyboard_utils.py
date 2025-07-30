import logging
from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.mode_manager import ModeManager
from .callback_data_manager import get_callback_data_manager

logger = logging.getLogger(__name__)


class KeyboardUtils:
    """Utility class for creating Telegram inline keyboards"""

    def __init__(self):
        self.mode_manager = ModeManager()
        self.callback_manager = get_callback_data_manager()

    def create_reanalysis_keyboard(
        self, file_id: str, current_mode: str, current_preset: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create context-aware keyboard for image reanalysis"""

        buttons = []

        if current_mode == "default":
            # Currently in default mode - show all artistic presets
            artistic_presets = self.mode_manager.get_mode_presets("artistic")

            for preset in artistic_presets:
                callback_data = self.callback_manager.create_callback_data(
                    action="reanalyze", file_id=file_id, mode="artistic", preset=preset
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
            callback_data = self.callback_manager.create_callback_data(
                action="reanalyze", file_id=file_id, mode="default", preset=None
            )
            buttons.append(
                InlineKeyboardButton("📝 Quick Analysis", callback_data=callback_data)
            )

            # Show other artistic presets (excluding current one)
            artistic_presets = self.mode_manager.get_mode_presets("artistic")

            for preset in artistic_presets:
                if preset != current_preset:  # Skip current preset
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
        self, current_mode: str = "default", current_preset: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        """Create keyboard for general mode selection (for /mode command)"""

        buttons = []

        # Default mode button
        if current_mode != "default":
            buttons.append(
                InlineKeyboardButton("📝 Quick Analysis", callback_data="mode:default:")
            )

        # Artistic mode buttons
        artistic_presets = self.mode_manager.get_mode_presets("artistic")

        for preset in artistic_presets:
            # Skip current preset if in artistic mode
            if current_mode == "artistic" and preset == current_preset:
                continue

            callback_data = f"mode:artistic:{preset}"

            # Choose appropriate emoji for each preset
            if preset == "Critic":
                emoji = "🎨"
                text = f"{emoji} Art Critic"
            elif preset == "Photo-coach":
                emoji = "📸"
                text = f"{emoji} Photo Coach"
            elif preset == "Creative":
                emoji = "✨"
                text = f"{emoji} Creative"
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

    def create_confirmation_keyboard(
        self, action: str, data: str
    ) -> InlineKeyboardMarkup:
        """Create confirmation keyboard for destructive actions"""

        buttons = [
            [
                InlineKeyboardButton(
                    "✅ Confirm", callback_data=f"confirm:{action}:{data}"
                ),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action}"),
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
        self, images: List[Dict], page: int, total_pages: int
    ) -> InlineKeyboardMarkup:
        """Create keyboard for gallery navigation and image actions"""

        buttons = []

        # Image action buttons (View Full Analysis for each image)
        for i, image in enumerate(images, 1):
            image_id = image["id"]
            button_text = f"🔍 View Image {(page-1)*10 + i}"
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
                    "◀️ Previous", callback_data=f"gallery:page:{page-1}"
                )
            )

        # Page indicator (non-clickable)
        nav_buttons.append(
            InlineKeyboardButton(
                f"📋 {page}/{total_pages}", callback_data="gallery:noop"
            )
        )

        # Next button
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton("Next ▶️", callback_data=f"gallery:page:{page+1}")
            )

        if nav_buttons:
            keyboard_rows.append(nav_buttons)

        # Back to menu button
        keyboard_rows.append(
            [InlineKeyboardButton("🏠 Main Menu", callback_data="gallery:menu")]
        )

        return InlineKeyboardMarkup(keyboard_rows)

    def create_image_detail_keyboard(
        self, image_id: int, current_mode: str, current_preset: Optional[str], page: int
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
                    "📝 Quick Analysis",
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
                    "◀️ Back to Gallery", callback_data=f"gallery:page:{page}"
                ),
                InlineKeyboardButton("🏠 Main Menu", callback_data="gallery:menu"),
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


# Global instance
_keyboard_utils: Optional[KeyboardUtils] = None


def get_keyboard_utils() -> KeyboardUtils:
    """Get the global keyboard utils instance"""
    global _keyboard_utils
    if _keyboard_utils is None:
        _keyboard_utils = KeyboardUtils()
    return _keyboard_utils
