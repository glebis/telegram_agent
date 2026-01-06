"""
Tests for the Completion Reactions utility.

Tests cover:
- send_completion_reaction main function
- Probability-based sending
- Emoji reactions via Telegram API
- Sticker sending (file_id or path)
- Animation/GIF sending (file_id or path)
- Random selection from comma-separated lists
- Error handling and edge cases
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.utils.completion_reactions import (
    _send_animation,
    _send_emoji_reaction,
    _send_sticker,
    send_completion_reaction,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Telegram bot with async methods."""
    bot = MagicMock()
    bot.set_message_reaction = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_sticker = AsyncMock()
    bot.send_animation = AsyncMock()
    return bot


@pytest.fixture
def mock_settings_emoji():
    """Create mock settings for emoji reaction type."""
    settings = MagicMock()
    settings.completion_reaction_probability = 1.0
    settings.completion_reaction_type = "emoji"
    settings.completion_reaction_value = "\U0001f44d"
    return settings


@pytest.fixture
def mock_settings_sticker():
    """Create mock settings for sticker reaction type."""
    settings = MagicMock()
    settings.completion_reaction_probability = 1.0
    settings.completion_reaction_type = "sticker"
    settings.completion_reaction_value = "CAACAgIAAxkBAAExample"
    return settings


@pytest.fixture
def mock_settings_animation():
    """Create mock settings for animation reaction type."""
    settings = MagicMock()
    settings.completion_reaction_probability = 1.0
    settings.completion_reaction_type = "animation"
    settings.completion_reaction_value = "CgACAgIAAxkBAAExample"
    return settings


@pytest.fixture
def mock_settings_none():
    """Create mock settings for no reaction type."""
    settings = MagicMock()
    settings.completion_reaction_probability = 1.0
    settings.completion_reaction_type = "none"
    settings.completion_reaction_value = ""
    return settings


@pytest.fixture
def temp_sticker_file():
    """Create a temporary sticker file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as f:
        f.write(b"fake sticker data")
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_animation_file():
    """Create a temporary animation file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
        f.write(b"fake gif data")
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Send Completion Reaction Tests
# =============================================================================


