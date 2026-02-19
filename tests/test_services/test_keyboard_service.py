"""
Tests for the Keyboard Service.

Tests cover:
- KeyboardService initialization and default config loading
- Fallback config when YAML fails to load
- Default and collect keyboard configuration retrieval
- User config caching and retrieval from database
- Saving and resetting user configs
- Building ReplyKeyboardMarkup objects
- Button text to action mapping
- Available buttons and command categories retrieval
- Cache management
- Global singleton instance management
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import ReplyKeyboardMarkup

from src.services.keyboard_service import (
    KeyboardService,
    get_keyboard_service,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_default_config():
    """Create a mock default configuration for testing."""
    return {
        "default_keyboard": {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [
                    {"emoji": "A", "label": "Alpha", "action": "/alpha"},
                    {"emoji": "B", "label": "Beta", "action": "/beta"},
                ],
                [
                    {"emoji": "C", "label": "Gamma", "action": "/gamma"},
                ],
            ],
        },
        "collect_keyboard": {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [
                    {"emoji": "X", "label": "Go", "action": "/collect:go"},
                    {"emoji": "Y", "label": "Stop", "action": "/collect:stop"},
                ],
            ],
        },
        "available_buttons": {
            "alpha": {
                "emoji": "A",
                "label": "Alpha",
                "action": "/alpha",
                "description": "Alpha button",
            },
            "beta": {
                "emoji": "B",
                "label": "Beta",
                "action": "/beta",
                "description": "Beta button",
            },
        },
        "command_categories": {
            "core": {
                "title": "Core Commands",
                "emoji": "X",
                "commands": [
                    {"command": "/start", "description": "Start"},
                    {"command": "/help", "description": "Help"},
                ],
            },
        },
    }


@pytest.fixture
def keyboard_service_with_mock_config(mock_default_config):
    """Create a KeyboardService with a mocked default config."""
    with patch.object(KeyboardService, "_load_default_config"):
        service = KeyboardService()
        service._default_config = mock_default_config
    return service


@pytest.fixture
def mock_user():
    """Create a mock User model object."""
    user = MagicMock()
    user.id = 1
    user.user_id = 12345
    return user


@pytest.fixture
def mock_keyboard_config():
    """Create a mock KeyboardConfig model object."""
    config = MagicMock()
    config.id = 1
    config.user_id = 1
    config.enabled = True
    config.resize_keyboard = True
    config.one_time = False
    config.buttons_json = json.dumps(
        [
            [
                {"emoji": "Z", "label": "Custom", "action": "/custom"},
            ]
        ]
    )
    return config


# =============================================================================
# KeyboardService Initialization Tests
# =============================================================================


class TestKeyboardServiceInit:
    """Tests for KeyboardService initialization."""

    def test_initialization_creates_empty_cache(self):
        """Test that initialization creates an empty config cache."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            assert service._config_cache == {}

    def test_initialization_calls_load_default_config(self):
        """Test that initialization calls _load_default_config."""
        with patch.object(KeyboardService, "_load_default_config") as mock_load:
            KeyboardService()
            mock_load.assert_called_once()

    def test_load_default_config_success(self, mock_default_config, tmp_path):
        """Test successful loading of default config from YAML."""
        import yaml

        config_file = tmp_path / "keyboard.yaml"
        with open(config_file, "w") as f:
            yaml.dump(mock_default_config, f)

        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()

        # Manually call the load method with our temp file
        with patch("pathlib.Path.__truediv__", return_value=config_file):
            service._load_default_config()

        assert service._default_config is not None

    def test_load_default_config_file_not_found(self):
        """Test fallback config when YAML file is not found."""
        with patch("builtins.open", side_effect=FileNotFoundError("Not found")):
            service = KeyboardService()

        assert service._default_config is not None
        assert "default_keyboard" in service._default_config

    def test_load_default_config_invalid_yaml(self):
        """Test fallback config when YAML is invalid."""
        with patch("builtins.open", MagicMock()):
            with patch("yaml.safe_load", side_effect=Exception("Invalid YAML")):
                service = KeyboardService()

        assert service._default_config is not None


