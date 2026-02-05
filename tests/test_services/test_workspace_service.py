"""Tests for workspace_service — per-chat CLAUDE.md memory."""

import pytest

from src.services.workspace_service import (
    DEFAULT_TEMPLATE,
    WORKSPACES_DIR,
    append_memory,
    ensure_workspace,
    export_memory_path,
    get_memory,
    reset_memory,
    update_memory,
)


@pytest.fixture(autouse=True)
def _patch_workspaces_dir(tmp_path, monkeypatch):
    """Redirect WORKSPACES_DIR to tmp_path for all tests."""
    monkeypatch.setattr(
        "src.services.workspace_service.WORKSPACES_DIR", tmp_path
    )


class TestEnsureWorkspace:
    def test_creates_dir_and_file(self, tmp_path):
        ws = ensure_workspace(123)
        assert ws.is_dir()
        memory_file = ws / "CLAUDE.md"
        assert memory_file.exists()
        assert memory_file.read_text() == DEFAULT_TEMPLATE

    def test_idempotent_does_not_overwrite(self, tmp_path):
        ensure_workspace(123)
        # Manually change content
        memory_file = tmp_path / "123" / "CLAUDE.md"
        memory_file.write_text("custom content")

        # Call again — should NOT overwrite
        ensure_workspace(123)
        assert memory_file.read_text() == "custom content"


class TestGetMemory:
    def test_returns_none_for_nonexistent_chat(self):
        assert get_memory(999) is None

    def test_returns_content_for_existing_chat(self, tmp_path):
        ensure_workspace(42)
        content = get_memory(42)
        assert content == DEFAULT_TEMPLATE

    def test_returns_custom_content(self, tmp_path):
        ensure_workspace(42)
        (tmp_path / "42" / "CLAUDE.md").write_text("hello world")
        assert get_memory(42) == "hello world"


class TestUpdateMemory:
    def test_overwrites_content(self):
        ensure_workspace(10)
        update_memory(10, "new content")
        assert get_memory(10) == "new content"

    def test_creates_workspace_if_missing(self):
        update_memory(11, "from scratch")
        assert get_memory(11) == "from scratch"


class TestAppendMemory:
    def test_appends_to_existing(self):
        ensure_workspace(20)
        append_memory(20, "extra line")
        content = get_memory(20)
        assert content.endswith("\nextra line")
        assert content.startswith(DEFAULT_TEMPLATE)

    def test_creates_workspace_if_missing(self):
        append_memory(21, "appended")
        content = get_memory(21)
        assert "appended" in content


class TestResetMemory:
    def test_restores_template(self):
        ensure_workspace(30)
        update_memory(30, "custom stuff")
        reset_memory(30)
        assert get_memory(30) == DEFAULT_TEMPLATE


class TestExportMemoryPath:
    def test_returns_path_when_exists(self):
        ensure_workspace(40)
        path = export_memory_path(40)
        assert path is not None
        assert path.name == "CLAUDE.md"

    def test_returns_none_when_missing(self):
        assert export_memory_path(404) is None


class TestPathTraversalProtection:
    def test_int_coercion_blocks_traversal(self):
        """chat_id is forced through int(), so path injection is impossible."""
        with pytest.raises((ValueError, TypeError)):
            ensure_workspace("../etc")  # type: ignore[arg-type]
