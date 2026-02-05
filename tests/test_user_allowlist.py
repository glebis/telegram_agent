"""Tests for user allowlist feature."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.bot import TelegramBot, _parse_allowed_user_ids


class TestParseAllowedUserIds:
    """Tests for the _parse_allowed_user_ids helper."""

    def test_empty_string_returns_empty(self):
        assert _parse_allowed_user_ids("") == frozenset()

    def test_whitespace_only_returns_empty(self):
        assert _parse_allowed_user_ids("   ") == frozenset()

    def test_single_id(self):
        assert _parse_allowed_user_ids("12345") == frozenset({12345})

    def test_multiple_ids(self):
        assert _parse_allowed_user_ids("111,222,333") == frozenset({111, 222, 333})

    def test_ids_with_spaces(self):
        assert _parse_allowed_user_ids(" 111 , 222 , 333 ") == frozenset(
            {111, 222, 333}
        )

    def test_ignores_non_numeric(self):
        assert _parse_allowed_user_ids("111,abc,333") == frozenset({111, 333})

    def test_ignores_empty_segments(self):
        assert _parse_allowed_user_ids("111,,333") == frozenset({111, 333})


def _make_update(user_id: int) -> MagicMock:
    """Create a mock Update with the given user ID."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_bot(allowed_ids: str = "") -> TelegramBot:
    """Create a TelegramBot with mocked internals."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "fake:token"}):
        settings_mock = MagicMock()
        settings_mock.allowed_user_ids = allowed_ids
        with patch(
            "src.core.config.get_settings", return_value=settings_mock
        ), patch.object(TelegramBot, "_setup_application"):
            bot = TelegramBot(token="fake:token")
            bot.application = MagicMock()
            bot.application.bot = MagicMock()
            bot.application.process_update = AsyncMock()
            return bot


class TestProcessUpdateAllowlist:
    """Tests for allowlist guard in TelegramBot.process_update()."""

    @pytest.mark.asyncio
    async def test_empty_allowlist_allows_all(self):
        bot = _make_bot("")
        update = _make_update(999)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True
        bot.application.process_update.assert_awaited_once_with(update)

    @pytest.mark.asyncio
    async def test_allowlist_allows_listed_user(self):
        bot = _make_bot("111,222")
        update = _make_update(111)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True
        bot.application.process_update.assert_awaited_once_with(update)

    @pytest.mark.asyncio
    async def test_allowlist_blocks_unlisted_user(self):
        bot = _make_bot("111,222")
        update = _make_update(999)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True  # Returns True so Telegram won't retry
        bot.application.process_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_blocked_update_returns_true(self):
        """Blocked updates return True to prevent webhook retries."""
        bot = _make_bot("111")
        update = _make_update(999)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True

    @pytest.mark.asyncio
    async def test_callback_query_also_filtered(self):
        bot = _make_bot("111")
        update = _make_update(999)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True
        bot.application.process_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_callback_query_allowed_for_listed_user(self):
        bot = _make_bot("111")
        update = _make_update(111)
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True
        bot.application.process_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_without_user_is_blocked(self):
        """Updates with no effective_user are blocked when allowlist is set."""
        bot = _make_bot("111")
        update = MagicMock()
        update.effective_user = None
        with patch("src.bot.bot.Update.de_json", return_value=update):
            result = await bot.process_update({"update_id": 1})
        assert result is True
        bot.application.process_update.assert_not_awaited()
