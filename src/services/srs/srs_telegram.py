#!/usr/bin/env python3
"""
SRS Telegram Bot Integration
Handlers for sending cards and processing ratings
"""

from typing import Dict, List, Optional
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from srs_algorithm import update_card_rating
from srs_scheduler import (
    send_morning_batch,
    get_review_command_cards,
    get_config,
    set_config
)

# Rating button callbacks
RATING_CALLBACKS = {
    'srs_again': 0,    # Restart interval
    'srs_hard': 1,     # Slightly increase
    'srs_good': 2,     # Normal increase
    'srs_easy': 3,     # Large increase
    'srs_develop': -1  # Open Agent SDK session
}

def create_card_keyboard(card_id: int, note_path: str) -> List[List[Dict]]:
    """
    Create inline keyboard for card rating.

    Only card_id is included in callback_data to stay under Telegram's
    64-byte limit. The note_path is looked up from the database on callback.

    Returns Telegram inline keyboard markup structure.
    """
    actions = [
        ('🔄 Again', f'srs_again:{card_id}'),
        ('😓 Hard', f'srs_hard:{card_id}'),
        ('✅ Good', f'srs_good:{card_id}'),
        ('⚡ Easy', f'srs_easy:{card_id}'),
    ]

    # Validate all callback data is under Telegram's 64-byte limit
    for label, data in actions:
        if len(data.encode('utf-8')) > 64:
            raise ValueError(f"SRS callback data exceeds 64 bytes: {data}")

    develop_data = f'srs_develop:{card_id}'
    if len(develop_data.encode('utf-8')) > 64:
        raise ValueError(f"SRS callback data exceeds 64 bytes: {develop_data}")

    return [
        [{'text': label, 'callback_data': data} for label, data in actions],
        [{'text': '🔧 Develop', 'callback_data': develop_data}],
    ]

def handle_rating_callback(callback_data: str) -> Dict:
    """
    Process rating button callback.

    Args:
        callback_data: Format "srs_{rating}:{card_id}"
            note_path is looked up from the database using card_id.

    Returns:
        Dict with success status and response message
    """
    import sqlite3
    from srs_algorithm import DB_PATH

    try:
        parts = callback_data.split(':')
        action = parts[0]
        card_id = int(parts[1])

        if action not in RATING_CALLBACKS:
            return {
                'success': False,
                'error': f'Unknown action: {action}'
            }

        # Lookup note_path from database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            'SELECT note_path FROM srs_cards WHERE id = ?', (card_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                'success': False,
                'error': f'Card {card_id} not found'
            }

        note_path = row[0]
        rating = RATING_CALLBACKS[action]

        # Handle "Develop" button separately
        if rating == -1:
            return {
                'success': True,
                'action': 'develop',
                'card_id': card_id,
                'note_path': note_path,
                'message': '🔧 Opening development session...'
            }

        # Update card with rating
        result = update_card_rating(note_path, rating)

        if not result['success']:
            return {
                'success': False,
                'error': result.get('error', 'Unknown error')
            }

        # Format response message
        rating_names = {
            0: '🔄 Again',
            1: '😓 Hard',
            2: '✅ Good',
            3: '⚡ Easy'
        }

        response = f"{rating_names[rating]}\n\n"
        response += f"Next review: {result['next_review']}\n"
        response += f"Interval: {result['interval']} days\n"
        response += f"Ease: {result['ease_factor']}"

        return {
            'success': True,
            'action': 'rated',
            'rating': rating,
            'message': response
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def send_card_to_telegram(
    bot_send_message,
    chat_id: str,
    card: Dict
):
    """
    Send a card to Telegram with rating buttons.

    Args:
        bot_send_message: Telegram bot send_message function
        chat_id: Telegram chat ID
        card: Formatted card dict from scheduler
    """
    keyboard = create_card_keyboard(card['card_id'], card['note_path'])

    bot_send_message(
        chat_id=chat_id,
        text=card['message'],
        parse_mode='HTML',
        reply_markup={
            'inline_keyboard': keyboard
        }
    )

def send_morning_batch_to_telegram(bot_send_message, chat_id: str):
    """Send morning batch of cards to Telegram."""
    cards = send_morning_batch()

    if not cards:
        bot_send_message(
            chat_id=chat_id,
            text="✅ No cards due for review today!",
            parse_mode='HTML'
        )
        return 0

    # Send batch header
    bot_send_message(
        chat_id=chat_id,
        text=f"🌅 <b>Morning Review</b>\n\n{len(cards)} cards due today:",
        parse_mode='HTML'
    )

    # Send each card
    for card in cards:
        send_card_to_telegram(bot_send_message, chat_id, card)

    return len(cards)

def handle_review_command(
    bot_send_message,
    chat_id: str,
    limit: int = 5
):
    """Handle /review command - send next N due cards."""
    cards = get_review_command_cards(limit=limit)

    if not cards:
        bot_send_message(
            chat_id=chat_id,
            text="✅ No cards due for review!",
            parse_mode='HTML'
        )
        return 0

    for card in cards:
        send_card_to_telegram(bot_send_message, chat_id, card)

    return len(cards)

def get_develop_context(note_path: str) -> Dict:
    """
    Get context for Agent SDK development session.

    Returns dict with note content and context for Claude.
    """
    from srs_scheduler import load_note_content, get_backlinks

    content_data = load_note_content(note_path, excerpt_length=5000)
    backlinks = get_backlinks(note_path, depth=2)

    context = f"""You're helping the user develop this idea from their vault:

# {Path(note_path).stem}

{content_data['full_content']}

## Related Notes (Backlinks)
{chr(10).join('- [[' + Path(link).stem + ']]' for link in backlinks[:5])}

The user may ask you to:
- Edit or expand this note
- Create related notes
- Explore connections to other ideas
- Add examples or applications
- Link to relevant concepts in their vault

Be concise and actionable. Preserve their voice and thinking style.
"""

    return {
        'note_path': note_path,
        'note_content': content_data['full_content'],
        'context_prompt': context,
        'backlinks': backlinks
    }

# Example integration for your Telegram bot
"""
# In your main bot file:

from srs_telegram import (
    send_morning_batch_to_telegram,
    handle_review_command,
    handle_rating_callback,
    get_develop_context
)

# Handle /review command
@bot.message_handler(commands=['review'])
def review_command(message):
    handle_review_command(bot.send_message, message.chat.id, limit=5)

# Handle rating button callbacks
@bot.callback_query_handler(func=lambda call: call.data.startswith('srs_'))
def rating_callback(call):
    result = handle_rating_callback(call.data)

    if result['action'] == 'develop':
        # Launch Agent SDK session with context
        context = get_develop_context(result['note_path'])
        # Start multi-turn conversation with context
        start_agent_session(call.message.chat.id, context['context_prompt'])
    else:
        # Show rating result
        bot.answer_callback_query(call.id, result['message'])

# Schedule morning batch (cron or scheduler)
def send_daily_batch():
    chat_id = get_config('telegram_chat_id')
    send_morning_batch_to_telegram(bot.send_message, chat_id)
"""

def main():
    """Test function."""
    import argparse

    parser = argparse.ArgumentParser(description='Test SRS Telegram integration')
    parser.add_argument('--test-callback', help='Test callback handler')
    args = parser.parse_args()

    if args.test_callback:
        result = handle_rating_callback(args.test_callback)
        print(result)

if __name__ == '__main__':
    main()
