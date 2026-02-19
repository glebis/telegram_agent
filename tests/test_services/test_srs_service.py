"""Tests for SRS Service - callback data validation and keyboard creation."""

from unittest.mock import MagicMock, patch

import pytest


class TestSRSCallbackDataSize:
    """Verify all SRS callback data stays within Telegram's 64-byte limit."""

    @pytest.fixture
    def srs_service(self):
        """Create SRS service instance."""
        # Need to mock the imports that require database/filesystem
        with (
            patch("src.services.srs_service.get_due_cards"),
            patch("src.services.srs_service.update_card_rating"),
            patch("src.services.srs_service.send_morning_batch"),
            patch("src.services.srs_service.get_review_command_cards"),
            patch("src.services.srs_service.get_config"),
            patch("src.services.srs_service.set_config"),
            patch("src.services.srs_service.load_note_content"),
            patch("src.services.srs_service.get_backlinks"),
        ):
            from src.services.srs_service import SRSService

            return SRSService()

    def test_all_callback_data_under_64_bytes(self, srs_service):
        """Every button in the SRS keyboard must have callback_data under 64 bytes."""
        # Test with various card_id values including large ones
        test_card_ids = [1, 42, 999, 99999, 999999999]

        for card_id in test_card_ids:
            rows = srs_service.create_card_keyboard(
                card_id=card_id,
                note_path="/Users/server/Research/vault/Ideas/Some Very Long Idea Name That Could Be Problematic.md",
            )

            for row in rows:
                for button in row:
                    data_bytes = button["callback_data"].encode("utf-8")
                    assert len(data_bytes) <= 64, (
                        f"Callback data too long ({len(data_bytes)} bytes): "
                        f"'{button['callback_data']}' for card_id={card_id}"
                    )

    def test_callback_data_does_not_include_note_path(self, srs_service):
        """Callback data should NOT contain the note path (it's looked up from DB)."""
        long_path = "/Users/server/Research/vault/Ideas/A Very Long Unicode Note Name That Would Definitely Exceed The 64 Byte Limit.md"
        rows = srs_service.create_card_keyboard(card_id=42, note_path=long_path)

        for row in rows:
            for button in row:
                assert long_path not in button["callback_data"]
                assert "vault" not in button["callback_data"]

    def test_callback_data_format_parseable(self, srs_service):
        """Callback data should be parseable as action:card_id."""
        rows = srs_service.create_card_keyboard(card_id=42, note_path="/test/path.md")

        expected_actions = {
            "srs_again",
            "srs_hard",
            "srs_good",
            "srs_easy",
            "srs_develop",
        }
        found_actions = set()

        for row in rows:
            for button in row:
                parts = button["callback_data"].split(":")
                assert (
                    len(parts) == 2
                ), f"Expected action:card_id format, got: {button['callback_data']}"
                action, card_id_str = parts
                found_actions.add(action)
                assert card_id_str == "42"

        assert found_actions == expected_actions

    def test_keyboard_has_all_rating_buttons(self, srs_service):
        """Keyboard should have Again, Hard, Good, Easy, and Develop buttons."""
        rows = srs_service.create_card_keyboard(card_id=1, note_path="/test.md")

        button_texts = []
        for row in rows:
            for button in row:
                button_texts.append(button["text"])

        assert any("Again" in t for t in button_texts)
        assert any("Hard" in t for t in button_texts)
        assert any("Good" in t for t in button_texts)
        assert any("Easy" in t for t in button_texts)
        assert any("Develop" in t for t in button_texts)

    def test_max_possible_card_id_under_limit(self, srs_service):
        """Even with maximum realistic card_id, data must be under 64 bytes."""
        # SQLite INTEGER max is 2^63 - 1
        huge_card_id = 9999999999999999
        rows = srs_service.create_card_keyboard(
            card_id=huge_card_id, note_path="/test.md"
        )

        for row in rows:
            for button in row:
                data_bytes = button["callback_data"].encode("utf-8")
                assert len(data_bytes) <= 64, (
                    f"Callback data too long ({len(data_bytes)} bytes) "
                    f"with huge card_id: '{button['callback_data']}'"
                )


class TestLegacySRSTelegramCallbackData:
    """Verify the legacy srs_telegram.py also respects the 64-byte limit."""

    def test_legacy_callback_data_under_64_bytes(self):
        """Legacy create_card_keyboard must produce callback_data under 64 bytes."""
        from src.services.srs.srs_telegram import create_card_keyboard

        long_path = "/Users/server/Research/vault/Ideas/Some Very Long Idea Name That Could Be Problematic.md"
        keyboard = create_card_keyboard(card_id=42, note_path=long_path)

        for row in keyboard:
            for button in row:
                data = button["callback_data"]
                data_bytes = data.encode("utf-8")
                assert len(data_bytes) <= 64, (
                    f"Legacy callback data too long ({len(data_bytes)} bytes): "
                    f"'{data}'"
                )

    def test_legacy_callback_data_no_note_path(self):
        """Legacy callback data should NOT contain the note path."""
        from src.services.srs.srs_telegram import create_card_keyboard

        note_path = "/Users/server/Research/vault/Ideas/Test.md"
        keyboard = create_card_keyboard(card_id=42, note_path=note_path)

        for row in keyboard:
            for button in row:
                assert note_path not in button["callback_data"]
                assert "vault" not in button["callback_data"]

    def test_legacy_callback_data_parseable(self):
        """Legacy callback data should be parseable as action:card_id."""
        from src.services.srs.srs_telegram import create_card_keyboard

        keyboard = create_card_keyboard(card_id=42, note_path="/test.md")

        expected_actions = {
            "srs_again",
            "srs_hard",
            "srs_good",
            "srs_easy",
            "srs_develop",
        }
        found_actions = set()

        for row in keyboard:
            for button in row:
                parts = button["callback_data"].split(":")
                assert (
                    len(parts) == 2
                ), f"Expected action:card_id format, got: {button['callback_data']}"
                action, card_id_str = parts
                found_actions.add(action)
                assert card_id_str == "42"

        assert found_actions == expected_actions

    def test_legacy_handle_rating_uses_card_id_only(self):
        """Legacy handle_rating_callback should work with action:card_id format."""
        from src.services.srs.srs_telegram import handle_rating_callback

        # The new format is action:card_id (note_path looked up from DB)
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("/test/path.md",)

        with (
            patch("src.services.srs.srs_telegram.update_card_rating") as mock_update,
            patch("sqlite3.connect", return_value=mock_conn),
        ):
            mock_update.return_value = {
                "success": True,
                "next_review": "2026-02-04",
                "interval": 1,
                "ease_factor": 2.5,
            }
            result = handle_rating_callback("srs_good:42")
            assert result["success"] is True
            assert result["action"] == "rated"