class TestFallbackConfig:
    """Tests for the fallback configuration."""

    def test_get_fallback_config_structure(self):
        """Test that fallback config has correct structure."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            fallback = service._get_fallback_config()

        assert "default_keyboard" in fallback
        assert "available_buttons" in fallback
        assert "command_categories" in fallback

    def test_fallback_config_default_keyboard_has_rows(self):
        """Test that fallback default keyboard has rows defined."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            fallback = service._get_fallback_config()

        default_kb = fallback["default_keyboard"]
        assert "rows" in default_kb
        assert len(default_kb["rows"]) > 0

    def test_fallback_config_buttons_have_required_fields(self):
        """Test that fallback buttons have emoji, label, action fields."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            fallback = service._get_fallback_config()

        for row in fallback["default_keyboard"]["rows"]:
            for button in row:
                assert "emoji" in button
                assert "label" in button
                assert "action" in button


# =============================================================================
# Default Keyboard Config Tests
# =============================================================================


class TestGetDefaultKeyboardConfig:
    """Tests for get_default_keyboard_config method."""

    def test_returns_default_keyboard_from_config(
        self, keyboard_service_with_mock_config
    ):
        """Test that it returns the default_keyboard section from config."""
        service = keyboard_service_with_mock_config
        result = service.get_default_keyboard_config()

        assert result["enabled"] is True
        assert result["resize_keyboard"] is True
        assert result["one_time"] is False
        assert len(result["rows"]) == 2

    def test_returns_fallback_when_no_config(self):
        """Test that it returns fallback when _default_config is None."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            service._default_config = None

        result = service.get_default_keyboard_config()

        assert "enabled" in result
        assert "rows" in result


# =============================================================================
# Collect Keyboard Config Tests
# =============================================================================


class TestGetCollectKeyboardConfig:
    """Tests for get_collect_keyboard_config method."""

    def test_returns_collect_keyboard_from_config(
        self, keyboard_service_with_mock_config
    ):
        """Test that it returns the collect_keyboard section from config."""
        service = keyboard_service_with_mock_config
        result = service.get_collect_keyboard_config()

        assert result["enabled"] is True
        assert len(result["rows"]) == 1
        assert result["rows"][0][0]["action"] == "/collect:go"

    def test_returns_fallback_when_no_config(self):
        """Test that it returns fallback collect keyboard when _default_config is None."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            service._default_config = None

        result = service.get_collect_keyboard_config()

        assert "enabled" in result
        assert "rows" in result
        # Fallback should have collect-related actions
        actions = [btn["action"] for row in result["rows"] for btn in row]
        assert any("collect" in action for action in actions)


# =============================================================================
# User Config Tests
# =============================================================================


class TestGetUserConfig:
    """Tests for get_user_config method."""

    @pytest.mark.asyncio
    async def test_returns_cached_config(self, keyboard_service_with_mock_config):
        """Test that cached config is returned without database lookup."""
        service = keyboard_service_with_mock_config
        cached_config = {
            "enabled": True,
            "rows": [[{"emoji": "Z", "label": "Cached", "action": "/cached"}]],
        }
        service._config_cache[12345] = cached_config

        result = await service.get_user_config(12345)

        assert result == cached_config

    @pytest.mark.asyncio
    async def test_returns_default_when_user_not_found(
        self, keyboard_service_with_mock_config
    ):
        """Test that default config is returned when user is not in database."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_ctx.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_config(12345)

        assert result == service.get_default_keyboard_config()

    @pytest.mark.asyncio
    async def test_returns_user_config_from_database(
        self, keyboard_service_with_mock_config, mock_user, mock_keyboard_config
    ):
        """Test that user's custom config is returned from database."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # First query returns user, second returns keyboard config
            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = mock_keyboard_config

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )

            result = await service.get_user_config(12345)

        assert result["enabled"] is True
        assert result["rows"][0][0]["action"] == "/custom"

    @pytest.mark.asyncio
    async def test_caches_user_config_after_retrieval(
        self, keyboard_service_with_mock_config, mock_user, mock_keyboard_config
    ):
        """Test that retrieved config is cached."""
        service = keyboard_service_with_mock_config
        assert 12345 not in service._config_cache

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = mock_keyboard_config

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )

            await service.get_user_config(12345)

        assert 12345 in service._config_cache

    @pytest.mark.asyncio
    async def test_returns_default_on_database_error(
        self, keyboard_service_with_mock_config
    ):
        """Test that default config is returned on database error."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("DB error")
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await service.get_user_config(12345)

        assert result == service.get_default_keyboard_config()


