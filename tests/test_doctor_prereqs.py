"""Tests for doctor.py plugin prerequisite matching.

Ensures check_plugin_health uses stable identifiers (directory name / id)
instead of the user-facing 'name' field for prereq detection.
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import yaml

from src.preflight.models import CheckStatus


class TestDoctorPluginPrereqSlugMatching:
    """doctor.py prereq checks must key off slug/id, not display name."""

    def _make_plugin(self, plugins_root: Path, dir_name: str, config: dict):
        """Helper to create a plugin directory with plugin.yaml."""
        plugin_dir = plugins_root / dir_name
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.dump(config))
        return plugin_dir

    def test_pdf_prereq_detected_via_dir_name(self, tmp_path):
        """PDF prereq warning fires when dir is 'pdf', even if name differs."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        self._make_plugin(
            plugins_root, "pdf", {"name": "Fancy PDF Suite", "enabled": True}
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        warnings = [r for r in results if r.status == CheckStatus.WARNING]
        assert any(
            "marker_single" in r.message for r in warnings
        ), f"Expected marker_single warning, got: {[r.message for r in results]}"

    def test_claude_prereq_detected_via_dir_name(self, tmp_path):
        """Claude prereq fires when dir is 'claude_code', regardless of name."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        self._make_plugin(
            plugins_root,
            "claude_code",
            {"name": "My Custom Claude Integration", "enabled": True},
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        warnings = [r for r in results if r.status == CheckStatus.WARNING]
        assert any(
            "Claude Code CLI" in r.message for r in warnings
        ), f"Expected Claude CLI warning, got: {[r.message for r in results]}"

    def test_explicit_id_overrides_dir_name(self, tmp_path):
        """Explicit 'id' in plugin.yaml takes precedence over directory name."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        # Dir name is "something_else" but id is "pdf"
        self._make_plugin(
            plugins_root,
            "something_else",
            {"name": "PDF Converter", "id": "pdf", "enabled": True},
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        warnings = [r for r in results if r.status == CheckStatus.WARNING]
        assert any(
            "marker_single" in r.message for r in warnings
        ), f"Expected marker_single warning via id override, got: {[r.message for r in results]}"

    def test_name_alone_does_not_trigger_prereq(self, tmp_path):
        """A plugin with name='pdf' but dir='custom' and no id should NOT match."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        # Only "name" is pdf, dir is "custom_tool", no id field
        self._make_plugin(
            plugins_root,
            "custom_tool",
            {"name": "pdf", "enabled": True},
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        # Should pass (no prereqs to check for "custom_tool" slug)
        warnings = [r for r in results if r.status == CheckStatus.WARNING]
        assert not any(
            "marker_single" in r.message for r in warnings
        ), "name alone should NOT trigger prereq check"

    def test_case_insensitive_matching(self, tmp_path):
        """Prereq matching is case-insensitive for the identifier."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        self._make_plugin(
            plugins_root,
            "PDF",
            {"name": "PDF Plugin", "enabled": True},
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        warnings = [r for r in results if r.status == CheckStatus.WARNING]
        assert any(
            "marker_single" in r.message for r in warnings
        ), f"Case-insensitive match should trigger, got: {[r.message for r in results]}"

    def test_no_prereqs_for_unknown_plugin(self, tmp_path):
        """A plugin with an unrecognized slug should pass without warnings."""
        from scripts.doctor import check_plugin_health

        plugins_root = tmp_path / "plugins"
        self._make_plugin(
            plugins_root,
            "my_custom_tool",
            {"name": "My Tool", "enabled": True},
        )

        with (
            patch("scripts.doctor.PLUGINS_ROOT", plugins_root),
            patch("scripts.doctor.shutil.which", return_value=None),
        ):
            results = check_plugin_health()

        for r in results:
            assert r.status != CheckStatus.WARNING, f"Unexpected warning: {r.message}"
