"""Life Weeks settings UI logic.

Builds inline keyboards and formats messages for Life Weeks
configuration. Pure presentation logic — no database access.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DAYS_OF_WEEK = [
    ("Mon", "Monday"),
    ("Tue", "Tuesday"),
    ("Wed", "Wednesday"),
    ("Thu", "Thursday"),
    ("Fri", "Friday"),
    ("Sat", "Saturday"),
    ("Sun", "Sunday"),
]

_HOUR_OPTIONS = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 21]

CB_PREFIX = "lw_"


def build_settings_keyboard(
    birth_date: Optional[date],
    notification_day: int,
    notification_hour: int,
    enabled: bool,
) -> List[List[Dict[str, str]]]:
    """Build inline keyboard for Life Weeks settings.

    Returns:
        List of button rows, each row is a list of dicts with "text" and "callback_data".
    """
    rows: List[List[Dict[str, str]]] = []

    # Birth date row
    bd_text = (
        f"🎂 Birth date: {birth_date.isoformat()}"
        if birth_date
        else "🎂 Set birth date"
    )
    rows.append([{"text": bd_text, "callback_data": f"{CB_PREFIX}set_birth_date"}])

    # Notification day
    day_name = _DAYS_OF_WEEK[notification_day][1] if 0 <= notification_day < 7 else "?"
    rows.append(
        [
            {
                "text": f"📅 Notification day: {day_name}",
                "callback_data": f"{CB_PREFIX}set_day",
            }
        ]
    )

    # Notification hour
    rows.append(
        [
            {
                "text": f"🕐 Notification hour: {notification_hour}:00",
                "callback_data": f"{CB_PREFIX}set_hour",
            }
        ]
    )

    # Enable/disable toggle
    if enabled:
        rows.append(
            [
                {
                    "text": "✅ Enabled — tap to disable",
                    "callback_data": f"{CB_PREFIX}toggle",
                }
            ]
        )
    else:
        rows.append(
            [
                {
                    "text": "❌ Disabled — tap to enable",
                    "callback_data": f"{CB_PREFIX}toggle",
                }
            ]
        )

    return rows


def build_day_keyboard(current_day: int) -> List[List[Dict[str, str]]]:
    """Build inline keyboard for selecting notification day.

    Args:
        current_day: Currently selected day (0=Monday).

    Returns:
        List of button rows with day options.
    """
    rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []

    for idx, (short, full) in enumerate(_DAYS_OF_WEEK):
        marker = " ✓" if idx == current_day else ""
        row.append(
            {
                "text": f"{short}{marker}",
                "callback_data": f"{CB_PREFIX}day_{idx}",
            }
        )
        if len(row) == 4:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([{"text": "← Back", "callback_data": f"{CB_PREFIX}back"}])
    return rows


def build_hour_keyboard(current_hour: int) -> List[List[Dict[str, str]]]:
    """Build inline keyboard for selecting notification hour.

    Args:
        current_hour: Currently selected hour (0-23).

    Returns:
        List of button rows with hour options.
    """
    rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []

    for hour in _HOUR_OPTIONS:
        marker = " ✓" if hour == current_hour else ""
        row.append(
            {
                "text": f"{hour}:00{marker}",
                "callback_data": f"{CB_PREFIX}hour_{hour}",
            }
        )
        if len(row) == 4:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([{"text": "← Back", "callback_data": f"{CB_PREFIX}back"}])
    return rows


def format_settings_message(
    birth_date: Optional[date],
    notification_day: int,
    notification_hour: int,
    enabled: bool,
    current_week: Optional[int],
) -> str:
    """Format the Life Weeks settings status message.

    Args:
        birth_date: User's birth date (None if not set).
        notification_day: Day of week (0=Monday).
        notification_hour: Hour of day.
        enabled: Whether notifications are enabled.
        current_week: Current life week number (None if birth_date not set).

    Returns:
        Formatted settings message.
    """
    if not birth_date:
        return (
            "📅 <b>Life Weeks Settings</b>\n\n"
            "Birth date not set. Please set your birth date to get started."
        )

    day_name = (
        _DAYS_OF_WEEK[notification_day][1] if 0 <= notification_day < 7 else "Unknown"
    )
    status = "✅ Enabled" if enabled else "❌ Disabled"

    week_info = ""
    if current_week is not None:
        week_info = f"\n🔢 Current week: <b>{current_week:,}</b>"

    return (
        f"📅 <b>Life Weeks Settings</b>\n\n"
        f"🎂 Birth date: {birth_date.isoformat()}{week_info}\n"
        f"📅 Notification: {day_name} at {notification_hour}:00\n"
        f"Status: {status}"
    )
