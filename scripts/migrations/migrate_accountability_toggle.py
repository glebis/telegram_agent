"""
Migration: Add accountability_enabled column to chats table.

Usage:
    python scripts/migrate_accountability_toggle.py
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "telegram_agent.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(chats)")
    columns = [row[1] for row in cursor.fetchall()]

    if "accountability_enabled" in columns:
        print("Column 'accountability_enabled' already exists. Nothing to do.")
        conn.close()
        return

    cursor.execute(
        "ALTER TABLE chats ADD COLUMN accountability_enabled BOOLEAN NOT NULL DEFAULT 0"
    )
    conn.commit()
    print("Added 'accountability_enabled' column to chats table (default: FALSE).")
    conn.close()


if __name__ == "__main__":
    migrate()
