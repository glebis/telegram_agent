"""
Trail Review Service - Manages trail reviews via Telegram polls.

Provides scheduled trail status checks with multi-question polling sequences.
Integrates with vault trail files to update status and schedule next reviews.

State persistence: poll states are saved to a JSON file so that in-progress
reviews survive bot restarts.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import frontmatter

from src.core.i18n import t

logger = logging.getLogger(__name__)

# File for persisting poll state across restarts
_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "trail_poll_state.json"


class TrailReviewService:
    """Service for managing trail reviews via Telegram polls."""

    def __init__(self, vault_path: Path = None):
        self.vault_path = vault_path or Path.home() / "Research/vault"
        self.trails_dir = self.vault_path / "Trails"

        # Poll state tracking: {chat_id: {trail_path: poll_state}}
        self._poll_states: Dict[int, Dict[str, Dict]] = {}

        # Mapping: {poll_id: {trail_path, field, chat_id, options}}
        # Persisted alongside _poll_states so answers work after restart
        self._poll_id_map: Dict[str, Dict] = {}

        # Load persisted state
        self._load_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load poll state from disk (survives restarts)."""
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text())
                # Convert chat_id keys back to int
                raw_states = data.get("poll_states", {})
                self._poll_states = {int(k): v for k, v in raw_states.items()}
                self._poll_id_map = data.get("poll_id_map", {})
                logger.info(
                    f"Loaded trail poll state: {len(self._poll_states)} chats, "
                    f"{len(self._poll_id_map)} poll mappings"
                )
        except Exception as e:
            logger.error(f"Error loading trail poll state: {e}")
            self._poll_states = {}
            self._poll_id_map = {}

    def _save_state(self) -> None:
        """Persist poll state to disk."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "poll_states": {str(k): v for k, v in self._poll_states.items()},
                "poll_id_map": self._poll_id_map,
                "saved_at": datetime.now().isoformat(),
            }
            _STATE_FILE.write_text(json.dumps(data, indent=2, default=str))
            logger.debug("Saved trail poll state to disk")
        except Exception as e:
            logger.error(f"Error saving trail poll state: {e}")

    # ------------------------------------------------------------------
    # Poll-ID mapping (replaces context.bot_data['trail_polls'])
    # ------------------------------------------------------------------

    def register_poll(
        self,
        poll_id: str,
        trail_path: str,
        field: str,
        chat_id: int,
        options: List[str],
    ) -> None:
        """Register a sent poll so its answer can be matched later."""
        self._poll_id_map[poll_id] = {
            "trail_path": trail_path,
            "field": field,
            "chat_id": chat_id,
            "options": options,
        }
        self._save_state()

    def unregister_poll(self, poll_id: str) -> None:
        """Remove a poll mapping after it has been answered."""
        self._poll_id_map.pop(poll_id, None)
        self._save_state()

    def get_poll_info(self, poll_id: str) -> Optional[Dict]:
        """Look up trail info for a poll_id.  Returns None if not a trail poll."""
        return self._poll_id_map.get(poll_id)

    # ------------------------------------------------------------------
    # Trail discovery
    # ------------------------------------------------------------------

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
                if post.get("type") != "trail":
                    continue

                status = post.get("status", "active")
                if status not in ["active", "paused"]:
                    continue

                # Check next_review date
                next_review = post.get("next_review")
                if not next_review:
                    # No review scheduled, add with low priority
                    trails_due.append(
                        {
                            "path": str(trail_file),
                            "name": trail_file.stem.replace("Trail - ", ""),
                            "status": status,
                            "velocity": post.get("velocity", "medium"),
                            "direction": post.get("direction", "unknown"),
                            "urgency": 0,
                            "next_review": None,
                        }
                    )
                    continue

                # Parse next_review date (format: YYYY-MM-DD)
                if isinstance(next_review, str):
                    try:
                        next_review_date = datetime.strptime(
                            next_review, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        logger.warning(
                            f"Invalid next_review format in {trail_file.name}: {next_review}"
                        )
                        continue
                else:
                    next_review_date = next_review

                # Calculate urgency (days overdue, negative if future)
                days_overdue = (today - next_review_date).days

                if days_overdue >= 0:
                    trails_due.append(
                        {
                            "path": str(trail_file),
                            "name": trail_file.stem.replace("Trail - ", ""),
                            "status": status,
                            "velocity": post.get("velocity", "medium"),
                            "direction": post.get("direction", "unknown"),
                            "urgency": days_overdue,
                            "next_review": next_review_date.isoformat(),
                        }
                    )

            except Exception as e:
                logger.error(f"Error processing trail {trail_file.name}: {e}")
                continue

        # Sort by urgency (most overdue first)
        trails_due.sort(key=lambda t: t["urgency"], reverse=True)

        return trails_due

    def get_random_active_trail(self) -> Optional[Dict]:
        """Get a random active trail for proactive review."""
        import random

        trails = self.get_trails_for_review()
        if not trails:
            return None

        # Weight by urgency
        if trails[0]["urgency"] > 0:
            # At least one trail is overdue, pick from overdue ones
            overdue = [t for t in trails if t["urgency"] > 0]
            return random.choice(overdue)
        else:
            # All trails current, pick any active one
            active = [t for t in trails if t["status"] == "active"]
            if active:
                return random.choice(active)
            return random.choice(trails)

    # ------------------------------------------------------------------
    # Poll creation
    # ------------------------------------------------------------------

    def create_velocity_poll(self, trail: Dict, locale: str = "en") -> Dict:
        """Create velocity assessment poll."""
        return {
            "question": t("trails.poll.velocity_question", locale, name=trail["name"]),
            "options": [
                t("trails.poll.velocity_high", locale),
                t("trails.poll.velocity_medium", locale),
                t("trails.poll.velocity_low", locale),
                t("trails.poll.velocity_paused", locale),
            ],
            "values": ["high", "medium", "low", "low"],
            "current_value": trail.get("velocity", "medium"),
            "field": "velocity",
        }

    def create_status_poll(self, trail: Dict, locale: str = "en") -> Dict:
        """Create status check poll."""
        return {
            "question": t("trails.poll.status_question", locale, name=trail["name"]),
            "options": [
                t("trails.poll.status_active", locale),
                t("trails.poll.status_paused", locale),
                t("trails.poll.status_completed", locale),
                t("trails.poll.status_abandoned", locale),
            ],
            "values": ["active", "paused", "completed", "abandoned"],
            "current_value": trail.get("status", "active"),
            "field": "status",
        }

    def create_stage_poll(
        self, trail: Dict, direction: str, locale: str = "en"
    ) -> Dict:
        """Create stage/progress poll based on trail direction."""
        if direction == "building":
            return {
                "question": t(
                    "trails.poll.stage_building_question",
                    locale,
                    name=trail["name"],
                ),
                "options": [
                    t("trails.poll.stage_planning", locale),
                    t("trails.poll.stage_building", locale),
                    t("trails.poll.stage_testing", locale),
                    t("trails.poll.stage_shipping", locale),
                ],
                "values": ["planning", "building", "testing", "shipping"],
                "field": "stage",
            }
        elif direction == "research":
            return {
                "question": t(
                    "trails.poll.stage_research_question",
                    locale,
                    name=trail["name"],
                ),
                "options": [
                    t("trails.poll.stage_exploring", locale),
                    t("trails.poll.stage_synthesizing", locale),
                    t("trails.poll.stage_integrating", locale),
                    t("trails.poll.stage_applying", locale),
                ],
                "values": [
                    "exploring",
                    "synthesizing",
                    "integrating",
                    "applying",
                ],
                "field": "stage",
            }
        else:
            return {
                "question": t(
                    "trails.poll.stage_progress_question",
                    locale,
                    name=trail["name"],
                ),
                "options": [
                    t("trails.poll.stage_starting", locale),
                    t("trails.poll.stage_growing", locale),
                    t("trails.poll.stage_mature", locale),
                    t("trails.poll.stage_finishing", locale),
                ],
                "values": ["starting", "growing", "mature", "finishing"],
                "field": "stage",
            }

    def create_next_review_poll(self, trail: Dict, locale: str = "en") -> Dict:
        """Create next review scheduling poll."""
        return {
            "question": t(
                "trails.poll.next_review_question",
                locale,
                name=trail["name"],
            ),
            "options": [
                t("trails.poll.review_tomorrow", locale),
                t("trails.poll.review_1_week", locale),
                t("trails.poll.review_2_weeks", locale),
                t("trails.poll.review_1_month", locale),
            ],
            "values": ["tomorrow", "1_week", "2_weeks", "1_month"],
            "field": "next_review",
        }

    def get_poll_sequence(self, trail: Dict, locale: str = "en") -> List[Dict]:
        """Get sequence of polls for a trail review."""
        sequence = [
            self.create_velocity_poll(trail, locale),
            self.create_status_poll(trail, locale),
            self.create_stage_poll(trail, trail.get("direction", "unknown"), locale),
            self.create_next_review_poll(trail, locale),
        ]
        return sequence

    # ------------------------------------------------------------------
    # Poll sequence lifecycle
    # ------------------------------------------------------------------

    def start_poll_sequence(
        self, chat_id: int, trail: Dict, locale: str = "en"
    ) -> Optional[Dict]:
        """
        Start a new poll sequence for a trail.

        Returns the first poll to send, or None if error.
        """
        if chat_id not in self._poll_states:
            self._poll_states[chat_id] = {}

        sequence = self.get_poll_sequence(trail, locale)

        self._poll_states[chat_id][trail["path"]] = {
            "trail": trail,
            "sequence": sequence,
            "current_index": 0,
            "answers": {},
            "started_at": datetime.now().isoformat(),
        }

        self._save_state()
        return sequence[0] if sequence else None

    def get_next_poll(
        self, chat_id: int, trail_path: str, answer: str
    ) -> Tuple[Optional[Dict], bool]:
        """
        Record answer and get next poll in sequence.

        Returns: (next_poll, is_complete)
        """
        if chat_id not in self._poll_states:
            return None, True

        if trail_path not in self._poll_states[chat_id]:
            return None, True

        state = self._poll_states[chat_id][trail_path]
        current_poll = state["sequence"][state["current_index"]]

        # Record answer — use internal value if available
        if "values" in current_poll:
            try:
                option_index = current_poll["options"].index(answer)
                state["answers"][current_poll["field"]] = current_poll["values"][
                    option_index
                ]
            except (ValueError, IndexError):
                state["answers"][current_poll["field"]] = answer
        else:
            state["answers"][current_poll["field"]] = answer

        # Move to next poll
        state["current_index"] += 1

        # Check if sequence complete
        if state["current_index"] >= len(state["sequence"]):
            self._save_state()
            return None, True

        self._save_state()
        return state["sequence"][state["current_index"]], False

    def get_active_review(self, chat_id: int) -> Optional[Dict]:
        """Get the currently active trail review for a chat, if any."""
        if chat_id not in self._poll_states:
            return None
        # Return the first (usually only) active review
        for trail_path, state in self._poll_states[chat_id].items():
            return {
                "trail_path": trail_path,
                "trail": state["trail"],
                "answers": state["answers"],
                "current_index": state["current_index"],
                "total_polls": len(state["sequence"]),
                "started_at": state.get("started_at"),
            }
        return None

    def finalize_review(self, chat_id: int, trail_path: str) -> Dict:
        """
        Finalize review and update trail file.

        Returns summary of changes made.
        """
        if chat_id not in self._poll_states:
            return {"success": False, "error": "No poll state found"}

        if trail_path not in self._poll_states[chat_id]:
            return {"success": False, "error": "Trail not in poll state"}

        state = self._poll_states[chat_id][trail_path]
        answers = state["answers"]
        trail = state["trail"]

        try:
            # Load trail file
            post = frontmatter.load(trail_path)

            # Update frontmatter based on answers
            changes = []

            # Velocity (uses internal values from poll)
            if "velocity" in answers:
                velocity_map = {
                    "high": "high",
                    "medium": "medium",
                    "low": "low",
                }
                new_velocity = velocity_map.get(answers["velocity"], "medium")
                if post.get("velocity") != new_velocity:
                    post["velocity"] = new_velocity
                    changes.append(f"velocity → {new_velocity}")

            # Status (uses internal values from poll)
            if "status" in answers:
                status_map = {
                    "active": "active",
                    "paused": "paused",
                    "completed": "completed",
                    "abandoned": "abandoned",
                }
                new_status = status_map.get(answers["status"], "active")
                if post.get("status") != new_status:
                    post["status"] = new_status
                    changes.append(f"status → {new_status}")

            # Next review
            next_review_date = None
            if "next_review" in answers:
                today = datetime.now().date()
                review_map = {
                    "tomorrow": today + timedelta(days=1),
                    "1_week": today + timedelta(weeks=1),
                    "2_weeks": today + timedelta(weeks=2),
                    "1_month": today + timedelta(days=30),
                }
                next_review_date = review_map.get(
                    answers["next_review"], today + timedelta(weeks=1)
                )
                post["next_review"] = next_review_date.isoformat()
                changes.append(f"next_review → {next_review_date.isoformat()}")

            # Update last_updated
            post["last_updated"] = datetime.now().date().isoformat()
            changes.append(f"last_updated → {post['last_updated']}")

            # Write back to file
            with open(trail_path, "w") as f:
                f.write(frontmatter.dumps(post))

            # Clean up poll state
            del self._poll_states[chat_id][trail_path]
            self._save_state()

            return {
                "success": True,
                "trail_name": trail["name"],
                "trail_path": trail_path,
                "changes": changes,
                "answers": answers,
                "next_review": (
                    next_review_date.isoformat() if next_review_date else None
                ),
            }

        except Exception as e:
            logger.error(f"Error finalizing review for {trail_path}: {e}")
            return {"success": False, "error": str(e)}

    def get_trail_content(self, trail_path: str) -> Optional[str]:
        """Read the full content of a trail file."""
        try:
            path = Path(trail_path)
            if path.exists():
                return path.read_text()
            return None
        except Exception as e:
            logger.error(f"Error reading trail file {trail_path}: {e}")
            return None

    def build_trail_context_for_claude(
        self,
        trail_path: str,
        trail_name: str,
        answers: Dict[str, str],
        user_comment: str,
    ) -> str:
        """
        Build a comprehensive prompt for Claude to update a trail file
        based on poll answers and user's comment/voice message.

        Args:
            trail_path: Path to the trail markdown file
            trail_name: Display name of the trail
            answers: Dict of poll field -> selected answer
            user_comment: Text or voice transcription from user
        """
        trail_content = self.get_trail_content(trail_path)

        parts = [
            f"[Trail Review Update for '{trail_name}']",
            "",
            "The user just completed a trail review checkin via polls and added a comment.",
            "Please update the trail file based on their poll answers AND their comment.",
            "",
            "== POLL ANSWERS ==",
        ]

        for field, answer in answers.items():
            parts.append(f"  {field}: {answer}")

        parts.append("")
        parts.append("== USER COMMENT ==")
        parts.append(user_comment)
        parts.append("")

        if trail_content:
            parts.append("== CURRENT TRAIL FILE ==")
            parts.append(f"Path: {trail_path}")
            parts.append("")
            parts.append(trail_content)
            parts.append("")

        parts.append("== INSTRUCTIONS ==")
        parts.append(
            "1. Read the trail file carefully\n"
            "2. Based on the poll answers and user comment, update the trail:\n"
            "   - Update the Progress Markers table with a new row for today\n"
            "   - Update Current Position if the comment describes new progress\n"
            "   - Update Open Questions if new questions were raised\n"
            "   - Update any other relevant sections\n"
            "3. The frontmatter (velocity, status, next_review) was already updated by the poll system\n"
            "4. Write the updated file using the Write tool\n"
            "5. Keep the user's voice/style in the updates"
        )

        return "\n".join(parts)


def get_trail_review_service() -> TrailReviewService:
    """Get the global trail review service instance (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.TRAIL_REVIEW)
