#!/usr/bin/env python3
"""
SRS Scheduler Service
Sends scheduled cards to Telegram at configured times
"""

import sqlite3
import re
from datetime import datetime, date, time
from pathlib import Path
from typing import Dict, List, Optional

from src.bot.handlers.formatting import markdown_to_telegram_html

VAULT_PATH = Path("/Users/server/Research/vault")
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "srs" / "schedule.db"

def get_config(key: str) -> Optional[str]:
    """Get config value from database."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(
            'SELECT value FROM srs_config WHERE key = ?',
            (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def set_config(key: str, value: str):
    """Set config value in database."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT INTO srs_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        ''', (key, value))
        conn.commit()
    finally:
        conn.close()

def should_send_morning_batch() -> bool:
    """Check if morning batch should be sent now."""
    batch_time_str = get_config('morning_batch_time') or '09:00'
    last_batch_str = get_config('last_batch_sent')

    # Parse batch time
    batch_hour, batch_min = map(int, batch_time_str.split(':'))
    batch_time = time(batch_hour, batch_min)

    # Check if we're past the batch time
    now = datetime.now()
    if now.time() < batch_time:
        return False

    # Check if batch already sent today
    if last_batch_str:
        last_batch = datetime.fromisoformat(last_batch_str).date()
        if last_batch >= date.today():
            return False

    return True

def get_due_cards(limit: int = 10, note_type: Optional[str] = None) -> List[Dict]:
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

def load_note_content(note_path: str, excerpt_length: int = 1000) -> Dict[str, str]:
    """Load note content and extract excerpt."""
    try:
        filepath = VAULT_PATH / note_path
        content = filepath.read_text(encoding='utf-8')

        # Remove frontmatter
        content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

        # Get first N characters
        excerpt = content[:excerpt_length]
        needs_more = len(content) > excerpt_length

        return {
            'full_content': content,
            'excerpt': excerpt,
            'needs_more': needs_more,
            'filepath': str(filepath)
        }

    except Exception as e:
        return {
            'full_content': '',
            'excerpt': f'[Error loading content: {e}]',
            'needs_more': False,
            'filepath': ''
        }

def get_backlinks(note_path: str, depth: int = 2) -> List[str]:
    """Get backlinks to a note (notes that link to this note)."""
    # This is a simplified version - could be enhanced with proper link parsing
    filepath = VAULT_PATH / note_path
    note_name = filepath.stem

    backlinks = []

    # Search for wikilinks to this note
    for md_file in VAULT_PATH.rglob('*.md'):
        if md_file == filepath:
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            # Look for [[Note Name]] or [[Note Name|Alias]]
            if f'[[{note_name}' in content:
                backlinks.append(str(md_file.relative_to(VAULT_PATH)))
        except:
            pass

    return backlinks[:5]  # Limit to 5 backlinks

def format_card_message(card: Dict) -> Dict[str, str]:
    """Format card data for Telegram message."""
    note_content = load_note_content(card['note_path'])
    backlinks = get_backlinks(card['note_path'])

    # Format message
    emoji = {
        'idea': '💡',
        'trail': '🛤️',
        'moc': '🗺️',
        'other': '📝'
    }.get(card['note_type'], '📝')

    message = f"{emoji} <b>{card['title']}</b>\n\n"

    # Convert markdown content (including wikilinks) to Telegram HTML
    excerpt_html = markdown_to_telegram_html(note_content['excerpt'], include_frontmatter=False)
    message += f"{excerpt_html}\n"

    if note_content['needs_more']:
        message += f"\n<i>...read more in note</i>\n"

    if backlinks:
        message += f"\n🔗 <b>Related:</b>\n"
        for link in backlinks[:3]:
            link_name = Path(link).stem
            # Convert backlinks to wikilinks, then to clickable deeplinks
            wikilink = f"[[{link_name}]]"
            backlink_html = markdown_to_telegram_html(wikilink, include_frontmatter=False)
            message += f"  • {backlink_html}\n"

    message += f"\n📊 Review #{card['total_reviews'] + 1} | "
    message += f"Interval: {card['interval_days']} days"

    return {
        'message': message,
        'note_path': card['note_path'],
        'card_id': card['id'],
        'full_content': note_content['full_content'],
        'backlinks': backlinks
    }

def send_morning_batch():
    """Send morning batch of cards."""
    batch_size = int(get_config('morning_batch_size') or 5)
    cards = get_due_cards(limit=batch_size)

    if not cards:
        print("No cards due for review")
        return []

    formatted_cards = [format_card_message(card) for card in cards]

    # Update last batch sent time
    set_config('last_batch_sent', datetime.now().isoformat())

    return formatted_cards

def get_review_command_cards(limit: int = 5):
    """Get cards for /review command."""
    cards = get_due_cards(limit=limit)
    return [format_card_message(card) for card in cards]

def main():
    """CLI for testing scheduler."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description='SRS Scheduler')
    parser.add_argument('--batch', action='store_true', help='Send morning batch')
    parser.add_argument('--review', type=int, help='Get N cards for review')
    parser.add_argument('--config', nargs=2, metavar=('KEY', 'VALUE'), help='Set config')
    args = parser.parse_args()

    if args.config:
        set_config(args.config[0], args.config[1])
        print(f"✅ Set {args.config[0]} = {args.config[1]}")

    elif args.batch:
        if should_send_morning_batch():
            cards = send_morning_batch()
            print(f"📬 Sending {len(cards)} cards:")
            for card in cards:
                print(f"\n{card['message'][:200]}...")
        else:
            print("⏸️  Not time for morning batch yet")

    elif args.review:
        cards = get_review_command_cards(limit=args.review)
        print(json.dumps(cards, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
