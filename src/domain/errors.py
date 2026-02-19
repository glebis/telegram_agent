"""
Typed domain errors for the Telegram Agent.

These replace bare except/return None patterns so callers can distinguish
specific failure modes (missing settings vs. missing tracker vs. TTS failure)
and map each to an appropriate user-facing message.
"""


class DomainError(Exception):
    """Base class for all domain-specific errors."""


# ---------------------------------------------------------------------------
# Accountability domain
# ---------------------------------------------------------------------------


class UserSettingsNotFound(DomainError):
    """No UserSettings row exists for the given user."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"No settings found for user {user_id}")


class TrackerNotFound(DomainError):
    """Tracker with the given ID does not exist."""

    def __init__(self, tracker_id: int) -> None:
        self.tracker_id = tracker_id
        super().__init__(f"Tracker {tracker_id} not found")


class VoiceSynthesisFailure(DomainError):
    """TTS provider returned an error or timed out."""


# ---------------------------------------------------------------------------
# Poll domain
# ---------------------------------------------------------------------------


class PollNotTracked(DomainError):
    """Received an answer for a poll we are not tracking."""

    def __init__(self, poll_id: str) -> None:
        self.poll_id = poll_id
        super().__init__(f"Received answer for untracked poll: {poll_id}")


class PollSendFailure(DomainError):
    """Failed to send a poll via the Telegram API."""


class EmbeddingFailure(DomainError):
    """Embedding generation failed (model not loaded, OOM, etc.)."""
