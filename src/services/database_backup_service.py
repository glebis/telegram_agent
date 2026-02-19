"""
Database backup service.

Provides SQLite backup with gzip compression and rotation of old backups.
Uses sqlite3.backup() which is safe for WAL-mode databases.
"""

import gzip
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def backup(source_db: Path, backup_dir: Path) -> Optional[Path]:
    """Create a gzipped backup of a SQLite database.

    Uses sqlite3.backup() for a consistent snapshot (safe for WAL mode).

    Args:
        source_db: Path to the source SQLite database file.
        backup_dir: Directory to store the backup. Created if missing.

    Returns:
        Path to the created .db.gz file, or None on failure.
    """
    source_db = Path(source_db)
    backup_dir = Path(backup_dir)

    if not source_db.exists():
        logger.error("Backup source not found: %s", source_db)
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"telegram_agent_{timestamp}.db.gz"
    backup_path = backup_dir / backup_name

    # Create an in-memory copy via sqlite3.backup(), then gzip it
    tmp_db_path = backup_dir / f"_tmp_{timestamp}.db"

    try:
        src_conn = sqlite3.connect(str(source_db))
        dst_conn = sqlite3.connect(str(tmp_db_path))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        # Gzip the temporary copy
        with open(tmp_db_path, "rb") as f_in:
            with gzip.open(backup_path, "wb") as f_out:
                while True:
                    chunk = f_in.read(65536)
                    if not chunk:
                        break
                    f_out.write(chunk)

        logger.info("Backup created: %s", backup_path)
        return backup_path

    except Exception:
        logger.exception("Backup failed for %s", source_db)
        return None

    finally:
        # Clean up temp file
        if tmp_db_path.exists():
            tmp_db_path.unlink()


def rotate(backup_dir: Path, keep: int = 7) -> int:
    """Remove old backups, keeping the *keep* most recent .db.gz files.

    Args:
        backup_dir: Directory containing backup files.
        keep: Number of most-recent backups to retain.

    Returns:
        Number of files removed.
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return 0

    backups = sorted(backup_dir.glob("*.db.gz"), key=lambda p: p.stat().st_mtime)

    if len(backups) <= keep:
        return 0

    to_remove = backups[: len(backups) - keep]
    for f in to_remove:
        f.unlink()
        logger.debug("Removed old backup: %s", f)

    removed = len(to_remove)
    logger.info("Rotated backups: removed %d, kept %d", removed, keep)
    return removed


def run_backup(backup_dir: Optional[Path] = None, keep: int = 7) -> Optional[Path]:
    """Convenience function: backup the project database and rotate.

    Reads the DB path from ``get_database_url()``, performs a backup,
    then rotates old backups.

    Args:
        backup_dir: Override backup directory. Defaults to ``data/backups/``.
        keep: Number of backups to retain after rotation.

    Returns:
        Path to the new backup, or None on failure.
    """
    from ..core.database import get_database_url

    db_url = get_database_url()
    # Strip the SQLAlchemy async prefix to get the file path
    # e.g. "sqlite+aiosqlite:///./data/telegram_agent.db" -> "./data/telegram_agent.db"
    if ":///" in db_url:
        db_file = db_url.split(":///", 1)[1]
    elif "://" in db_url:
        db_file = db_url.split("://", 1)[1]
    else:
        db_file = db_url

    source_db = Path(db_file)

    if backup_dir is None:
        backup_dir = source_db.parent / "backups"

    result = backup(source_db, backup_dir)
    if result is not None:
        rotate(backup_dir, keep=keep)

    return result
