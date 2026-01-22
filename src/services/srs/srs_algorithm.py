#!/usr/bin/env python3
"""
SRS SM-2 Algorithm Implementation
Calculates next review intervals based on user ratings
"""

import sqlite3
import re
import yaml
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional

VAULT_PATH = Path("/Users/server/Research/vault")
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "srs" / "schedule.db"

def calculate_next_review(
    rating: int,
    ease_factor: float,
    interval: int,
    repetitions: int
) -> Tuple[int, float, int]:
    """
    Calculate next review using SM-2 algorithm.

    Args:
        rating: 0=Again, 1=Hard, 2=Good, 3=Easy
        ease_factor: Current ease factor (min 1.3)
        interval: Current interval in days
        repetitions: Number of successful repetitions

    Returns:
        (new_interval, new_ease_factor, new_repetitions)
    """
    # Again: Reset to beginning
    if rating == 0:
        return 1, ease_factor, 0

    # Calculate new interval
    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 3
    else:
        new_interval = int(interval * ease_factor)

    # Adjust ease factor based on rating
    # Formula: EF' = EF + (0.1 - (3-q) * (0.08 + (3-q) * 0.02))
    ease_adjustment = 0.1 - (3 - rating) * (0.08 + (3 - rating) * 0.02)
    new_ease_factor = max(1.3, ease_factor + ease_adjustment)

    # Increment repetitions
    new_repetitions = repetitions + 1

    return new_interval, new_ease_factor, new_repetitions

def update_card_rating(
    note_path: str,
    rating: int
) -> Dict[str, any]:
    """
    Update card in database and vault frontmatter based on rating.

    Args:
        note_path: Relative path to note in vault
        rating: User rating (0-3)

    Returns:
        Dict with update results
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Get current card data
        cursor = conn.execute(
            'SELECT * FROM srs_cards WHERE note_path = ?',
            (note_path,)
        )
        card = cursor.fetchone()

        if not card:
            return {'success': False, 'error': 'Card not found'}

        # Calculate new values
        new_interval, new_ease, new_reps = calculate_next_review(
            rating,
            card['ease_factor'],
            card['interval_days'],
            card['repetitions']
        )

        # Calculate next review date
        next_review = date.today() + timedelta(days=new_interval)

        # Record review in history
        conn.execute('''
            INSERT INTO review_history (
                card_id, rating,
                interval_before, interval_after,
                ease_factor_before, ease_factor_after
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            card['id'], rating,
            card['interval_days'], new_interval,
            card['ease_factor'], new_ease
        ))

        # Update card in database
        conn.execute('''
            UPDATE srs_cards SET
                next_review_date = ?,
                last_review_date = ?,
                interval_days = ?,
                ease_factor = ?,
                repetitions = ?,
                is_due = 0,
                total_reviews = total_reviews + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE note_path = ?
        ''', (
            next_review,
            date.today(),
            new_interval,
            new_ease,
            new_reps,
            note_path
        ))

        conn.commit()

        # Update vault frontmatter
        vault_path = VAULT_PATH / note_path
        update_vault_frontmatter(
            vault_path,
            next_review,
            date.today(),
            new_interval,
            new_ease,
            new_reps
        )

        return {
            'success': True,
            'next_review': next_review.isoformat(),
            'interval': new_interval,
            'ease_factor': round(new_ease, 2)
        }

    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}

    finally:
        conn.close()

def update_vault_frontmatter(
    filepath: Path,
    next_review: date,
    last_review: date,
    interval: int,
    ease_factor: float,
    repetitions: int
):
    """Update SRS metadata in vault note frontmatter."""
    try:
        content = filepath.read_text(encoding='utf-8')

        # Parse frontmatter
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
        if not match:
            return

        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)

        # Update SRS fields
        frontmatter['srs_next_review'] = next_review.isoformat()
        frontmatter['srs_last_review'] = last_review.isoformat()
        frontmatter['srs_interval'] = interval
        frontmatter['srs_ease_factor'] = round(ease_factor, 2)
        frontmatter['srs_repetitions'] = repetitions

        # Write back
        new_content = f"---\n{yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)}---\n{body}"
        filepath.write_text(new_content, encoding='utf-8')

    except Exception as e:
        print(f"Error updating frontmatter: {e}")

def get_due_cards(limit: int = 10, note_type: Optional[str] = None) -> list:
    """Get cards due for review."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        query = '''
            SELECT * FROM srs_cards
            WHERE srs_enabled = 1
              AND next_review_date <= date('now')
        '''
        params = []

        if note_type:
            query += ' AND note_type = ?'
            params.append(note_type)

        query += ' ORDER BY next_review_date ASC LIMIT ?'
        params.append(limit)

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    finally:
        conn.close()

def main():
    """Test function."""
    import argparse

    parser = argparse.ArgumentParser(description='Test SRS algorithm')
    parser.add_argument('--due', action='store_true', help='Show due cards')
    parser.add_argument('--limit', type=int, default=10, help='Limit results')
    args = parser.parse_args()

    if args.due:
        cards = get_due_cards(limit=args.limit)
        print(f"📋 {len(cards)} cards due for review:\n")
        for card in cards:
            print(f"  • {card['title']}")
            print(f"    Path: {card['note_path']}")
            print(f"    Due: {card['next_review_date']}")
            print(f"    Interval: {card['interval_days']} days")
            print()

if __name__ == '__main__':
    main()