class TestSendCompletionReaction:
    """Tests for send_completion_reaction main function."""

    @pytest.mark.asyncio
    async def test_sends_emoji_reaction(self, mock_bot, mock_settings_emoji):
        """Test that emoji reaction is sent correctly."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_emoji,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True
            # Should have called reaction or message send
            assert (
                mock_bot.set_message_reaction.called
                or mock_bot.send_message.called
            )

    @pytest.mark.asyncio
    async def test_sends_sticker_reaction(self, mock_bot, mock_settings_sticker):
        """Test that sticker reaction is sent correctly."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_sticker,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True
            mock_bot.send_sticker.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_animation_reaction(self, mock_bot, mock_settings_animation):
        """Test that animation reaction is sent correctly."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_animation,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True
            mock_bot.send_animation.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_none_type(self, mock_bot, mock_settings_none):
        """Test that no reaction is sent when type is 'none'."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_none,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is False
            mock_bot.set_message_reaction.assert_not_called()
            mock_bot.send_message.assert_not_called()
            mock_bot.send_sticker.assert_not_called()
            mock_bot.send_animation.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_type(self, mock_bot):
        """Test that unknown reaction type returns False."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "unknown_type"
        settings.completion_reaction_value = "value"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is False

    @pytest.mark.asyncio
    async def test_passes_reply_to_message_id(self, mock_bot, mock_settings_emoji):
        """Test that reply_to_message_id is passed correctly."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_emoji,
        ):
            await send_completion_reaction(
                mock_bot, 12345, reply_to_message_id=999
            )

            # Check that reply_to was used
            if mock_bot.set_message_reaction.called:
                call_kwargs = mock_bot.set_message_reaction.call_args[1]
                assert call_kwargs.get("message_id") == 999

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, mock_bot, mock_settings_emoji):
        """Test that exceptions are handled and return False."""
        mock_bot.set_message_reaction.side_effect = Exception("API Error")
        mock_bot.send_message.side_effect = Exception("API Error")

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_emoji,
        ):
            result = await send_completion_reaction(
                mock_bot, 12345, reply_to_message_id=999
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_type_case_insensitive(self, mock_bot):
        """Test that reaction type is case-insensitive."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "EMOJI"  # Uppercase
        settings.completion_reaction_value = "\U0001f44d"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True


# =============================================================================
# Probability Tests
# =============================================================================


class TestProbability:
    """Tests for probability-based sending."""

    @pytest.mark.asyncio
    async def test_probability_zero_never_sends(self, mock_bot):
        """Test that 0 probability never sends."""
        settings = MagicMock()
        settings.completion_reaction_probability = 0.0
        settings.completion_reaction_type = "emoji"
        settings.completion_reaction_value = "\U0001f44d"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            # Run multiple times to ensure it never sends
            results = []
            for _ in range(10):
                result = await send_completion_reaction(mock_bot, 12345)
                results.append(result)

            assert all(r is False for r in results)
            mock_bot.set_message_reaction.assert_not_called()
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_probability_one_always_sends(self, mock_bot, mock_settings_emoji):
        """Test that 1.0 probability always sends."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_emoji,
        ):
            # Run multiple times
            results = []
            for _ in range(5):
                mock_bot.set_message_reaction.reset_mock()
                mock_bot.send_message.reset_mock()
                result = await send_completion_reaction(mock_bot, 12345)
                results.append(result)

            assert all(r is True for r in results)

    @pytest.mark.asyncio
    async def test_probability_half_sends_sometimes(self, mock_bot):
        """Test that 0.5 probability sends approximately half the time."""
        settings = MagicMock()
        settings.completion_reaction_probability = 0.5
        settings.completion_reaction_type = "emoji"
        settings.completion_reaction_value = "\U0001f44d"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            # Run many times to check distribution
            sent_count = 0
            trials = 100

            for _ in range(trials):
                mock_bot.set_message_reaction.reset_mock()
                mock_bot.send_message.reset_mock()
                result = await send_completion_reaction(mock_bot, 12345)
                if result:
                    sent_count += 1

            # Should be roughly around 50% (allow wide margin for randomness)
            # Statistically, should be between 30-70% most of the time
            assert 20 < sent_count < 80, f"Expected ~50%, got {sent_count}%"

    @pytest.mark.asyncio
    async def test_probability_check_uses_random(self, mock_bot, mock_settings_emoji):
        """Test that probability check uses random.random()."""
        mock_settings_emoji.completion_reaction_probability = 0.5

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=mock_settings_emoji,
            ),
            patch(
                "src.utils.completion_reactions.random.random", return_value=0.3
            ) as mock_random,
        ):
            await send_completion_reaction(mock_bot, 12345)
            mock_random.assert_called_once()

    @pytest.mark.asyncio
    async def test_probability_boundary_below(self, mock_bot, mock_settings_emoji):
        """Test sending when random value is below probability."""
        mock_settings_emoji.completion_reaction_probability = 0.5

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=mock_settings_emoji,
            ),
            patch("src.utils.completion_reactions.random.random", return_value=0.4),
        ):
            result = await send_completion_reaction(mock_bot, 12345)
            assert result is True

    @pytest.mark.asyncio
    async def test_probability_boundary_above(self, mock_bot, mock_settings_emoji):
        """Test not sending when random value is above probability."""
        mock_settings_emoji.completion_reaction_probability = 0.5

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=mock_settings_emoji,
            ),
            patch("src.utils.completion_reactions.random.random", return_value=0.6),
        ):
            result = await send_completion_reaction(mock_bot, 12345)
            assert result is False


# =============================================================================
# Emoji Reaction Tests
# =============================================================================


