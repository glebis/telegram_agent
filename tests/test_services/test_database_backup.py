"""
Tests for database_backup_service.py — backup, rotation, and run_backup.
"""

import gzip
import sqlite3
import time
from pathlib import Path

import pytest

from src.services.database_backup_service import backup, rotate, run_backup

# =============================================================================
# Helpers
# =============================================================================


def _create_test_db(db_path: Path) -> None:
    """Create a minimal SQLite database with one table and row."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test (value) VALUES ('hello')")
    conn.commit()
    conn.close()


# =============================================================================
# TestDatabaseBackupService
# =============================================================================


class TestDatabaseBackupService:
    """Tests for the backup() function."""

    def test_backup_creates_gzipped_file(self, tmp_path):
        """backup() produces a .db.gz file in the target directory."""
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _create_test_db(db_path)

        result = backup(db_path, backup_dir)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".gz"
        assert result.name.endswith(".db.gz")

    def test_backup_is_valid_sqlite(self, tmp_path):
        """Decompressed backup is a valid SQLite database."""
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _create_test_db(db_path)

        result = backup(db_path, backup_dir)
        assert result is not None

        # Decompress and verify it's valid SQLite
        decompressed = tmp_path / "restored.db"
        with gzip.open(result, "rb") as f_in:
            decompressed.write_bytes(f_in.read())

        conn = sqlite3.connect(str(decompressed))
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
        conn.close()

    def test_backup_preserves_data(self, tmp_path):
        """Backup preserves inserted data."""
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _create_test_db(db_path)

        result = backup(db_path, backup_dir)
        assert result is not None

        # Decompress and query
        decompressed = tmp_path / "restored.db"
        with gzip.open(result, "rb") as f_in:
            decompressed.write_bytes(f_in.read())

        conn = sqlite3.connect(str(decompressed))
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        assert cursor.fetchone() == ("hello",)
        conn.close()

    def test_backup_filename_contains_timestamp(self, tmp_path):
        """Backup filename matches telegram_agent_YYYYMMDD_HHMMSS.db.gz."""
        import re

        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _create_test_db(db_path)

        result = backup(db_path, backup_dir)
        assert result is not None

        pattern = r"^telegram_agent_\d{8}_\d{6}\.db\.gz$"
        assert re.match(pattern, result.name), f"Filename {result.name!r} doesn't match"

    def test_backup_creates_dir_if_missing(self, tmp_path):
        """backup() auto-creates backup_dir if it doesn't exist."""
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "deeply" / "nested" / "backups"
        _create_test_db(db_path)

        assert not backup_dir.exists()
        result = backup(db_path, backup_dir)

        assert result is not None
        assert backup_dir.exists()

    def test_backup_returns_path_on_success(self, tmp_path):
        """backup() returns the Path to the created .db.gz file."""
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        _create_test_db(db_path)

        result = backup(db_path, backup_dir)

        assert isinstance(result, Path)
        assert result.parent == backup_dir

    def test_backup_returns_none_when_source_missing(self, tmp_path):
        """backup() returns None when the source DB doesn't exist."""
        db_path = tmp_path / "nonexistent.db"
        backup_dir = tmp_path / "backups"

        result = backup(db_path, backup_dir)

        assert result is None


# =============================================================================
# TestBackupRotation
# =============================================================================


class TestBackupRotation:
    """Tests for the rotate() function."""

    def test_rotate_keeps_n_most_recent(self, tmp_path):
        """5 files, keep=3 → 3 newest survive."""
        files = []
        for i in range(5):
            f = tmp_path / f"telegram_agent_2025010{i}_120000.db.gz"
            f.write_bytes(b"fake")
            # Ensure distinct mtimes
            t = time.time() - (4 - i)
            import os

            os.utime(f, (t, t))
            files.append(f)

        removed = rotate(tmp_path, keep=3)

        assert removed == 2
        remaining = sorted(tmp_path.glob("*.db.gz"))
        assert len(remaining) == 3
        # The 3 newest (highest mtime) should survive
        assert files[2] in remaining
        assert files[3] in remaining
        assert files[4] in remaining

    def test_rotate_does_nothing_under_limit(self, tmp_path):
        """2 files, keep=5 → all survive."""
        for i in range(2):
            f = tmp_path / f"telegram_agent_2025010{i}_120000.db.gz"
            f.write_bytes(b"fake")

        removed = rotate(tmp_path, keep=5)

        assert removed == 0
        assert len(list(tmp_path.glob("*.db.gz"))) == 2

    def test_rotate_ignores_non_backup_files(self, tmp_path):
        """Non-.db.gz files are untouched."""
        # Create 3 backup files and 2 non-backup files
        for i in range(3):
            f = tmp_path / f"telegram_agent_2025010{i}_120000.db.gz"
            f.write_bytes(b"fake")
        txt = tmp_path / "notes.txt"
        txt.write_text("important")
        log = tmp_path / "backup.log"
        log.write_text("log data")

        rotate(tmp_path, keep=1)

        # Non-backup files should still exist
        assert txt.exists()
        assert log.exists()
        # Only 1 backup file should remain
        assert len(list(tmp_path.glob("*.db.gz"))) == 1


# =============================================================================
# TestRunBackup
# =============================================================================


class TestRunBackup:
    """Tests for the run_backup() convenience function."""

    def test_run_backup_uses_database_url(self, tmp_path, monkeypatch):
        """run_backup() reads DB path from get_database_url()."""
        db_path = tmp_path / "data" / "telegram_agent.db"
        db_path.parent.mkdir(parents=True)
        _create_test_db(db_path)

        backup_dir = tmp_path / "backups"

        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

        result = run_backup(backup_dir=backup_dir, keep=3)

        assert result is not None
        assert result.exists()
        assert len(list(backup_dir.glob("*.db.gz"))) == 1
