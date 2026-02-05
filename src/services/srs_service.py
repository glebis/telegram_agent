"""
SRS Service
Integrates spaced repetition system with Telegram bot
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.config import get_settings
from .srs.srs_algorithm import update_card_rating, get_due_cards
from .srs.srs_scheduler import (
    send_morning_batch,
    get_review_command_cards,
    get_config,
    set_config,
    load_note_content,
    get_backlinks
)

logger = logging.getLogger(__name__)


class SRSService:
    """Service for managing spaced repetition cards in Telegram."""

    def __init__(self):
        self.vault_path = Path(get_settings().vault_path).expanduser()

    def create_card_keyboard(self, card_id: int, note_path: str) -> InlineKeyboardMarkup:
        """Create inline keyboard for card rating.

        All callback_data must stay under Telegram's 64-byte limit.
        Only card_id is included; note_path is looked up from DB on callback.
        """
        actions = [
            ("🔄 Again", f"srs_again:{card_id}"),
            ("😓 Hard", f"srs_hard:{card_id}"),
            ("✅ Good", f"srs_good:{card_id}"),
            ("⚡ Easy", f"srs_easy:{card_id}"),
        ]

        # Validate all callback data is under Telegram's 64-byte limit
        for label, data in actions:
            if len(data.encode('utf-8')) > 64:
                raise ValueError(f"SRS callback data exceeds 64 bytes: {data}")

        develop_data = f"srs_develop:{card_id}"
        if len(develop_data.encode('utf-8')) > 64:
            raise ValueError(f"SRS callback data exceeds 64 bytes: {develop_data}")

        keyboard = [
            [InlineKeyboardButton(label, callback_data=data) for label, data in actions],
            [InlineKeyboardButton("🔧 Develop", callback_data=develop_data)],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def send_card(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        card: Dict
    ):
        """Send a single card to the user."""
        keyboard = self.create_card_keyboard(card['card_id'], card['note_path'])

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=card['message'],
            parse_mode='HTML',
            reply_markup=keyboard
        )

    async def handle_review_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        limit: int = 5,
        note_type: Optional[str] = None,
        force: bool = False
    ):
        """Handle /review command - send next N due cards.

        Args:
            update: Telegram update
            context: Telegram context
            limit: Maximum number of cards to show
            note_type: Filter by type ('idea', 'trail', 'moc')
            force: If True, show cards even if not due (by lowest interval)
        """
        try:
            cards = get_review_command_cards(
                limit=limit,
                note_type=note_type,
                force=force
            )

            if not cards:
                type_str = f" {note_type}s" if note_type else ""
                if force:
                    await update.message.reply_text(
                        f"📭 No{type_str} cards found in the system.",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        f"✅ No{type_str} cards due for review!\n\n"
                        f"<i>Use /review --force to review anyway</i>",
                        parse_mode='HTML'
                    )
                return

            type_label = f" {note_type}" if note_type else ""
            force_label = " (forced)" if force else ""
            await update.message.reply_text(
                f"📬 Sending {len(cards)}{type_label} cards{force_label}...",
                parse_mode='HTML'
            )

            for card in cards:
                await self.send_card(update, context, card)

        except Exception as e:
            logger.error(f"Error handling review command: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Error loading cards: {str(e)}"
            )

    async def handle_rating_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Dict:
        """Handle rating button callback."""
        from .srs.srs_algorithm import DB_PATH
        import sqlite3

        query = update.callback_query
        await query.answer()

        try:
            parts = query.data.split(':')
            action = parts[0]
            card_id = int(parts[1])

            # Lookup note_path from database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute('SELECT note_path FROM srs_cards WHERE id = ?', (card_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                await query.edit_message_text(f"❌ Card {card_id} not found")
                return {'success': False, 'error': 'Card not found'}

            note_path = row[0]

            # Rating mapping
            rating_map = {
                'srs_again': 0,
                'srs_hard': 1,
                'srs_good': 2,
                'srs_easy': 3,
            }

            # Handle "Develop" button
            if action == 'srs_develop':
                return {
                    'success': True,
                    'action': 'develop',
                    'card_id': card_id,
                    'note_path': note_path
                }

            # Update card with rating
            rating = rating_map.get(action)
            if rating is None:
                await query.edit_message_text(f"❌ Unknown action: {action}")
                return {'success': False, 'error': 'Unknown action'}

            result = update_card_rating(note_path, rating)

            if not result['success']:
                await query.edit_message_text(
                    f"❌ Error: {result.get('error', 'Unknown error')}"
                )
                return result

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

            await query.edit_message_text(response)

            return {
                'success': True,
                'action': 'rated',
                'rating': rating
            }

        except Exception as e:
            logger.error(f"Error handling rating callback: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_develop_context(self, note_path: str) -> Dict:
        """Get context for Agent SDK development session."""
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
            'backlinks': backlinks,
            'vault_path': str(self.vault_path / note_path)
        }

    async def send_morning_batch(
        self,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Send morning batch of cards."""
        try:
            cards = send_morning_batch()

            if not cards:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ No cards due for review today!",
                    parse_mode='HTML'
                )
                return 0

            # Send batch header
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🌅 <b>Morning Review</b>\n\n{len(cards)} cards due today:",
                parse_mode='HTML'
            )

            # Send each card
            for card in cards:
                keyboard = self.create_card_keyboard(card['card_id'], card['note_path'])
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=card['message'],
                    parse_mode='HTML',
                    reply_markup=keyboard
                )

            return len(cards)

        except Exception as e:
            logger.error(f"Error sending morning batch: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error sending morning batch: {str(e)}"
            )
            return 0

    def get_stats(self) -> Dict:
        """Get SRS statistics."""
        from .srs.srs_algorithm import DB_PATH
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.execute('''
                SELECT
                    note_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN is_due = 1 THEN 1 ELSE 0 END) as due_now,
                    AVG(ease_factor) as avg_ease,
                    AVG(interval_days) as avg_interval
                FROM srs_cards
                WHERE srs_enabled = 1
                GROUP BY note_type
            ''')

            stats = {}
            for row in cursor.fetchall():
                stats[row[0]] = {
                    'total': row[1],
                    'due_now': row[2],
                    'avg_ease': round(row[3], 2) if row[3] else 0,
                    'avg_interval': round(row[4], 1) if row[4] else 0
                }

            return stats

        finally:
            conn.close()


# Global instance
srs_service = SRSService()
