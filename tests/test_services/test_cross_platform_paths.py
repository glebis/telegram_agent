"""Tests for cross-platform path handling (issues #39 and #46).

Verifies that:
- SRS services use config-based vault paths, not hardcoded /Users/server paths
- Claude code service uses shutil.which() for binary lookup
- All paths use expanduser() for ~ resolution
- No hardcoded usernames in path resolution
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(vault_path: str = "/tmp/test_vault"):
    """Create a mock Settings object with the given vault_path."""
    mock = MagicMock()
    mock.vault_path = vault_path
    return mock


# ---------------------------------------------------------------------------
# SRS Algorithm - vault path from config
# ---------------------------------------------------------------------------

class TestSRSAlgorithmPaths:
    """srs_algorithm.py must resolve vault path from config, not hardcoded."""

    def test_get_vault_path_returns_config_value(self):
        """get_vault_path() should return the configured vault_path."""
        with patch(
            "src.services.srs.srs_algorithm.get_settings",
            return_value=_mock_settings("/tmp/test_vault"),
        ):
            from src.services.srs.srs_algorithm import get_vault_path

            result = get_vault_path()
            assert result == Path("/tmp/test_vault")

    def test_get_vault_path_expands_tilde(self):
        """get_vault_path() should expand ~ in vault_path."""
        with patch(
            "src.services.srs.srs_algorithm.get_settings",
            return_value=_mock_settings("~/Research/vault"),
        ):
            from src.services.srs.srs_algorithm import get_vault_path

            result = get_vault_path()
            assert "~" not in str(result)
            assert result == Path.home() / "Research" / "vault"

    def test_no_hardcoded_users_server_in_source(self):
        """Source code must not contain hardcoded /Users/server paths."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "srs"
            / "srs_algorithm.py"
        )
        content = source_file.read_text()
        assert "/Users/server" not in content, (
            "srs_algorithm.py still contains hardcoded /Users/server path"
        )

    def test_update_card_rating_uses_config_vault_path(self):
        """update_card_rating should use config-based vault path."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = Path(tmpdir) / "vault"
            vault_dir.mkdir()
            db_path = Path(tmpdir) / "schedule.db"

            # Create a minimal test note
            note_path = "test_note.md"
            note_file = vault_dir / note_path
            note_file.write_text(
                "---\nsrs_enabled: true\nsrs_next_review: 2025-01-01\n---\nTest note\n"
            )

            # Create the DB with required tables
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS srs_cards (
                    id INTEGER PRIMARY KEY,
                    note_path TEXT UNIQUE,
                    note_type TEXT DEFAULT 'idea',
                    title TEXT DEFAULT '',
                    srs_enabled INTEGER DEFAULT 1,
                    next_review_date TEXT,
                    last_review_date TEXT,
                    interval_days INTEGER DEFAULT 1,
                    ease_factor REAL DEFAULT 2.5,
                    repetitions INTEGER DEFAULT 0,
                    is_due INTEGER DEFAULT 0,
                    total_reviews INTEGER DEFAULT 0,
                    last_synced TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_history (
                    id INTEGER PRIMARY KEY,
                    card_id INTEGER,
                    rating INTEGER,
                    interval_before INTEGER,
                    interval_after INTEGER,
                    ease_factor_before REAL,
                    ease_factor_after REAL,
                    reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                INSERT INTO srs_cards (
                    note_path, ease_factor, interval_days, repetitions,
                    next_review_date, is_due
                ) VALUES (?, 2.5, 1, 0, '2025-01-01', 1)
            """, (note_path,))
            conn.commit()
            conn.close()

            with patch(
                "src.services.srs.srs_algorithm.get_settings",
                return_value=_mock_settings(str(vault_dir)),
            ), patch(
                "src.services.srs.srs_algorithm.DB_PATH", db_path
            ):
                from src.services.srs.srs_algorithm import update_card_rating

                result = update_card_rating(note_path, rating=2)
                assert result["success"] is True


# ---------------------------------------------------------------------------
# SRS Sync - vault path from config
# ---------------------------------------------------------------------------

