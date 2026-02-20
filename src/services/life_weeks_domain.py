"""Pure domain logic for Life Weeks feature.

No database, no I/O — only data transformations and decision logic.
"""

from datetime import date, datetime
from typing import Optional

ASSUMED_LIFESPAN_YEARS = 80
WEEKS_PER_YEAR = 52


def calculate_life_week(birth_date: date, reference_date: Optional[date] = None) -> int:
    """Calculate the current life week number from birth date.

    Args:
        birth_date: The user's date of birth.
        reference_date: Date to calculate from (defaults to today).

    Returns:
        Integer week number (0-indexed: week 0 = first 7 days of life).

    Raises:
        ValueError: If birth_date is None or in the future.
        TypeError: If birth_date is not a date.
    """
    if birth_date is None:
        raise TypeError("birth_date cannot be None")

    if reference_date is None:
        reference_date = date.today()

    if birth_date > reference_date:
        raise ValueError(
            f"birth_date ({birth_date}) cannot be in the future "
            f"relative to reference_date ({reference_date})"
        )

    delta = reference_date - birth_date
    return delta.days // 7


def format_life_week(week_number: int, birth_date: date) -> str:
    """Format life week info for display.

    Args:
        week_number: Current life week number.
        birth_date: User's birth date for age calculation.

    Returns:
        Formatted string with week number, age, and progress percentage.
    """
    years = week_number / WEEKS_PER_YEAR
    total_weeks = ASSUMED_LIFESPAN_YEARS * WEEKS_PER_YEAR
    percentage = (week_number / total_weeks) * 100

    return (
        f"📅 Week {week_number:,} of your life\n"
        f"🎂 Age: {years:.1f} years\n"
        f"⏳ {percentage:.1f}% of ~{ASSUMED_LIFESPAN_YEARS} years"
    )


def should_notify(
    notification_day: int,
    notification_hour: int,
    now: Optional[datetime] = None,
) -> bool:
    """Determine if a notification should be sent now.

    Args:
        notification_day: Day of week (0=Monday, 6=Sunday).
        notification_hour: Hour of day (0-23).
        now: Current datetime (defaults to datetime.now()).

    Returns:
        True if current day and hour match the notification schedule.
    """
    if now is None:
        now = datetime.now()

    return now.weekday() == notification_day and now.hour == notification_hour