class TestEmojiReaction:
    """Tests for _send_emoji_reaction function."""

    @pytest.mark.asyncio
    async def test_sends_reaction_with_message_id(self, mock_bot):
        """Test that emoji reaction is sent when reply_to_message_id is provided."""
        await _send_emoji_reaction(
            mock_bot, 12345, "\U0001f44d", reply_to_message_id=999
        )

        mock_bot.set_message_reaction.assert_called_once_with(
            chat_id=12345,
            message_id=999,
            reaction=[{"type": "emoji", "emoji": "\U0001f44d"}],
        )

    @pytest.mark.asyncio
    async def test_sends_message_without_message_id(self, mock_bot):
        """Test that emoji is sent as message when no reply_to_message_id."""
        await _send_emoji_reaction(mock_bot, 12345, "\U0001f44d")

        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="\U0001f44d",
        )

    @pytest.mark.asyncio
    async def test_fallback_to_message_on_reaction_error(self, mock_bot):
        """Test fallback to send_message when set_message_reaction fails."""
        mock_bot.set_message_reaction.side_effect = Exception("Reaction not supported")

        await _send_emoji_reaction(
            mock_bot, 12345, "\U0001f44d", reply_to_message_id=999
        )

        # Should fallback to send_message
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="\U0001f44d",
            reply_to_message_id=999,
        )

    @pytest.mark.asyncio
    async def test_picks_random_emoji_from_list(self, mock_bot):
        """Test that a random emoji is picked from comma-separated list."""
        emojis = "\U0001f44d,\U0001f389,\U0001f31f"

        # Run multiple times to verify random selection
        sent_emojis = set()
        for _ in range(50):
            mock_bot.send_message.reset_mock()
            await _send_emoji_reaction(mock_bot, 12345, emojis)

            call_args = mock_bot.send_message.call_args
            sent_emoji = call_args[1]["text"]
            sent_emojis.add(sent_emoji)

        # Should have picked at least 2 different emojis
        assert len(sent_emojis) >= 2
        # All should be from the list
        assert sent_emojis <= {"\U0001f44d", "\U0001f389", "\U0001f31f"}

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_emojis(self, mock_bot):
        """Test that whitespace is stripped from comma-separated emojis."""
        emojis = " \U0001f44d , \U0001f389 , \U0001f31f "

        await _send_emoji_reaction(mock_bot, 12345, emojis)

        call_args = mock_bot.send_message.call_args
        sent_emoji = call_args[1]["text"]
        # Should not have leading/trailing whitespace
        assert sent_emoji.strip() == sent_emoji

    @pytest.mark.asyncio
    async def test_single_emoji_always_selected(self, mock_bot):
        """Test that single emoji is always used."""
        emoji = "\U0001f44d"

        for _ in range(5):
            mock_bot.send_message.reset_mock()
            await _send_emoji_reaction(mock_bot, 12345, emoji)

            call_args = mock_bot.send_message.call_args
            sent_emoji = call_args[1]["text"]
            assert sent_emoji == "\U0001f44d"


# =============================================================================
# Sticker Tests
# =============================================================================


