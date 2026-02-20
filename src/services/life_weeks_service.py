"""Life Weeks service — reflection prompts, processing, and vault routing.

Handles the application layer for Life Weeks:
- Generating weekly reflection prompts
- Processing user reflection replies
- Formatting notes for the Obsidian vault
"""

import logging
from datetime import date
from typing import Any, Dict

from .life_weeks_domain import WEEKS_PER_YEAR, format_life_week

logger = logging.getLogger(__name__)

# Rotating reflection questions
_REFLECTION_QUESTIONS = [
    "What was the most meaningful moment this week?",
    "What did you learn about yourself this week?",
    "What are you grateful for this week?",
    "What challenge did you face, and how did you handle it?",
    "What would you do differently if you could relive this week?",
    "What conversation or interaction stood out to you?",
    "How did you take care of yourself this week?",
]


def generate_reflection_prompt(week_number: int, birth_date: date) -> str:
    """Generate a reflection prompt for the given life week.

    Args:
        week_number: Current life week number.
        birth_date: User's birth date for context.

    Returns:
        Formatted prompt string with week info and a reflection question.
    """
    week_info = format_life_week(week_number, birth_date)
    question_idx = week_number % len(_REFLECTION_QUESTIONS)
    question = _REFLECTION_QUESTIONS[question_idx]

    return f"{week_info}\n\n💭 {question}"


def process_reflection(
    user_id: int,
    week_number: int,
    text: str,
) -> Dict[str, Any]:
    """Process a user's reflection reply.

    Args:
        user_id: Telegram user ID.
        week_number: Life week number being reflected on.
        text: User's reply text (or "/skip").

    Returns:
        Dict with user_id, week_number, status, and reflection.
    """
    if text.strip().lower() in ("/skip", "skip"):
        return {
            "user_id": user_id,
            "week_number": week_number,
            "status": "skipped",
            "reflection": None,
        }

    return {
        "user_id": user_id,
        "week_number": week_number,
        "status": "completed",
        "reflection": text.strip(),
    }


def format_vault_note(
    week_number: int,
    birth_date: date,
    reflection: str,
    date_completed: date,
) -> str:
    """Format a life week reflection as an Obsidian vault note.

    Args:
        week_number: Life week number.
        birth_date: User's birth date.
        reflection: The reflection text.
        date_completed: Date the reflection was completed.

    Returns:
        Markdown string with YAML frontmatter.
    """
    years = week_number / WEEKS_PER_YEAR

    return (
        f"---\n"
        f"type: life-weeks\n"
        f"week: {week_number}\n"
        f"date: {date_completed.isoformat()}\n"
        f"age_years: {years:.1f}\n"
        f"---\n\n"
        f"# Life Week {week_number}\n\n"
        f"{format_life_week(week_number, birth_date)}\n\n"
        f"## Reflection\n\n"
        f"{reflection}\n"
    )


def get_vault_note_path(week_number: int, date_completed: date) -> str:
    """Determine the vault path for a life weeks note.

    Args:
        week_number: Life week number.
        date_completed: Date the reflection was completed.

    Returns:
        Relative path within the vault (e.g., "life-weeks/2026/week-1565.md").
    """
    year = date_completed.year
    return f"life-weeks/{year}/week-{week_number}.md"
