"""
Tests for link + comment pair detection in Message Buffer Service.

Tests cover:
- Basic link + comment detection
- Link with query params / fragments
- Short text with embedded URL (≤100 chars)
- Long text with embedded URL (>100 chars, URL <70%) — rejected
- Comment with small URL (<30%) — detected
- Comment that's mostly URL (>30%) — rejected
- Single message — rejected
- 3+ messages — rejected
- Reply messages — rejected
- Command messages — rejected
- Non-text messages — rejected
- get_link_comment_context() formatting
"""

from datetime import datetime
from unittest.mock import MagicMock

from src.services.message_buffer import (
    BufferedMessage,
    CombinedMessage,
    _detect_link_comment_pair,
)


def _make_text_msg(
    text: str,
    msg_id: int = 1,
    has_reply: bool = False,
    message_type: str = "text",
) -> BufferedMessage:
    """Helper to create a BufferedMessage for testing."""
    message = MagicMock()
    message.message_id = msg_id
    message.reply_to_message = MagicMock() if has_reply else None
    return BufferedMessage(
        message_id=msg_id,
        message=message,
        update=MagicMock(),
        context=MagicMock(),
        timestamp=datetime.now(),
        message_type=message_type,
        text=text,
    )


# =============================================================================
# Detection: positive cases
# =============================================================================


class TestLinkCommentDetectionPositive:
    """Cases where link + comment should be detected."""

    def test_basic_link_plus_comment(self):
        msgs = [
            _make_text_msg("https://example.com/article", msg_id=1),
            _make_text_msg("This is really interesting", msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is not None
        assert result["link_text"] == "https://example.com/article"
        assert result["comment"] == "This is really interesting"

    def test_link_with_query_params(self):
        url = "https://example.com/page?utm_source=twitter&id=42#section"
        msgs = [
            _make_text_msg(url, msg_id=1),
            _make_text_msg("Check out this section", msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is not None
        assert result["link_text"] == url

    def test_short_text_with_embedded_url(self):
        """Text ≤100 chars containing a URL should be detected as link-dominant."""
        text = "Look at this https://example.com/cool"
        assert len(text) <= 100
        msgs = [
            _make_text_msg(text, msg_id=1),
            _make_text_msg("So cool!", msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is not None
        assert result["link_text"] == text

    def test_comment_with_small_url_under_30_pct(self):
        """Comment containing a URL that is <30% of text should still be detected."""
        # URL is ~24 chars, text total is ~100 chars => ~24%
        comment = (
            "This reminds me of something I read before, "
            "see also http://other.com for background context."
        )
        url_len = len("http://other.com")
        total_len = len(comment.strip())
        assert url_len / total_len < 0.3

        msgs = [
            _make_text_msg("https://example.com/article", msg_id=1),
            _make_text_msg(comment, msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is not None

    def test_link_dominant_over_70_pct(self):
        """URL chars > 70% of first message — detected."""
        # URL is ~50 chars out of ~54 total
        text = "x https://example.com/very-long-path/to/resource"
        msgs = [
            _make_text_msg(text, msg_id=1),
            _make_text_msg("thoughts?", msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is not None


# =============================================================================
# Detection: negative cases
# =============================================================================


class TestLinkCommentDetectionNegative:
    """Cases where link + comment should NOT be detected."""

    def test_single_message_rejected(self):
        msgs = [_make_text_msg("https://example.com", msg_id=1)]
        assert _detect_link_comment_pair(msgs) is None

    def test_three_messages_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1),
            _make_text_msg("comment", msg_id=2),
            _make_text_msg("more", msg_id=3),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_reply_message_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1, has_reply=True),
            _make_text_msg("comment", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_second_message_reply_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1),
            _make_text_msg("comment", msg_id=2, has_reply=True),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_command_first_message_rejected(self):
        msgs = [
            _make_text_msg("/link https://example.com", msg_id=1),
            _make_text_msg("comment", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_command_second_message_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1),
            _make_text_msg("/save this", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_non_text_first_message_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1, message_type="photo"),
            _make_text_msg("comment", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_non_text_second_message_rejected(self):
        msgs = [
            _make_text_msg("https://example.com", msg_id=1),
            _make_text_msg("comment", msg_id=2, message_type="voice"),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_first_message_no_url_rejected(self):
        msgs = [
            _make_text_msg("just some text without links", msg_id=1),
            _make_text_msg("comment", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_long_text_with_url_under_70_pct_rejected(self):
        """Long text (>100 chars) where URL is <70% — not link-dominant."""
        text = (
            "I was reading this really interesting article about machine learning "
            "and deep neural networks the other day, here is the link: "
            "https://example.com/ml"
        )
        assert len(text) > 100
        msgs = [
            _make_text_msg(text, msg_id=1),
            _make_text_msg("thoughts?", msg_id=2),
        ]
        result = _detect_link_comment_pair(msgs)
        assert result is None

    def test_comment_mostly_url_over_30_pct_rejected(self):
        """Second message where URL chars >= 30% — rejected as commentary."""
        comment = "See https://other-example.com/long-path/resource"
        msgs = [
            _make_text_msg("https://example.com", msg_id=1),
            _make_text_msg(comment, msg_id=2),
        ]
        # URL is ~48 chars out of ~52 total — way over 30%
        result = _detect_link_comment_pair(msgs)
        assert result is None

    def test_empty_text_rejected(self):
        msgs = [
            _make_text_msg("", msg_id=1),
            _make_text_msg("comment", msg_id=2),
        ]
        assert _detect_link_comment_pair(msgs) is None

    def test_none_text_rejected(self):
        msg1 = _make_text_msg("https://example.com", msg_id=1)
        msg1.text = None
        msgs = [msg1, _make_text_msg("comment", msg_id=2)]
        assert _detect_link_comment_pair(msgs) is None


# =============================================================================
# get_link_comment_context() formatting
# =============================================================================


class TestGetLinkCommentContext:
    """Test the semantic formatting method."""

    def test_formatting(self):
        combined = CombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[],
            link_comment_pair={
                "link_text": "https://example.com/article",
                "comment": "This is great",
            },
        )
        result = combined.get_link_comment_context()
        assert result == (
            "User shared link: https://example.com/article\n\n" "Comment: This is great"
        )

    def test_returns_none_when_no_pair(self):
        combined = CombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[],
        )
        assert combined.get_link_comment_context() is None
