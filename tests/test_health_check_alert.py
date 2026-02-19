import json
import logging
import time
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from scripts.health_check_alert import (
    format_failure_alert,
    format_recovery_message,
    load_state,
    record_failure,
    record_success,
    save_state,
    send_telegram_alert,
    should_alert,
)


class TestStatePersistence:
    def test_should_return_defaults_when_file_missing(self, tmp_path):
        state_path = str(tmp_path / "nonexistent.json")
        state = load_state(state_path)
        assert state == {
            "failure_count": 0,
            "last_alert_time": None,
            "first_failure_time": None,
        }

    def test_should_roundtrip_write_then_read(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        original = {
            "failure_count": 3,
            "last_alert_time": 1700000000.0,
            "first_failure_time": 1699999000.0,
        }
        save_state(original, state_path)
        loaded = load_state(state_path)
        assert loaded == original

    def test_should_return_defaults_when_file_is_corrupt_json(self, tmp_path, caplog):
        state_path = str(tmp_path / "corrupt.json")
        with open(state_path, "w") as f:
            f.write("{not valid json!!!")
        with caplog.at_level(logging.WARNING):
            state = load_state(state_path)
        assert state == {
            "failure_count": 0,
            "last_alert_time": None,
            "first_failure_time": None,
        }
        assert any(
            "corrupt" in r.message.lower()
            or "invalid" in r.message.lower()
            or "error" in r.message.lower()
            or "fail" in r.message.lower()
            for r in caplog.records
        )

    def test_save_state_creates_valid_json_file(self, tmp_path):
        state_path = str(tmp_path / "output.json")
        state = {
            "failure_count": 1,
            "last_alert_time": None,
            "first_failure_time": 1700000000.0,
        }
        save_state(state, state_path)
        with open(state_path, "r") as f:
            raw = json.load(f)
        assert raw["failure_count"] == 1
        assert raw["last_alert_time"] is None
        assert raw["first_failure_time"] == 1700000000.0

    def test_should_roundtrip_state_with_none_values(self, tmp_path):
        state_path = str(tmp_path / "nones.json")
        original = {
            "failure_count": 0,
            "last_alert_time": None,
            "first_failure_time": None,
        }
        save_state(original, state_path)
        loaded = load_state(state_path)
        assert loaded["last_alert_time"] is None
        assert loaded["first_failure_time"] is None
        assert loaded["failure_count"] == 0


class TestFailureTracking:
    def test_record_failure_increments_count(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        state = load_state(state_path)
        assert state["failure_count"] == 1

    def test_record_failure_increments_count_on_subsequent_calls(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        record_failure("webhook_check", "re-register", state_path)
        state = load_state(state_path)
        assert state["failure_count"] == 3

    def test_record_failure_sets_first_failure_time_on_first_failure(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        state = load_state(state_path)
        assert state["first_failure_time"] is not None
        assert isinstance(state["first_failure_time"], float)

    def test_record_failure_preserves_first_failure_time_on_subsequent_failures(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        state_after_first = load_state(state_path)
        first_time = state_after_first["first_failure_time"]
        record_failure("local_health", "restart", state_path)
        record_failure("webhook_check", "re-register", state_path)
        state_after_third = load_state(state_path)
        assert state_after_third["first_failure_time"] == first_time

    def test_record_failure_persists_state_to_disk(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        with open(state_path) as f:
            raw = json.loads(f.read())
        assert raw["failure_count"] == 1

    def test_should_alert_returns_false_when_failure_count_below_threshold(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        assert should_alert(state_path) is False

    def test_should_alert_returns_true_when_failure_count_reaches_threshold(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        assert should_alert(state_path) is True

    def test_should_alert_returns_true_when_failure_count_exceeds_threshold(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        for _ in range(5):
            record_failure("local_health", "restart", state_path)
        assert should_alert(state_path) is True

    def test_should_alert_returns_false_when_last_alert_within_throttle_window(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        now = 1000000.0
        state = load_state(state_path)
        state["last_alert_time"] = now - 300
        save_state(state, state_path)
        assert should_alert(state_path, now=now) is False

    def test_should_alert_returns_true_when_last_alert_outside_throttle_window(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        now = 1000000.0
        state = load_state(state_path)
        state["last_alert_time"] = now - 601
        save_state(state, state_path)
        assert should_alert(state_path, now=now) is True

    def test_should_alert_returns_true_when_last_alert_exactly_at_throttle_boundary(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        now = 1000000.0
        state = load_state(state_path)
        state["last_alert_time"] = now - 600
        save_state(state, state_path)
        assert should_alert(state_path, now=now) is True

    def test_should_alert_returns_true_when_last_alert_time_is_none(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        state = load_state(state_path)
        assert state.get("last_alert_time") is None
        assert should_alert(state_path) is True

    def test_should_alert_returns_false_on_clean_state(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        assert should_alert(state_path) is False

    def test_record_success_resets_failure_count_to_zero(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        record_success(state_path)
        state = load_state(state_path)
        assert state["failure_count"] == 0

    def test_record_success_clears_first_failure_time(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_success(state_path)
        state = load_state(state_path)
        assert state["first_failure_time"] is None

    def test_record_success_persists_reset_state_to_disk(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_success(state_path)
        with open(state_path) as f:
            raw = json.loads(f.read())
        assert raw["failure_count"] == 0
        assert raw["first_failure_time"] is None

    def test_record_success_returns_was_failing_true_when_there_were_failures(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        was_failing, prev_count, first_time = record_success(state_path)
        assert was_failing is True

    def test_record_success_returns_previous_failure_count(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        record_failure("local_health", "restart", state_path)
        _, prev_count, _ = record_success(state_path)
        assert prev_count == 3

    def test_record_success_returns_first_failure_time(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        record_failure("local_health", "restart", state_path)
        state = load_state(state_path)
        expected_time = state["first_failure_time"]
        _, _, first_time = record_success(state_path)
        assert first_time == expected_time
        assert isinstance(first_time, float)

    def test_record_success_returns_was_failing_false_when_no_prior_failures(
        self, tmp_path
    ):
        state_path = str(tmp_path / "state.json")
        was_failing, prev_count, first_time = record_success(state_path)
        assert was_failing is False
        assert prev_count == 0
        assert first_time is None

    def test_record_success_returns_tuple_of_three_elements(self, tmp_path):
        state_path = str(tmp_path / "state.json")
        result = record_success(state_path)
        assert isinstance(result, tuple)
        assert len(result) == 3


class TestMessageFormatting:
    """Tests for format_failure_alert and format_recovery_message."""

    # --- format_failure_alert ---

    def test_failure_alert_contains_failure_type(self):
        msg = format_failure_alert("local_health", "restart", 3, 1700000000.0)
        assert "local_health" in msg

    def test_failure_alert_contains_action_taken(self):
        msg = format_failure_alert(
            "webhook_check", "webhook_recovery", 2, 1700000000.0
        )
        assert "webhook_recovery" in msg

    def test_failure_alert_contains_failure_count(self):
        msg = format_failure_alert("local_health", "restart", 5, 1700000000.0)
        assert "5" in msg

    def test_failure_alert_contains_timestamp(self):
        msg = format_failure_alert("local_health", "restart", 2, 1700000000.0)
        assert len(msg) > 0
        # Timestamp 1700000000.0 is 2023-11-14
        assert "2023" in msg or "Nov" in msg or "14" in msg

    def test_failure_alert_with_single_failure(self):
        msg = format_failure_alert("local_health", "restart", 1, 1700000000.0)
        assert "1" in msg
        assert "local_health" in msg
        assert "restart" in msg

    def test_failure_alert_with_different_failure_types(self):
        msg1 = format_failure_alert("local_health", "restart", 3, 1700000000.0)
        msg2 = format_failure_alert(
            "webhook_check", "webhook_recovery", 3, 1700000000.0
        )
        assert "local_health" in msg1
        assert "webhook_check" in msg2
        assert "local_health" not in msg2
        assert "webhook_check" not in msg1

    def test_failure_alert_returns_string(self):
        result = format_failure_alert("local_health", "restart", 2, 1700000000.0)
        assert isinstance(result, str)

    def test_failure_alert_with_high_failure_count(self):
        msg = format_failure_alert("local_health", "restart", 100, 1700000000.0)
        assert "100" in msg

    # --- format_recovery_message ---

    def test_recovery_message_indicates_recovery(self):
        now = 1700000300.0  # 5 minutes after first_failure_time
        msg = format_recovery_message(1700000000.0, 3, now=now)
        assert "recover" in msg.lower()

    def test_recovery_message_contains_failure_count(self):
        now = 1700000300.0
        msg = format_recovery_message(1700000000.0, 7, now=now)
        assert "7" in msg

    def test_recovery_message_contains_downtime_duration_minutes(self):
        first_failure = 1700000000.0
        now = first_failure + 300.0  # 5 minutes
        msg = format_recovery_message(first_failure, 3, now=now)
        assert "5" in msg
        assert "minute" in msg.lower()

    def test_recovery_message_contains_downtime_duration_hours_and_minutes(self):
        first_failure = 1700000000.0
        now = first_failure + (2 * 3600 + 15 * 60)  # 2 hours 15 minutes
        msg = format_recovery_message(first_failure, 5, now=now)
        assert "2" in msg
        assert "hour" in msg.lower()
        assert "15" in msg
        assert "minute" in msg.lower()

    def test_recovery_message_short_downtime_under_one_minute(self):
        first_failure = 1700000000.0
        now = first_failure + 30.0  # 30 seconds
        msg = format_recovery_message(first_failure, 2, now=now)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_recovery_message_returns_string(self):
        msg = format_recovery_message(1700000000.0, 2, now=1700000600.0)
        assert isinstance(msg, str)

    def test_recovery_message_with_single_failure(self):
        now = 1700000300.0
        msg = format_recovery_message(1700000000.0, 1, now=now)
        assert "1" in msg
        assert "recover" in msg.lower()

    def test_recovery_message_with_exactly_one_hour_downtime(self):
        first_failure = 1700000000.0
        now = first_failure + 3600.0  # exactly 1 hour
        msg = format_recovery_message(first_failure, 4, now=now)
        assert "1" in msg
        assert "hour" in msg.lower()

    def test_recovery_message_now_defaults_to_current_time(self):
        first_failure = time.time() - 120  # 2 minutes ago
        msg = format_recovery_message(first_failure, 3)
        assert isinstance(msg, str)
        assert "recover" in msg.lower()
        assert "3" in msg
        assert "minute" in msg.lower()


class TestAlertDispatch:
    """Tests for send_telegram_alert: HTTP dispatch via urllib, never raises."""

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_successful_send_returns_true(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok":true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_telegram_alert("Bot is down", "123:ABC", "456")
        assert result is True

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_successful_send_calls_correct_url(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok":true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        send_telegram_alert("test msg", "TOK123", "CHAT456")
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        assert "https://api.telegram.org/botTOK123/sendMessage" in request_obj.full_url

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_network_error_returns_false(self, mock_urlopen, caplog):
        mock_urlopen.side_effect = URLError("Connection refused")

        with caplog.at_level(logging.ERROR):
            result = send_telegram_alert("alert", "tok", "chat")
        assert result is False

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_network_error_logs_message(self, mock_urlopen, caplog):
        mock_urlopen.side_effect = URLError("Connection refused")

        with caplog.at_level(logging.ERROR):
            send_telegram_alert("alert", "tok", "chat")
        assert any(
            "error" in r.message.lower()
            or "fail" in r.message.lower()
            or "telegram" in r.message.lower()
            for r in caplog.records
        )

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_http_error_returns_false(self, mock_urlopen, caplog):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.telegram.org/bot/sendMessage",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with caplog.at_level(logging.ERROR):
            result = send_telegram_alert("alert", "bad_token", "chat")
        assert result is False

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_http_error_logs_message(self, mock_urlopen, caplog):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.telegram.org/bot/sendMessage",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with caplog.at_level(logging.ERROR):
            send_telegram_alert("alert", "bad_token", "chat")
        assert len(caplog.records) > 0

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_timeout_returns_false(self, mock_urlopen, caplog):
        import socket

        mock_urlopen.side_effect = socket.timeout("timed out")

        with caplog.at_level(logging.ERROR):
            result = send_telegram_alert("alert", "tok", "chat")
        assert result is False

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_timeout_logs_message(self, mock_urlopen, caplog):
        import socket

        mock_urlopen.side_effect = socket.timeout("timed out")

        with caplog.at_level(logging.ERROR):
            send_telegram_alert("alert", "tok", "chat")
        assert len(caplog.records) > 0

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_generic_exception_returns_false(self, mock_urlopen, caplog):
        mock_urlopen.side_effect = RuntimeError("something unexpected")

        with caplog.at_level(logging.ERROR):
            result = send_telegram_alert("alert", "tok", "chat")
        assert result is False

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_generic_exception_never_raises(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("something unexpected")

        # Must not raise -- just return False
        result = send_telegram_alert("alert", "tok", "chat")
        assert result is False

    @patch("scripts.health_check_alert.urllib.request.urlopen")
    def test_sends_message_and_chat_id_in_request_body(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok":true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        send_telegram_alert("Hello world", "mytoken", "12345")
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        body = json.loads(request_obj.data)
        assert body["chat_id"] == "12345"
        assert body["text"] == "Hello world"