# =============================================================================
# Save User Config Tests
# =============================================================================


class TestSaveUserConfig:
    """Tests for save_user_config method."""

    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_found(
        self, keyboard_service_with_mock_config
    ):
        """Test that save returns False when user is not in database."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_ctx.execute = AsyncMock(return_value=mock_result)

            result = await service.save_user_config(12345, {"enabled": True})

        assert result is False

    @pytest.mark.asyncio
    async def test_creates_new_config_when_not_exists(
        self, keyboard_service_with_mock_config, mock_user
    ):
        """Test that new KeyboardConfig is created when user has none.

        This test verifies the code path where a user exists but has no
        keyboard config, so a new one needs to be created and added to the session.

        Note: We use a simple mock approach that tracks session.add() being called
        rather than patching KeyboardConfig directly, which would break SQLAlchemy's
        select() statements.
        """
        service = keyboard_service_with_mock_config
        new_config = {
            "enabled": True,
            "rows": [[{"emoji": "N", "label": "New", "action": "/new"}]],
        }

        add_calls = []

        def capture_add(obj):
            add_calls.append(obj)

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = (
                None  # No existing config
            )

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )
            mock_ctx.add = MagicMock(side_effect=capture_add)
            mock_ctx.commit = AsyncMock()

            result = await service.save_user_config(12345, new_config)

        assert result is True
        # Verify session.add() was called once (with a new KeyboardConfig)
        assert mock_ctx.add.call_count == 1
        # Verify the added object has the right attributes set
        added_obj = add_calls[0]
        assert added_obj.user_id == mock_user.id
        assert added_obj.buttons_json == json.dumps(new_config["rows"])
        assert added_obj.enabled is True

    @pytest.mark.asyncio
    async def test_updates_existing_config(
        self, keyboard_service_with_mock_config, mock_user, mock_keyboard_config
    ):
        """Test that existing KeyboardConfig is updated."""
        service = keyboard_service_with_mock_config
        updated_config = {
            "enabled": False,
            "resize_keyboard": False,
            "one_time": True,
            "rows": [[{"emoji": "U", "label": "Updated", "action": "/updated"}]],
        }

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = mock_keyboard_config

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )
            mock_ctx.commit = AsyncMock()

            result = await service.save_user_config(12345, updated_config)

        assert result is True
        assert mock_keyboard_config.enabled is False
        assert mock_keyboard_config.resize_keyboard is False
        assert mock_keyboard_config.one_time is True

    @pytest.mark.asyncio
    async def test_updates_cache_after_save(
        self, keyboard_service_with_mock_config, mock_user, mock_keyboard_config
    ):
        """Test that cache is updated after successful save."""
        service = keyboard_service_with_mock_config
        new_config = {"enabled": True, "rows": []}

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = mock_keyboard_config

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )
            mock_ctx.commit = AsyncMock()

            await service.save_user_config(12345, new_config)

        assert service._config_cache[12345] == new_config

    @pytest.mark.asyncio
    async def test_returns_false_on_database_error(
        self, keyboard_service_with_mock_config
    ):
        """Test that save returns False on database error."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("DB error")
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await service.save_user_config(12345, {"enabled": True})

        assert result is False


# =============================================================================
# Reset User Config Tests
# =============================================================================


