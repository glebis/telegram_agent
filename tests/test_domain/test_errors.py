"""
Tests for typed domain errors.

Verifies that each error class exists, inherits correctly,
and carries the right attributes for downstream handling.
"""

pass


class TestDomainErrorHierarchy:
    """All domain errors inherit from a common base."""

    def test_base_error_exists(self):
        from src.domain.errors import DomainError

        assert issubclass(DomainError, Exception)

    def test_base_error_carries_message(self):
        from src.domain.errors import DomainError

        err = DomainError("something broke")
        assert str(err) == "something broke"


class TestAccountabilityErrors:
    """Errors raised by accountability_service."""

    def test_user_settings_not_found(self):
        from src.domain.errors import DomainError, UserSettingsNotFound

        assert issubclass(UserSettingsNotFound, DomainError)
        err = UserSettingsNotFound(user_id=42)
        assert err.user_id == 42
        assert "42" in str(err)

    def test_tracker_not_found(self):
        from src.domain.errors import DomainError, TrackerNotFound

        assert issubclass(TrackerNotFound, DomainError)
        err = TrackerNotFound(tracker_id=7)
        assert err.tracker_id == 7
        assert "7" in str(err)

    def test_voice_synthesis_failure(self):
        from src.domain.errors import DomainError, VoiceSynthesisFailure

        assert issubclass(VoiceSynthesisFailure, DomainError)
        err = VoiceSynthesisFailure("timeout from TTS provider")
        assert "timeout" in str(err).lower()


class TestPollErrors:
    """Errors raised by poll_service."""

    def test_poll_not_tracked(self):
        from src.domain.errors import DomainError, PollNotTracked

        assert issubclass(PollNotTracked, DomainError)
        err = PollNotTracked(poll_id="abc123")
        assert err.poll_id == "abc123"
        assert "abc123" in str(err)

    def test_poll_send_failure(self):
        from src.domain.errors import DomainError, PollSendFailure

        assert issubclass(PollSendFailure, DomainError)
        err = PollSendFailure("Telegram API 429")
        assert "429" in str(err)

    def test_embedding_failure(self):
        from src.domain.errors import DomainError, EmbeddingFailure

        assert issubclass(EmbeddingFailure, DomainError)
        err = EmbeddingFailure("model not loaded")
        assert "model not loaded" in str(err)