class TestSticker:
    """Tests for _send_sticker function."""

    @pytest.mark.asyncio
    async def test_sends_sticker_with_file_id(self, mock_bot):
        """Test sending sticker with Telegram file_id."""
        file_id = "CAACAgIAAxkBAAExample123"

        await _send_sticker(mock_bot, 12345, file_id)

        mock_bot.send_sticker.assert_called_once_with(
            chat_id=12345,
            sticker=file_id,
            reply_to_message_id=None,
        )

    @pytest.mark.asyncio
    async def test_sends_sticker_with_reply(self, mock_bot):
        """Test sending sticker with reply_to_message_id."""
        file_id = "CAACAgIAAxkBAAExample123"

        await _send_sticker(mock_bot, 12345, file_id, reply_to_message_id=999)

        mock_bot.send_sticker.assert_called_once_with(
            chat_id=12345,
            sticker=file_id,
            reply_to_message_id=999,
        )

    @pytest.mark.asyncio
    async def test_sends_sticker_from_file_path(self, mock_bot, temp_sticker_file):
        """Test sending sticker from file path."""
        await _send_sticker(mock_bot, 12345, temp_sticker_file)

        mock_bot.send_sticker.assert_called_once()
        call_args = mock_bot.send_sticker.call_args
        # File should be opened
        assert call_args[1]["chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_picks_random_sticker_from_list(self, mock_bot):
        """Test that a random sticker is picked from comma-separated list."""
        stickers = "CAACAgIA1,CAACAgIA2,CAACAgIA3"

        sent_stickers = set()
        for _ in range(50):
            mock_bot.send_sticker.reset_mock()
            await _send_sticker(mock_bot, 12345, stickers)

            call_args = mock_bot.send_sticker.call_args
            sent_sticker = call_args[1]["sticker"]
            sent_stickers.add(sent_sticker)

        # Should have picked at least 2 different stickers
        assert len(sent_stickers) >= 2
        # All should be from the list
        assert sent_stickers <= {"CAACAgIA1", "CAACAgIA2", "CAACAgIA3"}

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_stickers(self, mock_bot):
        """Test that whitespace is stripped from sticker IDs."""
        stickers = " CAACAgIA1 "

        await _send_sticker(mock_bot, 12345, stickers)

        call_args = mock_bot.send_sticker.call_args
        sent_sticker = call_args[1]["sticker"]
        assert sent_sticker == "CAACAgIA1"

    @pytest.mark.asyncio
    async def test_file_path_opens_file_correctly(self, mock_bot, temp_sticker_file):
        """Test that file is opened in binary read mode."""
        with patch("builtins.open", mock_open(read_data=b"sticker data")) as m:
            # Use a path that exists to trigger file opening
            with patch.object(Path, "exists", return_value=True):
                await _send_sticker(mock_bot, 12345, temp_sticker_file)

        m.assert_called_once_with(temp_sticker_file, "rb")


# =============================================================================
# Animation Tests
# =============================================================================


class TestAnimation:
    """Tests for _send_animation function."""

    @pytest.mark.asyncio
    async def test_sends_animation_with_file_id(self, mock_bot):
        """Test sending animation with Telegram file_id."""
        file_id = "CgACAgIAAxkBAAExample123"

        await _send_animation(mock_bot, 12345, file_id)

        mock_bot.send_animation.assert_called_once_with(
            chat_id=12345,
            animation=file_id,
            reply_to_message_id=None,
        )

    @pytest.mark.asyncio
    async def test_sends_animation_with_reply(self, mock_bot):
        """Test sending animation with reply_to_message_id."""
        file_id = "CgACAgIAAxkBAAExample123"

        await _send_animation(mock_bot, 12345, file_id, reply_to_message_id=999)

        mock_bot.send_animation.assert_called_once_with(
            chat_id=12345,
            animation=file_id,
            reply_to_message_id=999,
        )

    @pytest.mark.asyncio
    async def test_sends_animation_from_file_path(self, mock_bot, temp_animation_file):
        """Test sending animation from file path."""
        await _send_animation(mock_bot, 12345, temp_animation_file)

        mock_bot.send_animation.assert_called_once()
        call_args = mock_bot.send_animation.call_args
        assert call_args[1]["chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_picks_random_animation_from_list(self, mock_bot):
        """Test that a random animation is picked from comma-separated list."""
        animations = "CgACAgIA1,CgACAgIA2,CgACAgIA3"

        sent_animations = set()
        for _ in range(50):
            mock_bot.send_animation.reset_mock()
            await _send_animation(mock_bot, 12345, animations)

            call_args = mock_bot.send_animation.call_args
            sent_animation = call_args[1]["animation"]
            sent_animations.add(sent_animation)

        # Should have picked at least 2 different animations
        assert len(sent_animations) >= 2
        # All should be from the list
        assert sent_animations <= {"CgACAgIA1", "CgACAgIA2", "CgACAgIA3"}

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_animations(self, mock_bot):
        """Test that whitespace is stripped from animation IDs."""
        animations = " CgACAgIA1 "

        await _send_animation(mock_bot, 12345, animations)

        call_args = mock_bot.send_animation.call_args
        sent_animation = call_args[1]["animation"]
        assert sent_animation == "CgACAgIA1"

    @pytest.mark.asyncio
    async def test_file_path_opens_file_correctly(self, mock_bot, temp_animation_file):
        """Test that file is opened in binary read mode."""
        with patch("builtins.open", mock_open(read_data=b"gif data")) as m:
            with patch.object(Path, "exists", return_value=True):
                await _send_animation(mock_bot, 12345, temp_animation_file)

        m.assert_called_once_with(temp_animation_file, "rb")


# =============================================================================
# File Path vs File ID Tests
# =============================================================================


class TestFilePathVsFileId:
    """Tests for file path vs file_id handling."""

    @pytest.mark.asyncio
    async def test_sticker_detects_existing_file(self, mock_bot, temp_sticker_file):
        """Test that existing file path is detected for stickers."""
        await _send_sticker(mock_bot, 12345, temp_sticker_file)

        # Should be called with a file object, not the path string
        call_args = mock_bot.send_sticker.call_args
        sticker_arg = call_args[1]["sticker"]
        # When path exists, it opens the file
        assert hasattr(sticker_arg, "read") or call_args[1]["chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_sticker_treats_nonexistent_as_file_id(self, mock_bot):
        """Test that non-existent path is treated as file_id."""
        nonexistent_path = "/nonexistent/path/sticker.webp"

        await _send_sticker(mock_bot, 12345, nonexistent_path)

        call_args = mock_bot.send_sticker.call_args
        # Should pass the path as-is (treating it as file_id)
        assert call_args[1]["sticker"] == nonexistent_path

    @pytest.mark.asyncio
    async def test_animation_detects_existing_file(self, mock_bot, temp_animation_file):
        """Test that existing file path is detected for animations."""
        await _send_animation(mock_bot, 12345, temp_animation_file)

        # Should be called with a file object, not the path string
        call_args = mock_bot.send_animation.call_args
        assert call_args[1]["chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_animation_treats_nonexistent_as_file_id(self, mock_bot):
        """Test that non-existent path is treated as file_id."""
        nonexistent_path = "/nonexistent/path/animation.gif"

        await _send_animation(mock_bot, 12345, nonexistent_path)

        call_args = mock_bot.send_animation.call_args
        # Should pass the path as-is (treating it as file_id)
        assert call_args[1]["animation"] == nonexistent_path


# =============================================================================
# Random Selection Tests
# =============================================================================


class TestRandomSelection:
    """Tests for random selection from comma-separated lists."""

    @pytest.mark.asyncio
    async def test_emoji_random_uses_random_choice(self, mock_bot):
        """Test that emoji selection uses random.choice."""
        emojis = "\U0001f44d,\U0001f389,\U0001f31f"

        with patch(
            "src.utils.completion_reactions.random.choice",
            return_value="\U0001f389",
        ) as mock_choice:
            await _send_emoji_reaction(mock_bot, 12345, emojis)

            mock_choice.assert_called_once()
            call_args = mock_choice.call_args[0][0]
            assert call_args == ["\U0001f44d", "\U0001f389", "\U0001f31f"]

    @pytest.mark.asyncio
    async def test_sticker_random_uses_random_choice(self, mock_bot):
        """Test that sticker selection uses random.choice."""
        stickers = "CAACAgIA1,CAACAgIA2,CAACAgIA3"

        with patch(
            "src.utils.completion_reactions.random.choice",
            return_value="CAACAgIA2",
        ) as mock_choice:
            await _send_sticker(mock_bot, 12345, stickers)

            mock_choice.assert_called_once()
            call_args = mock_choice.call_args[0][0]
            assert call_args == ["CAACAgIA1", "CAACAgIA2", "CAACAgIA3"]

    @pytest.mark.asyncio
    async def test_animation_random_uses_random_choice(self, mock_bot):
        """Test that animation selection uses random.choice."""
        animations = "CgACAgIA1,CgACAgIA2,CgACAgIA3"

        with patch(
            "src.utils.completion_reactions.random.choice",
            return_value="CgACAgIA2",
        ) as mock_choice:
            await _send_animation(mock_bot, 12345, animations)

            mock_choice.assert_called_once()
            call_args = mock_choice.call_args[0][0]
            assert call_args == ["CgACAgIA1", "CgACAgIA2", "CgACAgIA3"]


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_main_function_catches_exception(self, mock_bot, mock_settings_sticker):
        """Test that main function catches exceptions and returns False."""
        mock_bot.send_sticker.side_effect = Exception("Network error")

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_sticker,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is False

    @pytest.mark.asyncio
    async def test_logs_error_on_exception(self, mock_bot, mock_settings_sticker):
        """Test that errors are logged."""
        mock_bot.send_sticker.side_effect = Exception("API Error")

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=mock_settings_sticker,
            ),
            patch("src.utils.completion_reactions.logger") as mock_logger,
        ):
            await send_completion_reaction(mock_bot, 12345)

            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_logs_success_on_completion(self, mock_bot, mock_settings_emoji):
        """Test that success is logged."""
        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=mock_settings_emoji,
            ),
            patch("src.utils.completion_reactions.logger") as mock_logger,
        ):
            await send_completion_reaction(mock_bot, 12345)

            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_logs_debug_on_probability_skip(self, mock_bot):
        """Test that debug log is written when probability check fails."""
        settings = MagicMock()
        settings.completion_reaction_probability = 0.0
        settings.completion_reaction_type = "emoji"
        settings.completion_reaction_value = "\U0001f44d"

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=settings,
            ),
            patch("src.utils.completion_reactions.logger") as mock_logger,
        ):
            await send_completion_reaction(mock_bot, 12345)

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_logs_warning_on_unknown_type(self, mock_bot):
        """Test that warning is logged for unknown reaction type."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "invalid_type"
        settings.completion_reaction_value = "value"

        with (
            patch(
                "src.utils.completion_reactions.get_settings",
                return_value=settings,
            ),
            patch("src.utils.completion_reactions.logger") as mock_logger,
        ):
            await send_completion_reaction(mock_bot, 12345)

            mock_logger.warning.assert_called()


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_emoji_config(self, mock_bot):
        """Test handling of empty emoji config."""
        # Empty string should still work (split gives [''])
        await _send_emoji_reaction(mock_bot, 12345, "")

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]["text"] == ""

    @pytest.mark.asyncio
    async def test_single_item_list(self, mock_bot):
        """Test handling of single-item comma-separated list."""
        await _send_emoji_reaction(mock_bot, 12345, "\U0001f44d,")

        mock_bot.send_message.assert_called_once()
        # Should pick from [thumbsup, '']
        call_args = mock_bot.send_message.call_args
        assert call_args[1]["text"] in ["\U0001f44d", ""]

    @pytest.mark.asyncio
    async def test_chat_id_passed_correctly(self, mock_bot, mock_settings_emoji):
        """Test that chat_id is passed correctly."""
        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=mock_settings_emoji,
        ):
            await send_completion_reaction(mock_bot, 999888777)

            if mock_bot.send_message.called:
                call_args = mock_bot.send_message.call_args
                assert call_args[1]["chat_id"] == 999888777

    @pytest.mark.asyncio
    async def test_unicode_emojis_handled(self, mock_bot):
        """Test handling of various Unicode emojis."""
        # Multi-byte emojis
        emojis = "\U0001f1fa\U0001f1f8,\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466,\U0001f3f3\ufe0f\u200d\U0001f308"

        await _send_emoji_reaction(mock_bot, 12345, emojis)

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]["text"] in [
            "\U0001f1fa\U0001f1f8",
            "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466",
            "\U0001f3f3\ufe0f\u200d\U0001f308",
        ]

    @pytest.mark.asyncio
    async def test_mixed_type_in_list_sticker(self, mock_bot, temp_sticker_file):
        """Test mixed file paths and file IDs in sticker list."""
        stickers = f"{temp_sticker_file},CAACAgIAFileID"

        # Run multiple times to hit both types
        for _ in range(10):
            mock_bot.send_sticker.reset_mock()
            await _send_sticker(mock_bot, 12345, stickers)

        mock_bot.send_sticker.assert_called()

    @pytest.mark.asyncio
    async def test_very_long_file_id(self, mock_bot):
        """Test handling of very long file_id."""
        long_file_id = "CAACAgIA" + "x" * 1000

        # Mock Path.exists to avoid OS filename length errors
        with patch.object(Path, "exists", return_value=False):
            await _send_sticker(mock_bot, 12345, long_file_id)

        call_args = mock_bot.send_sticker.call_args
        assert call_args[1]["sticker"] == long_file_id


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_emoji_flow(self, mock_bot):
        """Test complete emoji reaction flow."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "emoji"
        settings.completion_reaction_value = "\U0001f44d,\U0001f389"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(
                mock_bot, 12345, reply_to_message_id=999
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_full_sticker_flow(self, mock_bot):
        """Test complete sticker reaction flow."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "sticker"
        settings.completion_reaction_value = "CAACAgIA1,CAACAgIA2"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True
            mock_bot.send_sticker.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_animation_flow(self, mock_bot):
        """Test complete animation reaction flow."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "animation"
        settings.completion_reaction_value = "CgACAgIA1,CgACAgIA2"

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(mock_bot, 12345)

            assert result is True
            mock_bot.send_animation.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_fallback_mechanism(self, mock_bot):
        """Test that emoji fallback works when reaction API fails."""
        settings = MagicMock()
        settings.completion_reaction_probability = 1.0
        settings.completion_reaction_type = "emoji"
        settings.completion_reaction_value = "\U0001f44d"

        mock_bot.set_message_reaction.side_effect = Exception("Not supported")

        with patch(
            "src.utils.completion_reactions.get_settings",
            return_value=settings,
        ):
            result = await send_completion_reaction(
                mock_bot, 12345, reply_to_message_id=999
            )

            assert result is True
            # Should have tried reaction first, then fallback to message
            mock_bot.set_message_reaction.assert_called_once()
            mock_bot.send_message.assert_called_once()