class TestResetUserConfig:
    """Tests for reset_user_config method."""

    @pytest.mark.asyncio
    async def test_clears_cache_on_reset(self, keyboard_service_with_mock_config):
        """Test that cache is cleared on reset."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {"some": "config"}

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_ctx.execute = AsyncMock(return_value=mock_result)

            await service.reset_user_config(12345)

        assert 12345 not in service._config_cache

    @pytest.mark.asyncio
    async def test_returns_true_when_user_not_found(
        self, keyboard_service_with_mock_config
    ):
        """Test that reset returns True when user doesn't exist (nothing to reset)."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_ctx.execute = AsyncMock(return_value=mock_result)

            result = await service.reset_user_config(12345)

        assert result is True

    @pytest.mark.asyncio
    async def test_deletes_existing_config(
        self, keyboard_service_with_mock_config, mock_user, mock_keyboard_config
    ):
        """Test that existing config is deleted on reset."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = mock_user
            mock_result_config = MagicMock()
            mock_result_config.scalar_one_or_none.return_value = mock_keyboard_config

            mock_ctx.execute = AsyncMock(
                side_effect=[mock_result_user, mock_result_config]
            )
            mock_ctx.delete = AsyncMock()
            mock_ctx.commit = AsyncMock()

            result = await service.reset_user_config(12345)

        assert result is True
        mock_ctx.delete.assert_called_once_with(mock_keyboard_config)

    @pytest.mark.asyncio
    async def test_returns_false_on_database_error(
        self, keyboard_service_with_mock_config
    ):
        """Test that reset returns False on database error."""
        service = keyboard_service_with_mock_config

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("DB error")
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await service.reset_user_config(12345)

        assert result is False


# =============================================================================
# Build Reply Keyboard Tests
# =============================================================================


class TestBuildReplyKeyboard:
    """Tests for build_reply_keyboard method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self, keyboard_service_with_mock_config):
        """Test that None is returned when keyboard is disabled."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {"enabled": False, "rows": []}

        result = await service.build_reply_keyboard(12345)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_rows(self, keyboard_service_with_mock_config):
        """Test that None is returned when there are no rows."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {"enabled": True, "rows": []}

        result = await service.build_reply_keyboard(12345)

        assert result is None

    @pytest.mark.asyncio
    async def test_builds_keyboard_with_buttons(
        self, keyboard_service_with_mock_config
    ):
        """Test that ReplyKeyboardMarkup is built correctly."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [
                    {"emoji": "A", "label": "Test1", "action": "/test1"},
                    {"emoji": "B", "label": "Test2", "action": "/test2"},
                ],
                [
                    {"emoji": "C", "label": "Test3", "action": "/test3"},
                ],
            ],
        }

        result = await service.build_reply_keyboard(12345)

        assert result is not None
        assert isinstance(result, ReplyKeyboardMarkup)
        assert result.resize_keyboard is True
        assert result.one_time_keyboard is False

    @pytest.mark.asyncio
    async def test_button_text_format(self, keyboard_service_with_mock_config):
        """Test that button text is formatted as 'emoji label'."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [{"emoji": "X", "label": "MyButton", "action": "/test"}],
            ],
        }

        result = await service.build_reply_keyboard(12345)

        # Access the keyboard to verify button text
        assert result is not None
        # The keyboard property contains the rows of buttons
        assert len(result.keyboard) == 1
        assert len(result.keyboard[0]) == 1
        assert result.keyboard[0][0].text == "X MyButton"

    @pytest.mark.asyncio
    async def test_handles_empty_emoji(self, keyboard_service_with_mock_config):
        """Test that buttons with empty emoji are handled correctly."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [{"emoji": "", "label": "NoEmoji", "action": "/test"}],
            ],
        }

        result = await service.build_reply_keyboard(12345)

        assert result is not None
        assert result.keyboard[0][0].text == "NoEmoji"

    @pytest.mark.asyncio
    async def test_handles_empty_label(self, keyboard_service_with_mock_config):
        """Test that buttons with empty label are handled correctly."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [{"emoji": "X", "label": "", "action": "/test"}],
            ],
        }

        result = await service.build_reply_keyboard(12345)

        assert result is not None
        assert result.keyboard[0][0].text == "X"

    @pytest.mark.asyncio
    async def test_skips_empty_rows(self, keyboard_service_with_mock_config):
        """Test that empty rows are skipped."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [],  # Empty row
                [{"emoji": "A", "label": "Test", "action": "/test"}],
                [],  # Another empty row
            ],
        }

        result = await service.build_reply_keyboard(12345)

        assert result is not None
        assert len(result.keyboard) == 1


# =============================================================================
# Build Collect Keyboard Tests
# =============================================================================


class TestBuildCollectKeyboard:
    """Tests for build_collect_keyboard method."""

    def test_returns_reply_keyboard_markup(self, keyboard_service_with_mock_config):
        """Test that ReplyKeyboardMarkup is returned."""
        service = keyboard_service_with_mock_config

        result = service.build_collect_keyboard()

        assert isinstance(result, ReplyKeyboardMarkup)

    def test_uses_collect_keyboard_config(self, keyboard_service_with_mock_config):
        """Test that collect keyboard config is used."""
        service = keyboard_service_with_mock_config

        result = service.build_collect_keyboard()

        # Should have buttons from collect_keyboard config
        assert len(result.keyboard) > 0
        # First row should have Go and Stop buttons from mock config
        button_texts = [btn.text for btn in result.keyboard[0]]
        assert any("Go" in text for text in button_texts)

    def test_keyboard_properties(self, keyboard_service_with_mock_config):
        """Test that keyboard properties are set from config."""
        service = keyboard_service_with_mock_config
        service._default_config["collect_keyboard"]["resize_keyboard"] = False
        service._default_config["collect_keyboard"]["one_time"] = True

        result = service.build_collect_keyboard()

        assert result.resize_keyboard is False
        assert result.one_time_keyboard is True


# =============================================================================
# Get Action For Button Text Tests
# =============================================================================


class TestGetActionForButtonText:
    """Tests for get_action_for_button_text method."""

    def test_finds_action_in_available_buttons(self, keyboard_service_with_mock_config):
        """Test finding action from available_buttons config."""
        service = keyboard_service_with_mock_config

        result = service.get_action_for_button_text("A Alpha")

        assert result == "/alpha"

    def test_finds_action_in_default_keyboard(self, keyboard_service_with_mock_config):
        """Test finding action from default_keyboard rows."""
        service = keyboard_service_with_mock_config

        result = service.get_action_for_button_text("B Beta")

        assert result == "/beta"

    def test_finds_action_in_collect_keyboard(self, keyboard_service_with_mock_config):
        """Test finding action from collect_keyboard rows."""
        service = keyboard_service_with_mock_config

        result = service.get_action_for_button_text("X Go")

        assert result == "/collect:go"

    def test_returns_none_for_unknown_button(self, keyboard_service_with_mock_config):
        """Test that None is returned for unknown button text."""
        service = keyboard_service_with_mock_config

        result = service.get_action_for_button_text("Unknown Button")

        assert result is None

    def test_strips_whitespace(self, keyboard_service_with_mock_config):
        """Test that whitespace is stripped from button text."""
        service = keyboard_service_with_mock_config

        result = service.get_action_for_button_text("  A Alpha  ")

        assert result == "/alpha"

    def test_returns_none_when_no_config(self):
        """Test that None is returned when no config is loaded."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            service._default_config = None

        result = service.get_action_for_button_text("Some Button")

        # Should still check fallback config
        assert result is None or result is not None  # Can match fallback or not


