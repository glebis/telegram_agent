"""Tests for beads integration in ArchitectureReviewTask."""

from unittest.mock import AsyncMock, patch

import pytest

from scripts.proactive_tasks.tasks.architecture_review import ArchitectureReviewTask


class TestFileBeadsIssues:
    """Tests for _file_beads_issues beads integration."""

    def _make_task(self):
        return ArchitectureReviewTask(config={})

    async def test_returns_empty_when_no_issues(self):
        task = self._make_task()
        result = await task._file_beads_issues([])
        assert result == []

    async def test_returns_empty_when_beads_unavailable(self):
        task = self._make_task()
        mock_svc = AsyncMock()
        mock_svc.is_available.return_value = False

        import src.services.beads_service as mod

        with patch.object(mod, "_beads_service", mock_svc):
            result = await task._file_beads_issues(
                [{"title": "Test", "priority": "P0"}]
            )
        assert result == []

    async def test_creates_beads_issues_when_available(self):
        task = self._make_task()
        mock_svc = AsyncMock()
        mock_svc.is_available.return_value = True
        mock_svc.create_issue.return_value = {"id": "bd-abc1"}

        import src.services.beads_service as mod

        with patch.object(mod, "_beads_service", mock_svc):
            result = await task._file_beads_issues(
                [{"title": "Import error: foo", "priority": "P0"}]
            )

        assert result == ["bd-abc1"]
        mock_svc.create_issue.assert_called_once_with(
            "Import error: foo", priority=0, issue_type="bug"
        )

    async def test_maps_priority_strings_to_ints(self):
        task = self._make_task()
        mock_svc = AsyncMock()
        mock_svc.is_available.return_value = True
        mock_svc.create_issue.return_value = {"id": "bd-x"}

        import src.services.beads_service as mod

        issues = [
            {"title": "A", "priority": "P0"},
            {"title": "B", "priority": "P1"},
            {"title": "C", "priority": "P3"},
        ]

        with patch.object(mod, "_beads_service", mock_svc):
            result = await task._file_beads_issues(issues)

        assert len(result) == 3
        calls = mock_svc.create_issue.call_args_list
        assert calls[0].kwargs["priority"] == 0
        assert calls[1].kwargs["priority"] == 1
        assert calls[2].kwargs["priority"] == 3

    async def test_handles_create_failure_gracefully(self):
        task = self._make_task()
        mock_svc = AsyncMock()
        mock_svc.is_available.return_value = True
        mock_svc.create_issue.side_effect = [
            {"id": "bd-ok"},
            Exception("bd error"),
            {"id": "bd-ok2"},
        ]

        import src.services.beads_service as mod

        issues = [
            {"title": "A", "priority": "P0"},
            {"title": "B", "priority": "P1"},
            {"title": "C", "priority": "P2"},
        ]

        with patch.object(mod, "_beads_service", mock_svc):
            result = await task._file_beads_issues(issues)

        assert result == ["bd-ok", "", "bd-ok2"]
