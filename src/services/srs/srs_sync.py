#!/usr/bin/env python3
"""
SRS Vault Sync Script
Syncs vault note frontmatter with SRS scheduling database
"""

import os
import sqlite3
import yaml
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional, List

VAULT_PATH = Path("/Users/server/Research/vault")
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "srs" / "schedule.db"

def parse_frontmatter(content: str) -> Optional[Dict]:
    """Extract YAML frontmatter from markdown content."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None

    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

def extract_title(content: str, filepath: Path) -> str:
    """Extract title from first H1 or filename."""
    # Remove frontmatter
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

    # Look for first H1
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Fallback to filename
    return filepath.stem

def determine_note_type(filepath: Path, frontmatter: Dict) -> str:
    """Determine note type from path and frontmatter."""
    path_str = str(filepath)

    if 'Ideas/∞→' in path_str:
        return 'idea'
    elif 'Trails/' in path_str:
        return 'trail'
    elif filepath.name.startswith('MoC -'):
        return 'moc'

    # Check frontmatter type field
    fm_type = frontmatter.get('type', '').lower()
    if fm_type in ['idea', 'trail', 'moc']:
        return fm_type

    return 'other'

def parse_date(date_str) -> Optional[date]:
    """Parse date from various formats."""
    if not date_str:
        return None

    # Handle wikilink format [[YYYYMMDD]]
    if isinstance(date_str, str):
        date_str = re.sub(r'\[\[|\]\]', '', date_str)

    # Try parsing
    for fmt in ['%Y-%m-%d', '%Y%m%d', '%Y-%m-%dT%H:%M:%S']:
        try:
            return datetime.strptime(str(date_str), fmt).date()
        except ValueError:
            continue

    return None

def should_enable_srs(note_type: str, frontmatter: Dict) -> bool:
    """Determine if SRS should be enabled for this note."""
    # Explicit flag takes precedence
    if 'srs_enabled' in frontmatter:
        return bool(frontmatter['srs_enabled'])

    # Auto-enable for evergreen ideas
    if note_type == 'idea':
        return True

    # Trails and MoCs: enable if they have a next_review date (either format)
    if note_type in ['trail', 'moc']:
        return 'srs_next_review' in frontmatter or 'next_review' in frontmatter

    return False

def sync_note_to_db(filepath: Path, conn: sqlite3.Connection) -> bool:
    """Sync a single note to the database."""
    try:
        content = filepath.read_text(encoding='utf-8')
        frontmatter = parse_frontmatter(content)

        if not frontmatter:
            return False

        note_type = determine_note_type(filepath, frontmatter)

        # Skip if SRS not enabled for this note
        if not should_enable_srs(note_type, frontmatter):
            return False

        title = extract_title(content, filepath)
        relative_path = str(filepath.relative_to(VAULT_PATH))

        # Extract SRS metadata
        next_review = parse_date(
            frontmatter.get('srs_next_review') or frontmatter.get('next_review')
        )

        if not next_review:
            # Skip notes without review dates
            return False

        last_review = parse_date(
            frontmatter.get('srs_last_review') or frontmatter.get('last_review')
        )

        interval = int(frontmatter.get('srs_interval', 1))
        ease_factor = float(frontmatter.get('srs_ease_factor', 2.5))
        repetitions = int(frontmatter.get('srs_repetitions', 0))

        # Check if card is due
        is_due = next_review <= date.today()

        # Upsert to database
        conn.execute('''
            INSERT INTO srs_cards (
                note_path, note_type, title,
                srs_enabled, next_review_date, last_review_date,
                interval_days, ease_factor, repetitions,
                is_due, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(note_path) DO UPDATE SET
                note_type = excluded.note_type,
                title = excluded.title,
                srs_enabled = excluded.srs_enabled,
                next_review_date = excluded.next_review_date,
                last_review_date = excluded.last_review_date,
                interval_days = excluded.interval_days,
                ease_factor = excluded.ease_factor,
                repetitions = excluded.repetitions,
                is_due = excluded.is_due,
                last_synced = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            relative_path, note_type, title,
            True, next_review, last_review,
            interval, ease_factor, repetitions,
            is_due
        ))

        return True

    except Exception as e:
        print(f"Error syncing {filepath}: {e}")
        return False

def sync_vault(verbose: bool = False) -> Dict[str, int]:
    """Sync all eligible vault notes to database."""
    stats = {
        'scanned': 0,
        'synced': 0,
        'skipped': 0,
        'errors': 0
    }

    conn = sqlite3.connect(DB_PATH)

    try:
        # Find all markdown files
        for md_file in VAULT_PATH.rglob('*.md'):
            stats['scanned'] += 1

            if sync_note_to_db(md_file, conn):
                stats['synced'] += 1
                if verbose:
                    print(f"✓ {md_file.relative_to(VAULT_PATH)}")
            else:
                stats['skipped'] += 1

        conn.commit()

    finally:
        conn.close()

    return stats

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Sync vault notes to SRS database')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("🔄 Syncing vault to SRS database...")
    stats = sync_vault(verbose=args.verbose)

    print(f"\n📊 Stats:")
    print(f"  Scanned: {stats['scanned']}")
    print(f"  Synced:  {stats['synced']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors:  {stats['errors']}")

if __name__ == '__main__':
    main()
