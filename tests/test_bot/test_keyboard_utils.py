"""Tests for keyboard_utils - inline keyboard building utilities"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_mode_manager():
    """Create a mock ModeManager with predefined presets"""
    mock_mm = Mock()
    mock_mm.get_mode_presets.side_effect = lambda mode: {
        "artistic": ["Critic", "Photo-coach", "Creative"],
        "formal": ["Structured", "Tags", "COCO"],
        "default": [],
    }.get(mode, [])
    return mock_mm


@pytest.fixture
def mock_callback_manager():
    """Create a mock CallbackDataManager"""
    mock_cm = Mock()
    mock_cm.create_callback_data.side_effect = (
        lambda action, file_id, mode, preset=None:
        f"{action}:{file_id[:8]}:{mode}:{preset or ''}"
    )
    return mock_cm


@pytest.fixture
def keyboard_utils_instance(mock_mode_manager, mock_callback_manager):
    """Create a KeyboardUtils instance with mocked dependencies"""
    with patch("src.bot.keyboard_utils.ModeManager", return_value=mock_mode_manager):
        with patch("src.bot.keyboard_utils.get_callback_data_manager", return_value=mock_callback_manager):
            from src.bot.keyboard_utils import KeyboardUtils
            instance = KeyboardUtils()
            instance.mode_manager = mock_mode_manager
            instance.callback_manager = mock_callback_manager
            return instance


@pytest.fixture
def sample_sessions():
    """Create sample Claude sessions for testing"""
    sessions = []
    for i in range(3):
        session = Mock()
        session.session_id = f"session-{i:08d}-abcd-efgh-ijkl-mnopqrstuvwx"
        session.last_prompt = f"Test prompt number {i}"
        sessions.append(session)
    return sessions


@pytest.fixture
def sample_images():
    """Create sample image data for gallery testing"""
    return [
        {"id": 1, "file_path": "/path/to/image1.jpg", "analysis": "Test analysis 1"},
        {"id": 2, "file_path": "/path/to/image2.jpg", "analysis": "Test analysis 2"},
        {"id": 3, "file_path": "/path/to/image3.jpg", "analysis": "Test analysis 3"},
    ]


# ============================================================================
# Tests for parse_callback_data
# ============================================================================


class TestParseCallbackData:
    """Test callback data parsing utilities"""

    def test_parse_simple_callback_data(self, keyboard_utils_instance):
        """Test parsing simple callback data with action and params"""
        action, params = keyboard_utils_instance.parse_callback_data("mode:artistic:Critic")

        assert action == "mode"
        assert params == ["artistic", "Critic"]

    def test_parse_callback_data_single_param(self, keyboard_utils_instance):
        """Test parsing callback data with single parameter"""
        action, params = keyboard_utils_instance.parse_callback_data("gallery:menu")

        assert action == "gallery"
        assert params == ["menu"]

    def test_parse_callback_data_no_params(self, keyboard_utils_instance):
        """Test parsing callback data without parameters"""
        action, params = keyboard_utils_instance.parse_callback_data("cancel")

        assert action == "cancel"
        assert params == []

    def test_parse_callback_data_multiple_colons(self, keyboard_utils_instance):
        """Test parsing callback data with multiple colons (like URLs)"""
        action, params = keyboard_utils_instance.parse_callback_data(
            "route:inbox:https://example.com"
        )

        assert action == "route"
        assert params[0] == "inbox"
        # URL gets split on colons
        assert len(params) >= 2

    def test_parse_callback_data_empty_params(self, keyboard_utils_instance):
        """Test parsing callback data with trailing colon"""
        action, params = keyboard_utils_instance.parse_callback_data("mode:default:")

        assert action == "mode"
        assert "default" in params

    def test_parse_reanalyze_callback(self, keyboard_utils_instance):
        """Test parsing reanalyze callback data"""
        action, params = keyboard_utils_instance.parse_callback_data(
            "reanalyze:abcd1234:artistic:Critic"
        )

        assert action == "reanalyze"
        assert params[0] == "abcd1234"
        assert params[1] == "artistic"
        assert params[2] == "Critic"

    def test_parse_claude_callback(self, keyboard_utils_instance):
        """Test parsing Claude action callback data"""
        action, params = keyboard_utils_instance.parse_callback_data("claude:continue")

        assert action == "claude"
        assert params == ["continue"]


# ============================================================================
# Tests for create_reanalysis_keyboard
# ============================================================================


class TestCreateReanalysisKeyboard:
    """Test reanalysis keyboard creation for image mode switching"""

    def test_default_mode_shows_artistic_presets(self, keyboard_utils_instance):
        """When in default mode, keyboard should show all artistic presets"""
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id_12345",
            current_mode="default",
            current_preset=None,
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)

        # Flatten buttons for easier inspection
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        # Should have artistic presets
        assert any("Critic" in text for text in button_texts)
        assert any("Photo-coach" in text for text in button_texts)
        assert any("Creative" in text for text in button_texts)

    def test_artistic_mode_shows_default_and_other_presets(self, keyboard_utils_instance):
        """When in artistic mode, keyboard should show default and other presets"""
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id_12345",
            current_mode="artistic",
            current_preset="Critic",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        # Should have Quick Analysis (default mode) button
        assert any("Quick Analysis" in text for text in button_texts)

        # Should have other artistic presets but NOT current one
        assert not any("Critic" in text for text in button_texts)
        assert any("Photo-coach" in text for text in button_texts)
        assert any("Creative" in text for text in button_texts)

    def test_buttons_arranged_in_rows_of_two(self, keyboard_utils_instance):
        """Buttons should be arranged in rows of max 2 buttons"""
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id_12345",
            current_mode="default",
        )

        for row in keyboard.inline_keyboard:
            assert len(row) <= 2

    def test_callback_data_format_without_local_path(self, keyboard_utils_instance):
        """Callback data should use callback manager when no local path"""
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id_12345",
            current_mode="default",
            local_image_path=None,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        # All callbacks should go through the callback manager
        for btn in all_buttons:
            assert ":" in btn.callback_data

    def test_short_local_path_included_in_callback(self, keyboard_utils_instance):
        """Short local paths should be included directly in callback data"""
        short_path = "/img/test.jpg"
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="abc123",
            current_mode="default",
            local_image_path=short_path,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        # At least one button should have the local path in callback
        has_path = any(short_path in btn.callback_data for btn in all_buttons)
        assert has_path

    def test_long_local_path_triggers_callback_manager(self, keyboard_utils_instance):
        """Long local paths should trigger callback manager to avoid 64-byte limit"""
        # Create a path that would exceed 64 bytes
        long_path = "/very/long/path/to/image/file/" + "x" * 60 + ".jpg"
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id",
            current_mode="default",
            local_image_path=long_path,
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Keyboard should still be created without error

    def test_preset_emojis_are_correct(self, keyboard_utils_instance):
        """Verify correct emojis are assigned to each preset"""
        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test_file_id",
            current_mode="default",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        for btn in all_buttons:
            if "Critic" in btn.text:
                assert btn.text.startswith("\U0001f3a8")  # Art emoji
            elif "Photo-coach" in btn.text:
                assert btn.text.startswith("\U0001f4f8")  # Camera emoji
            elif "Creative" in btn.text:
                assert btn.text.startswith("\u2728")  # Sparkles emoji


# ============================================================================
# Tests for create_mode_selection_keyboard
# ============================================================================


class TestCreateModeSelectionKeyboard:
    """Test mode selection keyboard for /mode command"""

    def test_non_default_mode_shows_default_button(self, keyboard_utils_instance):
        """When not in default mode, should show Quick Analysis button"""
        keyboard = keyboard_utils_instance.create_mode_selection_keyboard(
            current_mode="artistic",
            current_preset="Critic",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        assert any("Quick Analysis" in text for text in button_texts)

    def test_default_mode_hides_default_button(self, keyboard_utils_instance):
        """When in default mode, should not show another default button"""
        keyboard = keyboard_utils_instance.create_mode_selection_keyboard(
            current_mode="default",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        # Should only have artistic presets, no default button
        assert not any(text == "\U0001f4dd Quick Analysis" for text in button_texts)

    def test_current_preset_excluded(self, keyboard_utils_instance):
        """Current preset should be excluded from keyboard"""
        keyboard = keyboard_utils_instance.create_mode_selection_keyboard(
            current_mode="artistic",
            current_preset="Photo-coach",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        # Photo Coach button should not appear
        assert not any("Photo Coach" in text and "\u2713" not in text for text in button_texts)

    def test_callback_data_format_for_mode_selection(self, keyboard_utils_instance):
        """Callback data should follow mode:mode_name:preset format"""
        keyboard = keyboard_utils_instance.create_mode_selection_keyboard(
            current_mode="default",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        for btn in all_buttons:
            assert btn.callback_data.startswith("mode:")
            parts = btn.callback_data.split(":")
            assert len(parts) >= 2


# ============================================================================
# Tests for create_comprehensive_mode_keyboard
# ============================================================================


class TestCreateComprehensiveModeKeyboard:
    """Test comprehensive mode keyboard showing all modes and presets"""

    def test_shows_all_modes(self, keyboard_utils_instance):
        """Should show default, formal, and artistic modes"""
        keyboard = keyboard_utils_instance.create_comprehensive_mode_keyboard()

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        # Should have default mode
        assert any("Quick Analysis" in text for text in button_texts)

        # Should have artistic presets
        assert any("Critic" in text for text in button_texts)
        assert any("Photo Coach" in text or "Photo-coach" in text for text in button_texts)
        assert any("Creative" in text for text in button_texts)

    def test_current_mode_marked_with_checkmark(self, keyboard_utils_instance):
        """Current mode/preset should be marked with checkmark"""
        keyboard = keyboard_utils_instance.create_comprehensive_mode_keyboard(
            current_mode="default",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        default_button = next(
            (btn for btn in all_buttons if "Quick Analysis" in btn.text), None
        )
        assert default_button is not None
        assert "\u2713" in default_button.text

    def test_current_preset_marked_with_checkmark(self, keyboard_utils_instance):
        """Current preset should be marked with checkmark"""
        keyboard = keyboard_utils_instance.create_comprehensive_mode_keyboard(
            current_mode="artistic",
            current_preset="Critic",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        critic_button = next(
            (btn for btn in all_buttons if "Critic" in btn.text), None
        )
        assert critic_button is not None
        assert "\u2713" in critic_button.text

    def test_buttons_arranged_in_rows_of_two(self, keyboard_utils_instance):
        """Buttons should be arranged in rows of max 2"""
        keyboard = keyboard_utils_instance.create_comprehensive_mode_keyboard()

        for row in keyboard.inline_keyboard:
            assert len(row) <= 2


# ============================================================================
# Tests for create_confirmation_keyboard
# ============================================================================


class TestCreateConfirmationKeyboard:
    """Test confirmation keyboard for destructive actions"""

    def test_has_confirm_and_cancel_buttons(self, keyboard_utils_instance):
        """Should have confirm and cancel buttons"""
        keyboard = keyboard_utils_instance.create_confirmation_keyboard(
            action="delete",
            data="image_123",
        )

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

        button_texts = [btn.text for btn in keyboard.inline_keyboard[0]]
        assert any("Confirm" in text for text in button_texts)
        assert any("Cancel" in text for text in button_texts)

    def test_confirm_callback_format(self, keyboard_utils_instance):
        """Confirm button should have correct callback format"""
        keyboard = keyboard_utils_instance.create_confirmation_keyboard(
            action="delete",
            data="image_123",
        )

        confirm_btn = keyboard.inline_keyboard[0][0]
        assert confirm_btn.callback_data == "confirm:delete:image_123"

    def test_cancel_callback_format(self, keyboard_utils_instance):
        """Cancel button should have correct callback format"""
        keyboard = keyboard_utils_instance.create_confirmation_keyboard(
            action="delete",
            data="image_123",
        )

        cancel_btn = keyboard.inline_keyboard[0][1]
        assert cancel_btn.callback_data == "cancel:delete"

    def test_buttons_have_emojis(self, keyboard_utils_instance):
        """Confirm and cancel buttons should have appropriate emojis"""
        keyboard = keyboard_utils_instance.create_confirmation_keyboard(
            action="test",
            data="data",
        )

        confirm_btn = keyboard.inline_keyboard[0][0]
        cancel_btn = keyboard.inline_keyboard[0][1]

        assert "\u2705" in confirm_btn.text  # Checkmark
        assert "\u274c" in cancel_btn.text  # X


# ============================================================================
# Tests for create_gallery_navigation_keyboard
# ============================================================================


class TestCreateGalleryNavigationKeyboard:
    """Test gallery navigation keyboard creation"""

    def test_first_page_no_previous_button(self, keyboard_utils_instance, sample_images):
        """First page should not have previous button"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=1,
            total_pages=5,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        # Should not have previous page
        assert not any("page:0" in cd for cd in callback_data)
        # Should have next page
        assert any("page:2" in cd for cd in callback_data)

    def test_last_page_no_next_button(self, keyboard_utils_instance, sample_images):
        """Last page should not have next button"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=5,
            total_pages=5,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        # Should have previous page
        assert any("page:4" in cd for cd in callback_data)
        # Should not have next page
        assert not any("page:6" in cd for cd in callback_data)

    def test_middle_page_has_both_navigation_buttons(self, keyboard_utils_instance, sample_images):
        """Middle page should have both previous and next buttons"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=3,
            total_pages=5,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("page:2" in cd for cd in callback_data)
        assert any("page:4" in cd for cd in callback_data)

    def test_has_page_indicator(self, keyboard_utils_instance, sample_images):
        """Should have page indicator showing current/total"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=2,
            total_pages=5,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        assert any("2/5" in text for text in button_texts)

    def test_has_main_menu_button(self, keyboard_utils_instance, sample_images):
        """Should have main menu button"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=1,
            total_pages=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("gallery:menu" in cd for cd in callback_data)

    def test_image_view_buttons_created(self, keyboard_utils_instance, sample_images):
        """Should create view buttons for each image"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=1,
            total_pages=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        # Should have view buttons for each image
        assert any("gallery:view:1" in cd for cd in callback_data)
        assert any("gallery:view:2" in cd for cd in callback_data)
        assert any("gallery:view:3" in cd for cd in callback_data)

    def test_image_buttons_arranged_in_pairs(self, keyboard_utils_instance, sample_images):
        """Image view buttons should be arranged 2 per row"""
        keyboard = keyboard_utils_instance.create_gallery_navigation_keyboard(
            images=sample_images,
            page=1,
            total_pages=1,
        )

        # Image buttons are in the first rows (before nav row)
        image_rows = [
            row for row in keyboard.inline_keyboard
            if any("gallery:view" in btn.callback_data for btn in row)
        ]

        for row in image_rows:
            assert len(row) <= 2


# ============================================================================
# Tests for create_image_detail_keyboard
# ============================================================================


class TestCreateImageDetailKeyboard:
    """Test image detail view keyboard creation"""

    def test_default_mode_shows_artistic_options(self, keyboard_utils_instance):
        """In default mode, should show artistic preset options"""
        keyboard = keyboard_utils_instance.create_image_detail_keyboard(
            image_id=123,
            current_mode="default",
            current_preset=None,
            page=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("artistic:Critic" in cd for cd in callback_data)
        assert any("artistic:Photo-coach" in cd for cd in callback_data)
        assert any("artistic:Creative" in cd for cd in callback_data)

    def test_artistic_mode_shows_default_option(self, keyboard_utils_instance):
        """In artistic mode, should show default mode option"""
        keyboard = keyboard_utils_instance.create_image_detail_keyboard(
            image_id=123,
            current_mode="artistic",
            current_preset="Critic",
            page=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        assert any("Quick Analysis" in text for text in button_texts)

    def test_current_preset_excluded(self, keyboard_utils_instance):
        """Current preset should not appear in reanalysis options"""
        keyboard = keyboard_utils_instance.create_image_detail_keyboard(
            image_id=123,
            current_mode="artistic",
            current_preset="Photo-coach",
            page=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        # Photo-coach should not be in reanalyze options
        assert not any(
            "gallery:reanalyze" in cd and "Photo-coach" in cd
            for cd in callback_data
        )

    def test_has_back_to_gallery_button(self, keyboard_utils_instance):
        """Should have back to gallery button with correct page"""
        keyboard = keyboard_utils_instance.create_image_detail_keyboard(
            image_id=123,
            current_mode="default",
            current_preset=None,
            page=3,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("gallery:page:3" in cd for cd in callback_data)

    def test_has_main_menu_button(self, keyboard_utils_instance):
        """Should have main menu button"""
        keyboard = keyboard_utils_instance.create_image_detail_keyboard(
            image_id=123,
            current_mode="default",
            current_preset=None,
            page=1,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("gallery:menu" in cd for cd in callback_data)


# ============================================================================
# Tests for create_simple_keyboard
# ============================================================================


class TestCreateSimpleKeyboard:
    """Test simple keyboard creation from tuples"""

    def test_creates_keyboard_from_tuples(self):
        """Should create keyboard from (text, callback_data) tuples"""
        from src.bot.keyboard_utils import KeyboardUtils

        buttons_data = [
            ("Button 1", "action:1"),
            ("Button 2", "action:2"),
            ("Button 3", "action:3"),
        ]

        keyboard = KeyboardUtils.create_simple_keyboard(buttons_data)

        assert isinstance(keyboard, InlineKeyboardMarkup)
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 3

    def test_default_max_per_row_is_two(self):
        """Default max_per_row should be 2"""
        from src.bot.keyboard_utils import KeyboardUtils

        buttons_data = [
            ("Button 1", "action:1"),
            ("Button 2", "action:2"),
            ("Button 3", "action:3"),
            ("Button 4", "action:4"),
        ]

        keyboard = KeyboardUtils.create_simple_keyboard(buttons_data)

        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2

    def test_custom_max_per_row(self):
        """Should respect custom max_per_row parameter"""
        from src.bot.keyboard_utils import KeyboardUtils

        buttons_data = [
            ("B1", "1"), ("B2", "2"), ("B3", "3"),
            ("B4", "4"), ("B5", "5"), ("B6", "6"),
        ]

        keyboard = KeyboardUtils.create_simple_keyboard(buttons_data, max_per_row=3)

        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 3
        assert len(keyboard.inline_keyboard[1]) == 3

    def test_single_button(self):
        """Should handle single button"""
        from src.bot.keyboard_utils import KeyboardUtils

        buttons_data = [("Single", "single:action")]

        keyboard = KeyboardUtils.create_simple_keyboard(buttons_data)

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1

    def test_empty_buttons_list(self):
        """Should handle empty buttons list"""
        from src.bot.keyboard_utils import KeyboardUtils

        keyboard = KeyboardUtils.create_simple_keyboard([])

        assert len(keyboard.inline_keyboard) == 0


# ============================================================================
# Tests for Claude-related keyboards
# ============================================================================


class TestClaudeActionKeyboard:
    """Test Claude action keyboard creation"""

    def test_locked_mode_shows_unlock_and_new(self, keyboard_utils_instance):
        """When locked, should show unlock and new session buttons"""
        keyboard = keyboard_utils_instance.create_claude_action_keyboard(
            is_locked=True,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:unlock" in cd for cd in callback_data)
        assert any("claude:new" in cd for cd in callback_data)

    def test_active_session_shows_continue_and_end(self, keyboard_utils_instance):
        """With active session, should show continue and end buttons"""
        keyboard = keyboard_utils_instance.create_claude_action_keyboard(
            has_active_session=True,
            session_id="test-session-123",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:continue" in cd for cd in callback_data)
        assert any("claude:end" in cd for cd in callback_data)
        assert any("claude:new" in cd for cd in callback_data)
        assert any("claude:list" in cd for cd in callback_data)

    def test_no_session_shows_new_and_history(self, keyboard_utils_instance):
        """Without session, should show new and history buttons"""
        keyboard = keyboard_utils_instance.create_claude_action_keyboard(
            has_active_session=False,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:new" in cd for cd in callback_data)
        assert any("claude:list" in cd for cd in callback_data)


class TestClaudeProcessingKeyboard:
    """Test Claude processing keyboard"""

    def test_has_stop_button(self, keyboard_utils_instance):
        """Should have stop button during processing"""
        keyboard = keyboard_utils_instance.create_claude_processing_keyboard()

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1

        stop_btn = keyboard.inline_keyboard[0][0]
        assert "Stop" in stop_btn.text
        assert stop_btn.callback_data == "claude:stop"


class TestClaudeCompleteKeyboard:
    """Test Claude completion keyboard"""

    def test_has_action_buttons(self, keyboard_utils_instance):
        """Should have retry, more, and new buttons"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard()

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:retry" in cd for cd in callback_data)
        assert any("claude:continue" in cd for cd in callback_data)
        assert any("claude:new" in cd for cd in callback_data)

    def test_has_model_selection_buttons(self, keyboard_utils_instance):
        """Should have model selection buttons"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard()

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:model:haiku" in cd for cd in callback_data)
        assert any("claude:model:sonnet" in cd for cd in callback_data)
        assert any("claude:model:opus" in cd for cd in callback_data)

    def test_current_model_marked(self, keyboard_utils_instance):
        """Current model should be marked with checkmark"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            current_model="opus",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        opus_btn = next(
            (btn for btn in all_buttons if "claude:model:opus" in btn.callback_data),
            None,
        )
        assert opus_btn is not None
        assert "\u2713" in opus_btn.text

    def test_locked_shows_unlock_button(self, keyboard_utils_instance):
        """When locked, should show unlock button"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            is_locked=True,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:unlock" in cd for cd in callback_data)

    def test_unlocked_shows_lock_button(self, keyboard_utils_instance):
        """When unlocked, should show lock button"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            is_locked=False,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:lock" in cd for cd in callback_data)

    def test_voice_url_adds_button(self, keyboard_utils_instance):
        """Voice URL should add continue with voice button"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            voice_url="https://voice.example.com/session123",
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        voice_btn = next(
            (btn for btn in all_buttons if "Voice" in btn.text),
            None,
        )
        assert voice_btn is not None
        assert voice_btn.url == "https://voice.example.com/session123"

    def test_note_paths_add_view_buttons(self, keyboard_utils_instance):
        """Note paths should add view buttons"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            note_paths=["Research/note1.md", "Projects/note2.md"],
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("note:view:Research/note1.md" in cd for cd in callback_data)
        assert any("note:view:Projects/note2.md" in cd for cd in callback_data)

    def test_note_paths_limited_to_three(self, keyboard_utils_instance):
        """Should limit note view buttons to 3"""
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            note_paths=[
                "note1.md", "note2.md", "note3.md",
                "note4.md", "note5.md",
            ],
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        note_buttons = [btn for btn in all_buttons if "note:view" in btn.callback_data]

        assert len(note_buttons) == 3

    def test_long_note_names_truncated(self, keyboard_utils_instance):
        """Long note names should be truncated in button text"""
        long_name = "A" * 50 + ".md"
        keyboard = keyboard_utils_instance.create_claude_complete_keyboard(
            note_paths=[f"folder/{long_name}"],
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        note_btn = next(
            (btn for btn in all_buttons if "note:view" in btn.callback_data),
            None,
        )

        assert note_btn is not None
        # Text should be truncated (check it's reasonably short)
        assert len(note_btn.text) < 35  # Emoji + truncated name


class TestClaudeLockedKeyboard:
    """Test Claude locked mode keyboard"""

    def test_has_unlock_and_new_buttons(self, keyboard_utils_instance):
        """Should have unlock and new session buttons"""
        keyboard = keyboard_utils_instance.create_claude_locked_keyboard()

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

        callback_data = [btn.callback_data for btn in keyboard.inline_keyboard[0]]
        assert "claude:unlock" in callback_data
        assert "claude:new" in callback_data


class TestClaudeSessionsKeyboard:
    """Test Claude sessions list keyboard"""

    def test_shows_up_to_five_sessions(self, keyboard_utils_instance, sample_sessions):
        """Should show up to 5 sessions"""
        # Create 7 sessions
        sessions = sample_sessions * 3  # 9 sessions

        keyboard = keyboard_utils_instance.create_claude_sessions_keyboard(
            sessions=sessions[:7],
        )

        session_rows = [
            row for row in keyboard.inline_keyboard
            if any("claude:select" in btn.callback_data for btn in row)
        ]

        assert len(session_rows) == 5

    def test_current_session_marked(self, keyboard_utils_instance, sample_sessions):
        """Current session should have different prefix"""
        current_id = sample_sessions[1].session_id

        keyboard = keyboard_utils_instance.create_claude_sessions_keyboard(
            sessions=sample_sessions,
            current_session_id=current_id,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        # Find button for current session
        current_btn = next(
            (btn for btn in all_buttons
             if "claude:select" in btn.callback_data
             and current_id[:16] in btn.callback_data),
            None,
        )

        assert current_btn is not None
        assert current_btn.text.startswith("\u25b6\ufe0f")  # Play button

    def test_has_new_and_back_buttons(self, keyboard_utils_instance, sample_sessions):
        """Should have new and back action buttons"""
        keyboard = keyboard_utils_instance.create_claude_sessions_keyboard(
            sessions=sample_sessions,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("claude:new" in cd for cd in callback_data)
        assert any("claude:back" in cd for cd in callback_data)

    def test_session_id_truncated_in_callback(self, keyboard_utils_instance, sample_sessions):
        """Session ID in callback should be truncated to 16 chars"""
        keyboard = keyboard_utils_instance.create_claude_sessions_keyboard(
            sessions=sample_sessions,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]

        for btn in all_buttons:
            if "claude:select:" in btn.callback_data:
                session_part = btn.callback_data.split(":")[-1]
                assert len(session_part) == 16


class TestClaudeConfirmKeyboard:
    """Test Claude confirmation keyboard"""

    def test_has_confirm_and_cancel(self, keyboard_utils_instance):
        """Should have confirm and cancel buttons"""
        keyboard = keyboard_utils_instance.create_claude_confirm_keyboard(
            action="end",
        )

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

        button_texts = [btn.text for btn in keyboard.inline_keyboard[0]]
        assert "Confirm" in button_texts
        assert "Cancel" in button_texts

    def test_callback_format_with_session(self, keyboard_utils_instance):
        """Callback should include truncated session ID when provided"""
        keyboard = keyboard_utils_instance.create_claude_confirm_keyboard(
            action="delete",
            session_id="session-12345678-abcd-efgh",
        )

        confirm_btn = keyboard.inline_keyboard[0][0]
        assert "claude:confirm_delete:" in confirm_btn.callback_data
        assert "session-12345678" in confirm_btn.callback_data

    def test_callback_format_without_session(self, keyboard_utils_instance):
        """Callback should work without session ID"""
        keyboard = keyboard_utils_instance.create_claude_confirm_keyboard(
            action="clear",
        )

        confirm_btn = keyboard.inline_keyboard[0][0]
        assert confirm_btn.callback_data == "claude:confirm_clear"


# ============================================================================
# Tests for Settings keyboards
# ============================================================================


class TestSettingsKeyboard:
    """Test settings menu keyboard"""

    def test_keyboard_enabled_shows_disable_option(self, keyboard_utils_instance):
        """When keyboard enabled, should show disable option"""
        keyboard = keyboard_utils_instance.create_settings_keyboard(
            keyboard_enabled=True,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        assert any("Disable Keyboard" in text for text in button_texts)

    def test_keyboard_disabled_shows_enable_option(self, keyboard_utils_instance):
        """When keyboard disabled, should show enable option"""
        keyboard = keyboard_utils_instance.create_settings_keyboard(
            keyboard_enabled=False,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        button_texts = [btn.text for btn in all_buttons]

        assert any("Enable Keyboard" in text for text in button_texts)

    def test_has_customize_and_reset_options(self, keyboard_utils_instance):
        """Should have customize and reset options"""
        keyboard = keyboard_utils_instance.create_settings_keyboard(
            keyboard_enabled=True,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("settings:customize" in cd for cd in callback_data)
        assert any("settings:reset" in cd for cd in callback_data)


class TestKeyboardCustomizeMenu:
    """Test keyboard customization menu"""

    def test_creates_button_for_each_option(self, keyboard_utils_instance):
        """Should create button for each available button option"""
        available_buttons = {
            "gallery": {"emoji": "\U0001f5bc", "label": "Gallery", "description": "View images"},
            "mode": {"emoji": "\U0001f3a8", "label": "Mode", "description": "Change mode"},
            "help": {"emoji": "\u2753", "label": "Help", "description": "Get help"},
        }

        keyboard = keyboard_utils_instance.create_keyboard_customize_menu(
            available_buttons=available_buttons,
        )

        # Should have 3 option buttons + 1 back button
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 4

    def test_has_back_button(self, keyboard_utils_instance):
        """Should have back button"""
        keyboard = keyboard_utils_instance.create_keyboard_customize_menu(
            available_buttons={},
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data for btn in all_buttons]

        assert any("settings:back" in cd for cd in callback_data)

    def test_button_callback_format(self, keyboard_utils_instance):
        """Button callbacks should follow settings:add_btn:key format"""
        available_buttons = {
            "gallery": {"emoji": "\U0001f5bc", "label": "Gallery", "description": "View"},
        }

        keyboard = keyboard_utils_instance.create_keyboard_customize_menu(
            available_buttons=available_buttons,
        )

        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        gallery_btn = next(
            (btn for btn in all_buttons if "Gallery" in btn.text),
            None,
        )

        assert gallery_btn is not None
        assert gallery_btn.callback_data == "settings:add_btn:gallery"


# ============================================================================
# Tests for get_keyboard_utils singleton
# ============================================================================


class TestGetKeyboardUtils:
    """Test global keyboard utils instance"""

    def test_returns_keyboard_utils_instance(self):
        """Should return a KeyboardUtils instance"""
        from src.bot.keyboard_utils import get_keyboard_utils

        instance = get_keyboard_utils()

        from src.bot.keyboard_utils import KeyboardUtils
        assert isinstance(instance, KeyboardUtils)

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls (singleton)"""
        from src.bot.keyboard_utils import get_keyboard_utils

        instance1 = get_keyboard_utils()
        instance2 = get_keyboard_utils()

        assert instance1 is instance2


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_artistic_presets(self, keyboard_utils_instance):
        """Should handle empty artistic presets gracefully"""
        keyboard_utils_instance.mode_manager.get_mode_presets.return_value = []

        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test",
            current_mode="default",
        )

        # Should return valid keyboard even with no presets
        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_very_long_file_id(self, keyboard_utils_instance):
        """Should handle very long file_id values"""
        long_file_id = "A" * 200

        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id=long_file_id,
            current_mode="default",
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_special_characters_in_preset_name(self, keyboard_utils_instance):
        """Should handle special characters in preset names"""
        keyboard_utils_instance.mode_manager.get_mode_presets.return_value = [
            "Test-Preset",
            "Another_Preset",
            "Preset 123",
        ]

        keyboard = keyboard_utils_instance.create_reanalysis_keyboard(
            file_id="test",
            current_mode="default",
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) >= 3

    def test_unicode_in_button_text(self, keyboard_utils_instance):
        """Should handle unicode characters properly"""
        keyboard = keyboard_utils_instance.create_confirmation_keyboard(
            action="delete",
            data="\U0001f4f7 photo",  # Camera emoji
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_none_current_preset(self, keyboard_utils_instance):
        """Should handle None current_preset"""
        keyboard = keyboard_utils_instance.create_mode_selection_keyboard(
            current_mode="artistic",
            current_preset=None,
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # All artistic presets should be shown
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) >= 3  # Default + artistic presets
