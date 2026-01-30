"""
Trail Review Service - Manages trail reviews via Telegram polls.

Provides scheduled trail status checks with multi-question polling sequences.
Integrates with vault trail files to update status and schedule next reviews.
"""

import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import frontmatter

logger = logging.getLogger(__name__)


class TrailReviewService:
    """Service for managing trail reviews via Telegram polls."""

    def __init__(self, vault_path: Path = None):
        self.vault_path = vault_path or Path.home() / "Research/vault"
        self.trails_dir = self.vault_path / "Trails"

        # Poll state tracking: {chat_id: {trail_path: poll_state}}
        self._poll_states: Dict[int, Dict[str, Dict]] = {}

    def get_trails_for_review(self) -> List[Dict]:
        """
        Get trails that are due for review.

        Returns list of trails with metadata, sorted by review urgency.
        """
        today = datetime.now().date()
        trails_due = []

        if not self.trails_dir.exists():
            logger.warning(f"Trails directory not found: {self.trails_dir}")
            return []

        for trail_file in self.trails_dir.glob("Trail - *.md"):
            try:
                post = frontmatter.load(trail_file)

                # Skip non-trail files or inactive trails
                if post.get('type') != 'trail':
                    continue

                status = post.get('status', 'active')
                if status not in ['active', 'paused']:
                    continue

                # Check next_review date
                next_review = post.get('next_review')
                if not next_review:
                    # No review scheduled, add with low priority
                    trails_due.append({
                        'path': str(trail_file),
                        'name': trail_file.stem.replace('Trail - ', ''),
                        'status': status,
                        'velocity': post.get('velocity', 'medium'),
                        'direction': post.get('direction', 'unknown'),
                        'urgency': 0,
                        'next_review': None
                    })
                    continue

                # Parse next_review date (format: YYYY-MM-DD)
                if isinstance(next_review, str):
                    try:
                        next_review_date = datetime.strptime(next_review, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(f"Invalid next_review format in {trail_file.name}: {next_review}")
                        continue
                else:
                    next_review_date = next_review

                # Calculate urgency (days overdue, negative if future)
                days_overdue = (today - next_review_date).days

                if days_overdue >= 0:
                    trails_due.append({
                        'path': str(trail_file),
                        'name': trail_file.stem.replace('Trail - ', ''),
                        'status': status,
                        'velocity': post.get('velocity', 'medium'),
                        'direction': post.get('direction', 'unknown'),
                        'urgency': days_overdue,
                        'next_review': next_review_date.isoformat()
                    })

            except Exception as e:
                logger.error(f"Error processing trail {trail_file.name}: {e}")
                continue

        # Sort by urgency (most overdue first)
        trails_due.sort(key=lambda t: t['urgency'], reverse=True)

        return trails_due

    def get_random_active_trail(self) -> Optional[Dict]:
        """Get a random active trail for proactive review."""
        import random

        trails = self.get_trails_for_review()
        if not trails:
            return None

        # Weight by urgency
        if trails[0]['urgency'] > 0:
            # At least one trail is overdue, pick from overdue ones
            overdue = [t for t in trails if t['urgency'] > 0]
            return random.choice(overdue)
        else:
            # All trails current, pick any active one
            active = [t for t in trails if t['status'] == 'active']
            if active:
                return random.choice(active)
            return random.choice(trails)

    def create_velocity_poll(self, trail: Dict) -> Dict:
        """Create velocity assessment poll."""
        return {
            'question': f"🚀 Trail velocity for '{trail['name']}'?",
            'options': [
                '🔥 High (moving fast)',
                '⚡ Medium (steady progress)',
                '🐢 Low (slow/background)',
                '⏸️ Paused'
            ],
            'current_value': trail.get('velocity', 'medium'),
            'field': 'velocity'
        }

    def create_status_poll(self, trail: Dict) -> Dict:
        """Create status check poll."""
        return {
            'question': f"📊 Status for '{trail['name']}'?",
            'options': [
                '✅ Active (working on it)',
                '⏸️ Paused (on hold)',
                '🎯 Completed',
                '❌ Abandoned'
            ],
            'current_value': trail.get('status', 'active'),
            'field': 'status'
        }

    def create_stage_poll(self, trail: Dict, direction: str) -> Dict:
        """Create stage/progress poll based on trail direction."""
        # Parse current stage from direction stages
        # Format: "RESEARCH → SYNTHESIS → INTEGRATION → PROACTIVE"
        #              ✓         ◐            ◐            ○

        if direction == 'building':
            return {
                'question': f"🏗️ Current stage for '{trail['name']}'?",
                'options': [
                    '📋 Planning',
                    '🔨 Building',
                    '🧪 Testing',
                    '🚀 Shipping'
                ],
                'field': 'stage'
            }
        elif direction == 'research':
            return {
                'question': f"🔬 Research stage for '{trail['name']}'?",
                'options': [
                    '🔍 Exploring',
                    '📚 Synthesizing',
                    '🔗 Integrating',
                    '💡 Applying'
                ],
                'field': 'stage'
            }
        else:
            return {
                'question': f"📍 Progress on '{trail['name']}'?",
                'options': [
                    '🌱 Starting',
                    '🌿 Growing',
                    '🌳 Mature',
                    '🍂 Finishing'
                ],
                'field': 'stage'
            }

    def create_next_review_poll(self, trail: Dict) -> Dict:
        """Create next review scheduling poll."""
        return {
            'question': f"📅 When to review '{trail['name']}' again?",
            'options': [
                '🔔 Tomorrow (urgent)',
                '📆 In 1 week',
                '📆 In 2 weeks',
                '📆 In 1 month'
            ],
            'field': 'next_review'
        }

    def get_poll_sequence(self, trail: Dict) -> List[Dict]:
        """Get sequence of polls for a trail review."""
        sequence = [
            self.create_velocity_poll(trail),
            self.create_status_poll(trail),
            self.create_stage_poll(trail, trail.get('direction', 'unknown')),
            self.create_next_review_poll(trail)
        ]
        return sequence

    def start_poll_sequence(self, chat_id: int, trail: Dict) -> Optional[Dict]:
        """
        Start a new poll sequence for a trail.

        Returns the first poll to send, or None if error.
        """
        if chat_id not in self._poll_states:
            self._poll_states[chat_id] = {}

        sequence = self.get_poll_sequence(trail)

        self._poll_states[chat_id][trail['path']] = {
            'trail': trail,
            'sequence': sequence,
            'current_index': 0,
            'answers': {},
            'started_at': datetime.now().isoformat()
        }

        return sequence[0] if sequence else None

    def get_next_poll(self, chat_id: int, trail_path: str, answer: str) -> Tuple[Optional[Dict], bool]:
        """
        Record answer and get next poll in sequence.

        Returns: (next_poll, is_complete)
        """
        if chat_id not in self._poll_states:
            return None, True

        if trail_path not in self._poll_states[chat_id]:
            return None, True

        state = self._poll_states[chat_id][trail_path]
        current_poll = state['sequence'][state['current_index']]

        # Record answer
        state['answers'][current_poll['field']] = answer

        # Move to next poll
        state['current_index'] += 1

        # Check if sequence complete
        if state['current_index'] >= len(state['sequence']):
            return None, True

        return state['sequence'][state['current_index']], False

    def finalize_review(self, chat_id: int, trail_path: str) -> Dict:
        """
        Finalize review and update trail file.

        Returns summary of changes made.
        """
        if chat_id not in self._poll_states:
            return {'success': False, 'error': 'No poll state found'}

        if trail_path not in self._poll_states[chat_id]:
            return {'success': False, 'error': 'Trail not in poll state'}

        state = self._poll_states[chat_id][trail_path]
        answers = state['answers']
        trail = state['trail']

        try:
            # Load trail file
            post = frontmatter.load(trail_path)

            # Update frontmatter based on answers
            changes = []

            # Velocity
            if 'velocity' in answers:
                velocity_map = {
                    '🔥 High (moving fast)': 'high',
                    '⚡ Medium (steady progress)': 'medium',
                    '🐢 Low (slow/background)': 'low',
                    '⏸️ Paused': 'low'
                }
                new_velocity = velocity_map.get(answers['velocity'], 'medium')
                if post.get('velocity') != new_velocity:
                    post['velocity'] = new_velocity
                    changes.append(f"velocity → {new_velocity}")

            # Status
            if 'status' in answers:
                status_map = {
                    '✅ Active (working on it)': 'active',
                    '⏸️ Paused (on hold)': 'paused',
                    '🎯 Completed': 'completed',
                    '❌ Abandoned': 'abandoned'
                }
                new_status = status_map.get(answers['status'], 'active')
                if post.get('status') != new_status:
                    post['status'] = new_status
                    changes.append(f"status → {new_status}")

            # Next review
            if 'next_review' in answers:
                today = datetime.now().date()
                review_map = {
                    '🔔 Tomorrow (urgent)': today + timedelta(days=1),
                    '📆 In 1 week': today + timedelta(weeks=1),
                    '📆 In 2 weeks': today + timedelta(weeks=2),
                    '📆 In 1 month': today + timedelta(days=30)
                }
                next_review = review_map.get(answers['next_review'], today + timedelta(weeks=1))
                post['next_review'] = next_review.isoformat()
                changes.append(f"next_review → {next_review.isoformat()}")

            # Update last_updated
            post['last_updated'] = datetime.now().date().isoformat()
            changes.append(f"last_updated → {post['last_updated']}")

            # Write back to file
            with open(trail_path, 'w') as f:
                f.write(frontmatter.dumps(post))

            # Clean up poll state
            del self._poll_states[chat_id][trail_path]

            return {
                'success': True,
                'trail_name': trail['name'],
                'changes': changes,
                'answers': answers
            }

        except Exception as e:
            logger.error(f"Error finalizing review for {trail_path}: {e}")
            return {'success': False, 'error': str(e)}


# Singleton instance
_trail_review_service: Optional[TrailReviewService] = None


def get_trail_review_service() -> TrailReviewService:
    """Get the global trail review service instance."""
    global _trail_review_service
    if _trail_review_service is None:
        _trail_review_service = TrailReviewService()
    return _trail_review_service
