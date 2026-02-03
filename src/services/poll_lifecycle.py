"""
Poll Lifecycle Tracker - Tracks sent polls, expiration, and backpressure.

Solves:
- Poll pileup (backpressure stops sending when user ignores polls)
- No expiration (auto-deletes stale polls after TTL)
- No sent-time tracking (records actual send time, not just answer time)

State persisted to data/poll_lifecycle_state.json for restart survival.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "poll_lifecycle_state.json"

# Defaults (overridable from poll_templates.yaml scheduling section)
DEFAULT_POLL_TTL_MINUTES = 45
DEFAULT_MAX_UNANSWERED = 2
DEFAULT_BACKPRESSURE_THRESHOLD = 2  # consecutive misses before stopping


class PollLifecycleTracker:
    """Tracks sent-but-unanswered polls for expiration and backpressure."""

    def __init__(
        self,
        ttl_minutes: int = DEFAULT_POLL_TTL_MINUTES,
        max_unanswered: int = DEFAULT_MAX_UNANSWERED,
        backpressure_threshold: int = DEFAULT_BACKPRESSURE_THRESHOLD,
    ):
        self.ttl_minutes = ttl_minutes
        self.max_unanswered = max_unanswered
        self.backpressure_threshold = backpressure_threshold

        # {poll_id: {chat_id, message_id, template_id, sent_at, expires_at, question}}
        self._sent_polls: Dict[str, Dict] = {}

        # {chat_id_str: {consecutive_misses, last_sent_at, last_answered_at, backpressure_active}}
        self._chat_state: Dict[str, Dict] = {}

        self._load_state()

    # -- State persistence (mirrors TrailReviewService pattern) --

    def _load_state(self) -> None:
        """Load state from disk."""
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text())
                self._sent_polls = data.get("sent_polls", {})
                self._chat_state = data.get("chat_state", {})
                logger.info(
                    f"Loaded poll lifecycle state: {len(self._sent_polls)} sent polls, "
                    f"{len(self._chat_state)} chat states"
                )
        except Exception as e:
            logger.error(f"Error loading poll lifecycle state: {e}")
            self._sent_polls = {}
            self._chat_state = {}

    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "sent_polls": self._sent_polls,
                "chat_state": self._chat_state,
                "saved_at": datetime.utcnow().isoformat(),
            }
            _STATE_FILE.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving poll lifecycle state: {e}")

    # -- Core operations --

    def record_sent(
        self, poll_id: str, chat_id: int, message_id: int, template_id: str, question: str
    ) -> None:
        """Record that a poll was sent. Call this right after context.bot.send_poll()."""
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.ttl_minutes)
        chat_key = str(chat_id)

        self._sent_polls[poll_id] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "template_id": template_id,
            "sent_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "question": question,
        }

        # Update chat state: record last_sent_at
        if chat_key not in self._chat_state:
            self._chat_state[chat_key] = {
                "consecutive_misses": 0,
                "last_sent_at": None,
                "last_answered_at": None,
                "backpressure_active": False,
            }
        self._chat_state[chat_key]["last_sent_at"] = now.isoformat()

        self._save_state()
        logger.info(
            f"Recorded sent poll {poll_id} for chat {chat_id}, "
            f"expires at {expires_at.isoformat()}"
        )

    def record_answered(self, poll_id: str) -> None:
        """Record that a poll was answered. Resets backpressure."""
        poll_info = self._sent_polls.pop(poll_id, None)
        if not poll_info:
            logger.debug(f"Poll {poll_id} not in lifecycle tracker (already expired or unknown)")
            return

        chat_key = str(poll_info["chat_id"])
        now = datetime.utcnow()

        if chat_key in self._chat_state:
            state = self._chat_state[chat_key]
            state["consecutive_misses"] = 0
            state["last_answered_at"] = now.isoformat()
            state["backpressure_active"] = False
            logger.info(f"Poll {poll_id} answered, backpressure reset for chat {chat_key}")

        self._save_state()

    def record_expired(self, poll_id: str) -> Optional[Dict]:
        """
        Record that a poll expired (TTL passed without answer).
        Increments consecutive_misses. Returns poll info for cleanup, or None.
        """
        poll_info = self._sent_polls.pop(poll_id, None)
        if not poll_info:
            return None

        chat_key = str(poll_info["chat_id"])

        if chat_key not in self._chat_state:
            self._chat_state[chat_key] = {
                "consecutive_misses": 0,
                "last_sent_at": None,
                "last_answered_at": None,
                "backpressure_active": False,
            }

        state = self._chat_state[chat_key]
        state["consecutive_misses"] = state.get("consecutive_misses", 0) + 1

        if state["consecutive_misses"] >= self.backpressure_threshold:
            state["backpressure_active"] = True
            logger.warning(
                f"Backpressure activated for chat {chat_key}: "
                f"{state['consecutive_misses']} consecutive misses"
            )

        self._save_state()
        return poll_info

    def should_send(self, chat_id: int) -> Tuple[bool, str]:
        """
        Check if we should send a new poll to this chat.
        Returns (allowed, reason).
        """
        chat_key = str(chat_id)
        state = self._chat_state.get(chat_key, {})

        # Check backpressure
        if state.get("backpressure_active", False):
            return False, (
                f"backpressure active ({state.get('consecutive_misses', 0)} "
                f"consecutive misses)"
            )

        # Check unanswered count
        unanswered = self.get_unanswered_count(chat_id)
        if unanswered >= self.max_unanswered:
            return False, f"too many unanswered polls ({unanswered}/{self.max_unanswered})"

        return True, "ok"

    def get_unanswered_count(self, chat_id: int) -> int:
        """Count currently unanswered (sent but not expired/answered) polls for a chat."""
        count = 0
        for poll_info in self._sent_polls.values():
            if poll_info["chat_id"] == chat_id:
                count += 1
        return count

    def get_last_sent_time(self, chat_id: int) -> Optional[datetime]:
        """Get the actual last-sent time (not last-answered time)."""
        chat_key = str(chat_id)
        state = self._chat_state.get(chat_key, {})
        last = state.get("last_sent_at")
        if last:
            return datetime.fromisoformat(last)
        return None

    def get_expired_polls(self) -> List[Dict]:
        """Get all polls whose TTL has passed (for startup cleanup)."""
        now = datetime.utcnow()
        expired = []
        for poll_id, info in list(self._sent_polls.items()):
            expires_at = datetime.fromisoformat(info["expires_at"])
            if now >= expires_at:
                expired.append({"poll_id": poll_id, **info})
        return expired

    def get_chat_state(self, chat_id: int) -> Dict:
        """Get lifecycle state for a chat (for /polls:status display)."""
        chat_key = str(chat_id)
        return self._chat_state.get(
            chat_key,
            {
                "consecutive_misses": 0,
                "backpressure_active": False,
            },
        )


# Singleton
_tracker: Optional[PollLifecycleTracker] = None


def get_poll_lifecycle_tracker() -> PollLifecycleTracker:
    """Get or create poll lifecycle tracker singleton."""
    global _tracker
    if _tracker is None:
        # Load config from poll_templates.yaml if available
        try:
            import yaml

            with open("config/poll_templates.yaml", "r") as f:
                data = yaml.safe_load(f)
                lifecycle_config = data.get("scheduling", {}).get("lifecycle", {})
        except Exception:
            lifecycle_config = {}

        _tracker = PollLifecycleTracker(
            ttl_minutes=lifecycle_config.get("poll_ttl_minutes", DEFAULT_POLL_TTL_MINUTES),
            max_unanswered=lifecycle_config.get(
                "max_unanswered_polls", DEFAULT_MAX_UNANSWERED
            ),
            backpressure_threshold=lifecycle_config.get(
                "backpressure_threshold", DEFAULT_BACKPRESSURE_THRESHOLD
            ),
        )
    return _tracker