class TestSRSSyncPaths:
    """srs_sync.py must resolve vault path from config, not hardcoded."""

    def test_no_hardcoded_users_server_in_source(self):
        """Source code must not contain hardcoded /Users/server paths."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "srs"
            / "srs_sync.py"
        )
        content = source_file.read_text()
        assert "/Users/server" not in content, (
            "srs_sync.py still contains hardcoded /Users/server path"
        )

    def test_get_vault_path_returns_config_value(self):
        """get_vault_path() should return the configured vault_path."""
        with patch(
            "src.services.srs.srs_sync.get_settings",
            return_value=_mock_settings("/tmp/test_vault"),
        ):
            from src.services.srs.srs_sync import get_vault_path

            result = get_vault_path()
            assert result == Path("/tmp/test_vault")

    def test_get_vault_path_expands_tilde(self):
        """get_vault_path() should expand ~ in the path."""
        with patch(
            "src.services.srs.srs_sync.get_settings",
            return_value=_mock_settings("~/Research/vault"),
        ):
            from src.services.srs.srs_sync import get_vault_path

            result = get_vault_path()
            assert "~" not in str(result)

    def test_sync_note_to_db_uses_config_vault_path(self):
        """sync_note_to_db should use the config vault path for relative_to."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = Path(tmpdir) / "vault"
            vault_dir.mkdir()
            db_path = Path(tmpdir) / "schedule.db"

            # Create a test note
            ideas_dir = vault_dir / "Ideas"
            ideas_dir.mkdir()
            note_file = ideas_dir / "test_idea.md"
            note_file.write_text(
                "---\nsrs_enabled: true\nsrs_next_review: 2025-01-01\ntype: idea\n---\n# Test Idea\nContent\n"
            )

            # Create DB
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS srs_cards (
                    id INTEGER PRIMARY KEY,
                    note_path TEXT UNIQUE,
                    note_type TEXT DEFAULT 'idea',
                    title TEXT DEFAULT '',
                    srs_enabled INTEGER DEFAULT 1,
                    next_review_date TEXT,
                    last_review_date TEXT,
                    interval_days INTEGER DEFAULT 1,
                    ease_factor REAL DEFAULT 2.5,
                    repetitions INTEGER DEFAULT 0,
                    is_due INTEGER DEFAULT 0,
                    total_reviews INTEGER DEFAULT 0,
                    last_synced TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            with patch(
                "src.services.srs.srs_sync.get_settings",
                return_value=_mock_settings(str(vault_dir)),
            ), patch(
                "src.services.srs.srs_sync.DB_PATH", db_path
            ):
                from src.services.srs.srs_sync import sync_note_to_db

                result = sync_note_to_db(note_file, conn)
                assert result is True

            conn.close()


# ---------------------------------------------------------------------------
# SRS Seed - vault path from config
# ---------------------------------------------------------------------------

class TestSRSSeedPaths:
    """srs_seed.py must resolve vault path from config, not hardcoded."""

    def test_no_hardcoded_users_server_in_source(self):
        """Source code must not contain hardcoded /Users/server paths."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "srs"
            / "srs_seed.py"
        )
        content = source_file.read_text()
        assert "/Users/server" not in content, (
            "srs_seed.py still contains hardcoded /Users/server path"
        )

    def test_get_vault_path_returns_config_value(self):
        """get_vault_path() should return the configured vault_path."""
        with patch(
            "src.services.srs.srs_seed.get_settings",
            return_value=_mock_settings("/tmp/test_vault"),
        ):
            from src.services.srs.srs_seed import get_vault_path

            result = get_vault_path()
            assert result == Path("/tmp/test_vault")

    def test_get_vault_path_expands_tilde(self):
        """get_vault_path() should expand ~ in the path."""
        with patch(
            "src.services.srs.srs_seed.get_settings",
            return_value=_mock_settings("~/Research/vault"),
        ):
            from src.services.srs.srs_seed import get_vault_path

            result = get_vault_path()
            assert "~" not in str(result)

    def test_seed_evergreen_ideas_uses_config_path(self):
        """seed_evergreen_ideas should use the config vault path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = Path(tmpdir) / "vault"
            ideas_dir = vault_dir / "Ideas"
            ideas_dir.mkdir(parents=True)

            with patch(
                "src.services.srs.srs_seed.get_settings",
                return_value=_mock_settings(str(vault_dir)),
            ):
                from src.services.srs.srs_seed import seed_evergreen_ideas

                stats = seed_evergreen_ideas(dry_run=True)
                # Should not raise, even if no ideas found
                assert isinstance(stats, dict)
                assert "total" in stats


# ---------------------------------------------------------------------------
# SRS Scheduler - vault path from config
# ---------------------------------------------------------------------------

class TestSRSSchedulerPaths:
    """srs_scheduler.py must resolve vault path from config, not hardcoded."""

    def test_no_hardcoded_users_server_in_source(self):
        """Source code must not contain hardcoded /Users/server paths."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "srs"
            / "srs_scheduler.py"
        )
        content = source_file.read_text()
        assert "/Users/server" not in content, (
            "srs_scheduler.py still contains hardcoded /Users/server path"
        )

    def test_get_vault_path_returns_config_value(self):
        """get_vault_path() should return the configured vault_path."""
        # srs_scheduler uses a local import of get_settings inside get_vault_path,
        # so we patch at the config module level
        with patch(
            "src.core.config.get_settings",
            return_value=_mock_settings("/tmp/test_vault"),
        ):
            from src.services.srs.srs_scheduler import get_vault_path

            result = get_vault_path()
            assert result == Path("/tmp/test_vault")

    def test_get_vault_path_expands_tilde(self):
        """get_vault_path() should expand ~ in the path."""
        with patch(
            "src.core.config.get_settings",
            return_value=_mock_settings("~/Research/vault"),
        ):
            from src.services.srs.srs_scheduler import get_vault_path

            result = get_vault_path()
            assert "~" not in str(result)


# ---------------------------------------------------------------------------
# SRS Service - vault path from config
# ---------------------------------------------------------------------------

class TestSRSServicePaths:
    """srs_service.py must resolve vault path from config, not hardcoded."""

    def test_no_hardcoded_users_server_in_source(self):
        """Source code must not contain hardcoded /Users/server paths."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "srs_service.py"
        )
        content = source_file.read_text()
        assert "/Users/server" not in content, (
            "srs_service.py still contains hardcoded /Users/server path"
        )

    def test_vault_path_comes_from_config(self):
        """SRSService.vault_path should come from config, not hardcoded."""
        with patch(
            "src.services.srs_service.get_settings",
            return_value=_mock_settings("/tmp/test_vault"),
        ):
            from src.services.srs_service import SRSService

            service = SRSService()
            assert service.vault_path == Path("/tmp/test_vault")

    def test_vault_path_expands_tilde(self):
        """SRSService.vault_path should expand ~ in the path."""
        with patch(
            "src.services.srs_service.get_settings",
            return_value=_mock_settings("~/Research/vault"),
        ):
            from src.services.srs_service import SRSService

            service = SRSService()
            assert "~" not in str(service.vault_path)
            assert service.vault_path == Path.home() / "Research" / "vault"


