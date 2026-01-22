#!/usr/bin/env python3
"""
SRS Initial Seeding Script
Adds SRS metadata to existing evergreen ideas with random distribution
"""

import os
import random
import re
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

VAULT_PATH = Path("/Users/server/Research/vault")

def parse_frontmatter(content: str) -> tuple[Optional[Dict], str]:
    """Extract YAML frontmatter and return (frontmatter, body)."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if not match:
        return None, content

    try:
        fm = yaml.safe_load(match.group(1))
        body = match.group(2)
        return fm, body
    except yaml.YAMLError:
        return None, content

def has_srs_metadata(frontmatter: Optional[Dict]) -> bool:
    """Check if note already has SRS metadata."""
    if not frontmatter:
        return False

    return any(key in frontmatter for key in [
        'srs_enabled', 'srs_next_review', 'srs_interval'
    ])

def generate_srs_metadata() -> Dict:
    """Generate initial SRS metadata with random interval."""
    # Random initial interval: 1-30 days
    initial_interval = random.randint(1, 30)
    next_review = datetime.now() + timedelta(days=initial_interval)

    return {
        'srs_enabled': True,
        'srs_next_review': next_review.strftime('%Y-%m-%d'),
        'srs_last_review': None,
        'srs_interval': initial_interval,
        'srs_ease_factor': 2.5,
        'srs_repetitions': 0
    }

def add_srs_to_note(filepath: Path, dry_run: bool = False) -> bool:
    """Add SRS metadata to a note file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        frontmatter, body = parse_frontmatter(content)

        if not frontmatter:
            print(f"⚠️  No frontmatter: {filepath.name}")
            return False

        if has_srs_metadata(frontmatter):
            print(f"⏭️  Already has SRS: {filepath.name}")
            return False

        # Add SRS metadata
        srs_meta = generate_srs_metadata()
        frontmatter.update(srs_meta)

        # Reconstruct file
        new_content = f"---\n{yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)}---\n{body}"

        if dry_run:
            print(f"🔍 Would seed: {filepath.name} (next: {srs_meta['srs_next_review']})")
            return True

        filepath.write_text(new_content, encoding='utf-8')
        print(f"✅ Seeded: {filepath.name} (next: {srs_meta['srs_next_review']})")
        return True

    except Exception as e:
        print(f"❌ Error: {filepath.name} - {e}")
        return False

def seed_evergreen_ideas(dry_run: bool = False) -> Dict[str, int]:
    """Seed all evergreen ideas with SRS metadata."""
    stats = {
        'total': 0,
        'seeded': 0,
        'skipped': 0,
        'errors': 0
    }

    ideas_path = VAULT_PATH / "Ideas"
    if not ideas_path.exists():
        print(f"❌ Ideas folder not found: {ideas_path}")
        return stats

    # Find all evergreen ideas (∞→ prefix)
    for idea_file in ideas_path.glob("∞→*.md"):
        stats['total'] += 1

        if add_srs_to_note(idea_file, dry_run=dry_run):
            stats['seeded'] += 1
        else:
            stats['skipped'] += 1

    return stats

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Seed SRS metadata to evergreen ideas'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without writing files'
    )
    args = parser.parse_args()

    print("🌱 Seeding SRS metadata to evergreen ideas...\n")

    if args.dry_run:
        print("🔍 DRY RUN - No files will be modified\n")

    stats = seed_evergreen_ideas(dry_run=args.dry_run)

    print(f"\n📊 Stats:")
    print(f"  Total:   {stats['total']}")
    print(f"  Seeded:  {stats['seeded']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors:  {stats['errors']}")

if __name__ == '__main__':
    main()
