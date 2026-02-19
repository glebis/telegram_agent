"""
Tests for work_summary_service — formatting work statistics.

Extracted from handler layer (#218).
"""

import pytest


class TestFormatWorkSummary:
    """Tests for format_work_summary function in service layer."""

    def test_import_from_service(self):
        """Function should be importable from services.work_summary_service."""
        from src.services.work_summary_service import format_work_summary

        assert callable(format_work_summary)

    def test_empty_stats(self):
        from src.services.work_summary_service import format_work_summary

        assert format_work_summary({}) == ""

    def test_none_stats(self):
        from src.services.work_summary_service import format_work_summary

        assert format_work_summary(None) == ""

    def test_duration_only(self):
        from src.services.work_summary_service import format_work_summary

        result = format_work_summary({"duration": "45s"})
        assert "45s" in result
        assert "<i>" in result
        assert "</i>" in result

    def test_duration_minutes(self):
        from src.services.work_summary_service import format_work_summary

        result = format_work_summary({"duration": "2m 30s"})
        assert "2m 30s" in result

    def test_read_tools(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Read": 5}}
        result = format_work_summary(stats)
        assert "5 reads" in result

    def test_write_tools(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Write": 2}}
        result = format_work_summary(stats)
        assert "2 edits" in result

    def test_edit_tools(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Edit": 3}}
        result = format_work_summary(stats)
        assert "3 edits" in result

    def test_write_and_edit_combined(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Write": 2, "Edit": 3}}
        result = format_work_summary(stats)
        assert "5 edits" in result

    def test_search_tools(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Grep": 4, "Glob": 2}}
        result = format_work_summary(stats)
        assert "6 searches" in result

    def test_bash_commands(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "30s", "tool_counts": {"Bash": 7}}
        result = format_work_summary(stats)
        assert "7 commands" in result

    def test_web_fetches(self):
        from src.services.work_summary_service import format_work_summary

        stats = {
            "duration": "1m 0s",
            "web_fetches": [
                "https://example.com",
                "https://docs.python.org",
                "search: AI research",
            ],
        }
        result = format_work_summary(stats)
        assert "3 web fetches" in result

    def test_skills_used(self):
        from src.services.work_summary_service import format_work_summary

        stats = {
            "duration": "2m 15s",
            "skills_used": ["tavily-search", "pdf-generation"],
        }
        result = format_work_summary(stats)
        assert "Skills:" in result
        assert "tavily-search" in result
        assert "pdf-generation" in result

    def test_full_stats(self):
        from src.services.work_summary_service import format_work_summary

        stats = {
            "duration": "3m 45s",
            "tool_counts": {
                "Read": 10,
                "Write": 3,
                "Edit": 5,
                "Grep": 8,
                "Glob": 2,
                "Bash": 4,
            },
            "web_fetches": ["https://example.com"],
            "skills_used": ["deep-research"],
            "bash_commands": ["npm install", "npm test"],
        }
        result = format_work_summary(stats)
        assert "3m 45s" in result
        assert "10 reads" in result
        assert "8 edits" in result
        assert "10 searches" in result
        assert "4 commands" in result
        assert "1 web fetch" in result
        assert "deep-research" in result
        assert "</i>" in result
        assert " · " in result

    def test_empty_tool_counts(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "10s", "tool_counts": {}}
        result = format_work_summary(stats)
        assert "10s" in result
        assert "reads" not in result

    def test_zero_counts_ignored(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "10s", "tool_counts": {"Read": 0, "Write": 0, "Bash": 3}}
        result = format_work_summary(stats)
        assert "3 commands" in result
        assert "reads" not in result
        assert "edits" not in result

    def test_empty_web_fetches(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "10s", "web_fetches": []}
        result = format_work_summary(stats)
        assert "web fetch" not in result

    def test_empty_skills(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"duration": "10s", "skills_used": []}
        result = format_work_summary(stats)
        assert "Skills" not in result

    def test_no_duration(self):
        from src.services.work_summary_service import format_work_summary

        stats = {"tool_counts": {"Read": 3}}
        result = format_work_summary(stats)
        assert "3 reads" in result
        assert "⏱" not in result


class TestBackwardsCompatFormatWorkSummary:
    """The old import path should still work via re-export."""

    def test_old_import_still_works(self):
        from src.bot.handlers.claude_commands import _format_work_summary

        assert callable(_format_work_summary)

    def test_old_and_new_are_same_function(self):
        from src.bot.handlers.claude_commands import (
            _format_work_summary as old_fn,
        )
        from src.services.work_summary_service import (
            format_work_summary as new_fn,
        )

        assert old_fn is new_fn