# ---------------------------------------------------------------------------
# Claude Code Service - binary lookup
# ---------------------------------------------------------------------------

class TestClaudeCodeServicePaths:
    """claude_code_service.py must not hardcode binary paths."""

    def test_no_hardcoded_users_server_binary_in_source(self):
        """Source should not contain hardcoded /Users/server/.local/bin/claude."""
        source_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "services"
            / "claude_code_service.py"
        )
        content = source_file.read_text()
        assert "/Users/server/.local/bin/claude" not in content, (
            "claude_code_service.py still contains hardcoded claude binary path"
        )

    def test_kill_stuck_processes_uses_which_for_detection(self):
        """_kill_stuck_processes should use shutil.which for claude binary path."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        # Mock shutil.which to return a test path
        with patch(
            "src.services.claude_code_service.shutil.which",
            return_value="/usr/local/bin/claude",
        ), patch(
            "subprocess.run"
        ) as mock_run:
            # Mock ps output with no claude processes
            mock_run.return_value = MagicMock(
                stdout="PID ETIME COMMAND\n1234 01:00 /usr/bin/python3\n",
                returncode=0,
            )
            killed = service._kill_stuck_processes()
            assert killed == 0

    def test_kill_stuck_processes_works_when_claude_not_found(self):
        """_kill_stuck_processes should handle claude binary not in PATH."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        with patch(
            "src.services.claude_code_service.shutil.which",
            return_value=None,
        ), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                stdout="PID ETIME COMMAND\n1234 01:00 /usr/bin/python3\n",
                returncode=0,
            )
            # Should not crash when claude binary not found
            killed = service._kill_stuck_processes()
            assert killed == 0
