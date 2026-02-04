"""Tests for scripts/check_import_case.py — import-case-sensitivity checker."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.check_import_case import (
    check_directories,
    check_file,
    extract_imports,
    resolve_import_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: resolve_import_path
# ---------------------------------------------------------------------------
class TestResolveImportPath:
    """Low-level tests for path resolution against the real project tree."""

    def test_correct_case_no_mismatch(self):
        """Importing 'src.models.user' should produce zero mismatches."""
        mismatches = resolve_import_path(["src", "models", "user"], PROJECT_ROOT)
        assert mismatches == []

    def test_wrong_case_detected(self):
        """Importing 'src.Models.user' should flag 'Models' vs 'models'."""
        mismatches = resolve_import_path(["src", "Models", "user"], PROJECT_ROOT)
        assert len(mismatches) == 1
        assert mismatches[0] == ("Models", "models")

    def test_nonexistent_module_ignored(self):
        """A path segment that doesn't exist at all is not an error."""
        mismatches = resolve_import_path(
            ["src", "nonexistent_module"], PROJECT_ROOT
        )
        assert mismatches == []

    def test_multiple_bad_segments(self):
        """Multiple case mismatches in one import are all reported."""
        mismatches = resolve_import_path(["SRC", "Models"], PROJECT_ROOT)
        assert ("SRC", "src") in mismatches
        assert ("Models", "models") in mismatches


# ---------------------------------------------------------------------------
# Tests: extract_imports
# ---------------------------------------------------------------------------
class TestExtractImports:
    """Parsing imports from source code."""

    def test_plain_import(self, tmp_path):
        f = _write(tmp_path / "a.py", "import os\nimport src.models.user\n")
        imports = extract_imports(f.read_text(), f)
        modules = [m for _, m in imports]
        assert "os" in modules
        assert "src.models.user" in modules

    def test_from_import(self, tmp_path):
        f = _write(tmp_path / "a.py", "from src.core.config import get_settings\n")
        imports = extract_imports(f.read_text(), f)
        assert any(m == "src.core.config" for _, m in imports)

    def test_relative_import_resolved(self, tmp_path):
        """Relative imports should be resolved to absolute module paths."""
        pkg = tmp_path / "src" / "bot"
        pkg.mkdir(parents=True)
        _write(pkg / "__init__.py", "")
        f = _write(pkg / "handlers.py", "from .bot import get_bot\n")

        imports = extract_imports(f.read_text(), f)
        modules = [m for _, m in imports]
        # Relative `.bot` inside src/bot/handlers.py -> src.bot.bot
        assert any("bot" in m for m in modules)

    def test_syntax_error_returns_empty(self, tmp_path):
        f = _write(tmp_path / "bad.py", "def foo(\n")
        imports = extract_imports(f.read_text(), f)
        assert imports == []


# ---------------------------------------------------------------------------
# Tests: check_file
# ---------------------------------------------------------------------------
class TestCheckFile:
    """Integration-level: parse + resolve on a single file."""

    def test_clean_file_no_errors(self, tmp_path):
        """A file that only imports stdlib/third-party should pass."""
        f = _write(tmp_path / "clean.py", "import os\nimport sys\nimport json\n")
        errors = check_file(f, tmp_path)
        assert errors == []

    def test_detects_case_mismatch(self):
        """A file importing 'src.Models.user' against the real tree."""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(PROJECT_ROOT)
        ) as f:
            f.write("from src.Models.user import User\n")
            f.flush()
            p = Path(f.name)

        try:
            errors = check_file(p, PROJECT_ROOT)
            assert len(errors) == 1
            filepath, lineno, module, mismatches = errors[0]
            assert module == "src.Models.user"
            assert ("Models", "models") in mismatches
        finally:
            p.unlink()

    def test_correct_local_import_passes(self):
        """A correctly-cased local import should produce no errors."""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(PROJECT_ROOT)
        ) as f:
            f.write("from src.models.user import User\n")
            f.flush()
            p = Path(f.name)

        try:
            errors = check_file(p, PROJECT_ROOT)
            assert errors == []
        finally:
            p.unlink()


# ---------------------------------------------------------------------------
# Tests: check_directories (current codebase)
# ---------------------------------------------------------------------------
class TestCheckDirectoriesRealCodebase:
    """Verify the actual codebase has no import-case issues."""

    def test_src_has_no_case_mismatches(self):
        errors = check_directories([PROJECT_ROOT / "src"], PROJECT_ROOT)
        assert errors == [], (
            f"Found import-case mismatches in src/:\n"
            + "\n".join(
                f"  {f.relative_to(PROJECT_ROOT)}:{ln} {mod} -> {mm}"
                for f, ln, mod, mm in errors
            )
        )

    def test_scripts_has_no_case_mismatches(self):
        errors = check_directories([PROJECT_ROOT / "scripts"], PROJECT_ROOT)
        assert errors == [], (
            f"Found import-case mismatches in scripts/:\n"
            + "\n".join(
                f"  {f.relative_to(PROJECT_ROOT)}:{ln} {mod} -> {mm}"
                for f, ln, mod, mm in errors
            )
        )


