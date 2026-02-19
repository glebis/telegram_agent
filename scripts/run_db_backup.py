#!/usr/bin/env python3
"""CLI entry point for database backup.

Usage:
    python scripts/run_db_backup.py [--backup-dir DIR] [--keep N]

Intended to be called from launchd or cron.
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.services.database_backup_service import run_backup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup the bot SQLite database")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Override backup directory (default: data/backups/)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of backups to retain (default: 7)",
    )
    args = parser.parse_args()

    result = run_backup(backup_dir=args.backup_dir, keep=args.keep)
    if result is None:
        print("Backup failed", file=sys.stderr)
        sys.exit(1)
    print(f"Backup created: {result}")


if __name__ == "__main__":
    main()