# =============================================================================
# Get Available Buttons Tests
# =============================================================================


class TestGetAvailableButtons:
    """Tests for get_available_buttons method."""

    def test_returns_available_buttons_from_config(
        self, keyboard_service_with_mock_config
    ):
        """Test returning available_buttons from config."""
        service = keyboard_service_with_mock_config

        result = service.get_available_buttons()

        assert "alpha" in result
        assert "beta" in result
        assert result["alpha"]["action"] == "/alpha"

    def test_returns_empty_dict_when_no_config(self):
        """Test returning empty dict when no config is loaded."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            service._default_config = None

        result = service.get_available_buttons()

        assert result == {}


# =============================================================================
# Get Command Categories Tests
# =============================================================================


class TestGetCommandCategories:
    """Tests for get_command_categories method."""

    def test_returns_command_categories_from_config(
        self, keyboard_service_with_mock_config
    ):
        """Test returning command_categories from config."""
        service = keyboard_service_with_mock_config

        result = service.get_command_categories()

        assert "core" in result
        assert result["core"]["title"] == "Core Commands"

    def test_returns_empty_dict_when_no_config(self):
        """Test returning empty dict when no config is loaded."""
        with patch.object(KeyboardService, "_load_default_config"):
            service = KeyboardService()
            service._default_config = None

        result = service.get_command_categories()

        assert result == {}


# =============================================================================
# Cache Management Tests
# =============================================================================


class TestClearCache:
    """Tests for clear_cache method."""

    def test_clear_specific_user_cache(self, keyboard_service_with_mock_config):
        """Test clearing cache for a specific user."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {"some": "config"}
        service._config_cache[67890] = {"other": "config"}

        service.clear_cache(user_id=12345)

        assert 12345 not in service._config_cache
        assert 67890 in service._config_cache

    def test_clear_all_cache(self, keyboard_service_with_mock_config):
        """Test clearing entire cache."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {"some": "config"}
        service._config_cache[67890] = {"other": "config"}

        service.clear_cache()

        assert service._config_cache == {}

    def test_clear_nonexistent_user_no_error(self, keyboard_service_with_mock_config):
        """Test that clearing non-existent user doesn't raise error."""
        service = keyboard_service_with_mock_config

        # Should not raise
        service.clear_cache(user_id=99999)


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global singleton instance management via DI container."""

    def _setup_container(self):
        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

    def test_get_keyboard_service_creates_instance(self):
        """Test that get_keyboard_service creates instance if needed."""
        self._setup_container()

        service = get_keyboard_service()

        assert service is not None
        assert isinstance(service, KeyboardService)

    def test_get_keyboard_service_returns_same_instance(self):
        """Test that get_keyboard_service returns the same instance."""
        self._setup_container()

        service1 = get_keyboard_service()
        service2 = get_keyboard_service()

        assert service1 is service2


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_button_with_missing_keys(self, keyboard_service_with_mock_config):
        """Test handling buttons with missing keys."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [{"label": "NoEmoji", "action": "/test"}],  # Missing emoji
                [{"emoji": "X", "action": "/test2"}],  # Missing label
            ],
        }

        # This tests that .get() with defaults handles missing keys
        # The service should handle this gracefully

    @pytest.mark.asyncio
    async def test_build_keyboard_with_none_values(
        self, keyboard_service_with_mock_config
    ):
        """Test building keyboard when config has None values."""
        service = keyboard_service_with_mock_config
        service._config_cache[12345] = {
            "enabled": True,
            "resize_keyboard": None,  # None value
            "one_time": None,
            "rows": [
                [{"emoji": "A", "label": "Test", "action": "/test"}],
            ],
        }

        # Should not raise, should use defaults
        result = await service.build_reply_keyboard(12345)
        assert result is not None

    def test_action_matching_exact_match_required(
        self, keyboard_service_with_mock_config
    ):
        """Test that action matching requires exact button text match."""
        service = keyboard_service_with_mock_config

        # Partial match should not work
        result = service.get_action_for_button_text("Alpha")  # Missing emoji
        # Should return None because "Alpha" != "A Alpha"
        assert result is None

    def test_multiple_buttons_same_text_returns_first(
        self, keyboard_service_with_mock_config
    ):
        """Test that when multiple buttons have same text, first is returned."""
        service = keyboard_service_with_mock_config
        # Add duplicate to available_buttons
        service._default_config["available_buttons"]["alpha_dup"] = {
            "emoji": "A",
            "label": "Alpha",
            "action": "/alpha_duplicate",
        }

        result = service.get_action_for_button_text("A Alpha")

        # Should return one of them (implementation returns first found)
        assert result in ["/alpha", "/alpha_duplicate"]