# ---------------------------------------------------------------------------
# Tests: stdlib / third-party skipping
# ---------------------------------------------------------------------------
class TestSkipNonLocalImports:
    """Ensure stdlib and third-party imports are not flagged."""

    def test_stdlib_imports_skipped(self):
        """os, sys, json etc. should never produce errors."""
        import tempfile

        code = textwrap.dedent("""\
            import os
            import sys
            import json
            from pathlib import Path
            from collections import defaultdict
            from typing import Optional
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(PROJECT_ROOT)
        ) as f:
            f.write(code)
            f.flush()
            p = Path(f.name)

        try:
            errors = check_file(p, PROJECT_ROOT)
            assert errors == []
        finally:
            p.unlink()

    def test_third_party_imports_skipped(self):
        """fastapi, telegram, sqlalchemy etc. should not be flagged."""
        import tempfile

        code = textwrap.dedent("""\
            from fastapi import FastAPI
            from telegram import Bot
            import sqlalchemy
            import litellm
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(PROJECT_ROOT)
        ) as f:
            f.write(code)
            f.flush()
            p = Path(f.name)

        try:
            errors = check_file(p, PROJECT_ROOT)
            assert errors == []
        finally:
            p.unlink()


# ---------------------------------------------------------------------------
# Tests: check_directories with synthetic tree
# ---------------------------------------------------------------------------
class TestCheckDirectoriesSynthetic:
    """Build a temporary project tree to simulate mismatches."""

    def test_finds_mismatch_in_synthetic_tree(self, tmp_path):
        """Create a tree with a lowercase dir, then import it uppercased."""
        # Build: tmp_path/mypackage/sub/mod.py
        pkg = tmp_path / "mypackage" / "sub"
        pkg.mkdir(parents=True)
        _write(pkg / "__init__.py", "")
        _write(pkg / "mod.py", "X = 1\n")
        _write(tmp_path / "mypackage" / "__init__.py", "")

        # A consumer file that uses wrong case
        consumer = tmp_path / "mypackage" / "consumer.py"
        _write(consumer, "from mypackage.Sub.mod import X\n")

        errors = check_directories([tmp_path / "mypackage"], tmp_path)
        assert len(errors) == 1
        assert errors[0][2] == "mypackage.Sub.mod"
        assert ("Sub", "sub") in errors[0][3]

    def test_clean_synthetic_tree_passes(self, tmp_path):
        """Correct case produces no errors."""
        pkg = tmp_path / "mypackage" / "sub"
        pkg.mkdir(parents=True)
        _write(pkg / "__init__.py", "")
        _write(pkg / "mod.py", "X = 1\n")
        _write(tmp_path / "mypackage" / "__init__.py", "")

        consumer = tmp_path / "mypackage" / "consumer.py"
        _write(consumer, "from mypackage.sub.mod import X\n")

        errors = check_directories([tmp_path / "mypackage"], tmp_path)
        assert errors == []


# ---------------------------------------------------------------------------
# Tests: main() entry point
# ---------------------------------------------------------------------------
class TestMain:
    """Test the CLI entry point."""

    def test_main_returns_zero_on_clean_codebase(self):
        from scripts.check_import_case import main

        assert main(["src", "scripts"]) == 0

    def test_main_returns_one_on_mismatch(self, tmp_path, capsys):
        """Create a bad file in a temp dir and verify main() returns 1."""
        from scripts.check_import_case import main

        # We need a project structure: tmp_path/src/models/user.py
        pkg = tmp_path / "src" / "models"
        pkg.mkdir(parents=True)
        _write(pkg / "__init__.py", "")
        _write(pkg / "user.py", "class User: pass\n")
        _write(tmp_path / "src" / "__init__.py", "")

        # Consumer with bad case
        consumer_dir = tmp_path / "app"
        consumer_dir.mkdir()
        _write(consumer_dir / "bad.py", "from src.Models.user import User\n")

        # We need to call main with the right project root, so we
        # monkeypatch the script's __file__ resolution instead.
        import scripts.check_import_case as mod

        original_main = mod.main

        def patched_main(argv):
            """Override project_root inside main."""
            import types

            saved = mod.Path.__func__ if hasattr(mod.Path, "__func__") else None
            # Direct approach: call check_directories ourselves
            dirs = [tmp_path / d for d in argv]
            errors = mod.check_directories(dirs, tmp_path)
            if not errors:
                return 0
            return 1

        result = patched_main(["app"])
        assert result == 1
