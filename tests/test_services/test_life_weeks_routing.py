"""Tests for Life Weeks reply context and vault routing.

TDD: RED → GREEN → REFACTOR for reflection handling and vault note creation.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest


class TestReflectionPrompt:
    """Slice 1: Generate a reflection prompt for the user's current life week."""

    def test_generate_prompt_includes_week_number(self):
        from src.services.life_weeks_service import generate_reflection_prompt

        prompt = generate_reflection_prompt(
            week_number=1565, birth_date=date(1996, 2, 20)
        )
        assert "1565" in prompt or "1,565" in prompt

    def test_generate_prompt_includes_question(self):
        from src.services.life_weeks_service import generate_reflection_prompt

        prompt = generate_reflection_prompt(
            week_number=1565, birth_date=date(1996, 2, 20)
        )
        assert "?" in prompt  # Should ask a reflection question

    def test_generate_prompt_varies_by_week(self):
        from src.services.life_weeks_service import generate_reflection_prompt

        p1 = generate_reflection_prompt(week_number=100, birth_date=date(2024, 1, 1))
        p2 = generate_reflection_prompt(week_number=101, birth_date=date(2024, 1, 1))
        # Questions should rotate (don't need to be unique, but content varies)
        assert p1 != p2 or "100" in p1  # At minimum, week number differs


class TestReflectionProcessing:
    """Slice 2: Process a user's reflection reply."""

    def test_process_reflection_returns_entry_dict(self):
        from src.services.life_weeks_service import process_reflection

        result = process_reflection(
            user_id=123,
            week_number=1565,
            text="This week I learned about patience.",
        )
        assert result["user_id"] == 123
        assert result["week_number"] == 1565
        assert result["status"] == "completed"
        assert "patience" in result["reflection"]

    def test_process_skip_returns_skipped(self):
        from src.services.life_weeks_service import process_reflection

        result = process_reflection(
            user_id=123,
            week_number=1565,
            text="/skip",
        )
        assert result["status"] == "skipped"


class TestVaultNoteFormatting:
    """Slice 3: Format a life week reflection as a vault note."""

    def test_format_vault_note_has_frontmatter(self):
        from src.services.life_weeks_service import format_vault_note

        note = format_vault_note(
            week_number=1565,
            birth_date=date(1996, 2, 20),
            reflection="This week I learned about patience.",
            date_completed=date(2026, 2, 20),
        )
        assert "---" in note  # YAML frontmatter
        assert "1565" in note

    def test_format_vault_note_has_reflection_text(self):
        from src.services.life_weeks_service import format_vault_note

        note = format_vault_note(
            week_number=1565,
            birth_date=date(1996, 2, 20),
            reflection="This week I learned about patience.",
            date_completed=date(2026, 2, 20),
        )
        assert "patience" in note

    def test_format_vault_note_has_metadata(self):
        from src.services.life_weeks_service import format_vault_note

        note = format_vault_note(
            week_number=1565,
            birth_date=date(1996, 2, 20),
            reflection="Great week.",
            date_completed=date(2026, 2, 20),
        )
        assert "2026-02-20" in note
        assert "life-weeks" in note.lower() or "life_weeks" in note.lower()


class TestVaultPath:
    """Slice 4: Determine the vault path for a life weeks note."""

    def test_vault_path_includes_year(self):
        from src.services.life_weeks_service import get_vault_note_path

        path = get_vault_note_path(week_number=1565, date_completed=date(2026, 2, 20))
        assert "2026" in path

    def test_vault_path_includes_week(self):
        from src.services.life_weeks_service import get_vault_note_path

        path = get_vault_note_path(week_number=1565, date_completed=date(2026, 2, 20))
        assert "1565" in path

    def test_vault_path_is_markdown(self):
        from src.services.life_weeks_service import get_vault_note_path

        path = get_vault_note_path(week_number=1565, date_completed=date(2026, 2, 20))
        assert path.endswith(".md")
