"""Tests for health check alerting service.

TDD: RED → GREEN → REFACTOR for health alert state, decision logic,
and message formatting.
"""

import os
import tempfile
import time
from unittest.mock import patch


class TestHealthAlertState:
    """Slice 1: State persistence — track consecutive failures."""

    def test_initial_state_has_zero_failures(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        assert state.consecutive_failures == 0
        assert state.last_alert_time == 0.0
        assert state.last_failure_reason == ""

    def test_record_failure_increments_count(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        state.record_failure("endpoint down")
        assert state.consecutive_failures == 1
        assert state.last_failure_reason == "endpoint down"

    def test_record_multiple_failures(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        state.record_failure("endpoint down")
        state.record_failure("webhook error")
        assert state.consecutive_failures == 2
        assert state.last_failure_reason == "webhook error"

    def test_record_recovery_resets_count(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        state.record_failure("endpoint down")
        state.record_failure("endpoint down")
        state.record_recovery()
        assert state.consecutive_failures == 0
        assert state.last_failure_reason == ""

    def test_save_and_load_state(self):
        from src.services.health_alert_service import HealthAlertState

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            state = HealthAlertState()
            state.record_failure("test reason")
            state.record_failure("test reason 2")
            state.last_alert_time = 1000.0
            state.save(path)

            loaded = HealthAlertState.load(path)
            assert loaded.consecutive_failures == 2
            assert loaded.last_failure_reason == "test reason 2"
            assert loaded.last_alert_time == 1000.0
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_fresh_state(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState.load("/tmp/nonexistent_health_state_xyz.json")
        assert state.consecutive_failures == 0

    def test_load_corrupt_file_returns_fresh_state(self):
        from src.services.health_alert_service import HealthAlertState

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not valid json{{{")
            path = f.name
        try:
            state = HealthAlertState.load(path)
            assert state.consecutive_failures == 0
        finally:
            os.unlink(path)


class TestAlertDecisionLogic:
    """Slice 2: Alert decision — threshold, cooldown, recovery."""

    def test_should_not_alert_below_threshold(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        state.record_failure("down")
        state.record_failure("down")
        # Default threshold is 3, only 2 failures
        assert state.should_alert(threshold=3) is False

    def test_should_alert_at_threshold(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        for _ in range(3):
            state.record_failure("down")
        assert state.should_alert(threshold=3) is True

    def test_should_not_alert_during_cooldown(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        for _ in range(5):
            state.record_failure("down")
        state.last_alert_time = time.time()  # Just alerted
        assert state.should_alert(threshold=3, cooldown_seconds=600) is False

    def test_should_alert_after_cooldown_expires(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        for _ in range(5):
            state.record_failure("down")
        state.last_alert_time = time.time() - 700  # 700s ago, cooldown is 600s
        assert state.should_alert(threshold=3, cooldown_seconds=600) is True

    def test_should_send_recovery_after_failures(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        for _ in range(3):
            state.record_failure("down")
        state.last_alert_time = time.time() - 100  # Previously alerted
        # Now recovery happens
        assert state.should_send_recovery() is True

    def test_should_not_send_recovery_if_no_prior_alert(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        state.record_failure("down")
        # Only 1 failure, never alerted
        assert state.should_send_recovery() is False

    def test_should_not_send_recovery_if_no_failures(self):
        from src.services.health_alert_service import HealthAlertState

        state = HealthAlertState()
        assert state.should_send_recovery() is False


class TestAlertMessageFormatting:
    """Slice 3: Message formatting."""

    def test_failure_alert_contains_count(self):
        from src.services.health_alert_service import format_alert_message

        msg = format_alert_message(
            consecutive_failures=5, reason="Health endpoint did not respond"
        )
        assert "5" in msg
        assert "Health endpoint did not respond" in msg

    def test_failure_alert_contains_warning_emoji_or_header(self):
        from src.services.health_alert_service import format_alert_message

        msg = format_alert_message(consecutive_failures=3, reason="down")
        # Should have some alert indicator
        assert "alert" in msg.lower() or "warning" in msg.lower() or "⚠" in msg

    def test_recovery_message_is_distinct(self):
        from src.services.health_alert_service import format_recovery_message

        msg = format_recovery_message(total_downtime_checks=10)
        assert "recover" in msg.lower() or "restored" in msg.lower() or "✅" in msg
        assert "10" in msg


class TestHealthAlertIntegration:
    """Slice 4: Integration — process_health_result orchestrates everything."""

    def test_process_failure_below_threshold_no_alert(self):
        from src.services.health_alert_service import HealthAlertState

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            from src.services.health_alert_service import process_health_result

            with patch("src.services.health_alert_service._send_alert") as mock_send:
                process_health_result(
                    success=False,
                    reason="down",
                    state_file=path,
                    admin_chat_id=123,
                    threshold=3,
                )
                mock_send.assert_not_called()

            # State should have 1 failure
            state = HealthAlertState.load(path)
            assert state.consecutive_failures == 1
        finally:
            os.unlink(path)

    def test_process_failure_at_threshold_sends_alert(self):
        from src.services.health_alert_service import HealthAlertState

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            from src.services.health_alert_service import process_health_result

            # Pre-populate 2 failures
            state = HealthAlertState()
            state.record_failure("down")
            state.record_failure("down")
            state.save(path)

            with patch("src.services.health_alert_service._send_alert") as mock_send:
                process_health_result(
                    success=False,
                    reason="down again",
                    state_file=path,
                    admin_chat_id=123,
                    threshold=3,
                )
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert call_args[0][0] == 123  # chat_id
                assert "down again" in call_args[0][1]  # message contains reason
        finally:
            os.unlink(path)

    def test_process_success_after_alert_sends_recovery(self):
        from src.services.health_alert_service import HealthAlertState

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            from src.services.health_alert_service import process_health_result

            # Pre-populate failures + alert
            state = HealthAlertState()
            for _ in range(5):
                state.record_failure("down")
            state.last_alert_time = time.time() - 60
            state.save(path)

            with patch("src.services.health_alert_service._send_alert") as mock_send:
                process_health_result(
                    success=True,
                    reason="",
                    state_file=path,
                    admin_chat_id=123,
                )
                mock_send.assert_called_once()
                msg = mock_send.call_args[0][1]
                assert (
                    "recover" in msg.lower() or "restored" in msg.lower() or "✅" in msg
                )

            # State should be reset
            state = HealthAlertState.load(path)
            assert state.consecutive_failures == 0
        finally:
            os.unlink(path)

    def test_process_success_without_prior_alert_no_message(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            from src.services.health_alert_service import process_health_result

            with patch("src.services.health_alert_service._send_alert") as mock_send:
                process_health_result(
                    success=True,
                    reason="",
                    state_file=path,
                    admin_chat_id=123,
                )
                mock_send.assert_not_called()
        finally:
            os.unlink(path)
