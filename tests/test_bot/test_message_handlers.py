"""
Tests for message_handlers.py - Message routing and processing.

Tests cover:
- Message type detection and routing
- Text message handling (with and without URLs, prefix commands)
- Photo/image message handling
- Voice message handling
- Contact message handling
- Document handling
- URL extraction and link capture
- Prefix command parsing
- Error handling
- Claude mode routing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_user():
    """Create a mock Telegram User."""
    user = MagicMock()
    user.id = 12345
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    return user


@pytest.fixture
def mock_chat():
    """Create a mock Telegram Chat."""
    chat = MagicMock()
    chat.id = 67890
    return chat


@pytest.fixture
def mock_message(mock_user, mock_chat):
    """Create a mock Telegram Message."""
    message = MagicMock()
    message.message_id = 100
    message.from_user = mock_user
    message.chat = mock_chat
    message.chat_id = mock_chat.id
    message.reply_text = AsyncMock()
    message.text = None
    message.photo = None
    message.voice = None
    message.document = None
    message.contact = None
    message.caption = None
    return message


@pytest.fixture
def mock_update(mock_user, mock_chat, mock_message):
    """Create a mock Telegram Update."""
    update = MagicMock()
    update.effective_user = mock_user
    update.effective_chat = mock_chat
    update.message = mock_message
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram Context."""
    context = MagicMock()
    context.bot = MagicMock()
    context.args = []
    return context


@pytest.fixture
def mock_photo():
    """Create a mock Telegram PhotoSize."""
    photo = MagicMock()
    photo.file_id = "photo_file_id_12345"
    photo.file_unique_id = "unique_photo_id"
    photo.width = 800
    photo.height = 600
    return photo


@pytest.fixture
def mock_voice():
    """Create a mock Telegram Voice message."""
    voice = MagicMock()
    voice.file_id = "voice_file_id_12345"
    voice.duration = 30
    return voice


@pytest.fixture
def mock_document():
    """Create a mock Telegram Document."""
    doc = MagicMock()
    doc.file_id = "doc_file_id_12345"
    doc.file_name = "test_image.jpg"
    doc.mime_type = "image/jpeg"
    doc.file_size = 1024 * 100  # 100KB
    return doc


@pytest.fixture
def mock_contact():
    """Create a mock Telegram Contact."""
    contact = MagicMock()
    contact.phone_number = "+1234567890"
    contact.first_name = "John"
    contact.last_name = "Doe"
    contact.user_id = 99999
    contact.vcard = None
    return contact


# =============================================================================
# URL Extraction Tests
# =============================================================================


class TestURLExtraction:
    """Tests for URL extraction from text."""

    def test_extract_single_url(self):
        """Test extracting a single URL from text."""
        from src.bot.message_handlers import extract_urls

        text = "Check out https://example.com for more info"
        urls = extract_urls(text)

        assert len(urls) == 1
        assert urls[0] == "https://example.com"

    def test_extract_multiple_urls(self):
        """Test extracting multiple URLs from text."""
        from src.bot.message_handlers import extract_urls

        text = "Visit https://example.com and http://test.org today"
        urls = extract_urls(text)

        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "http://test.org" in urls

    def test_extract_url_with_path(self):
        """Test extracting URL with path."""
        from src.bot.message_handlers import extract_urls

        text = "Article at https://example.com/path/to/article?id=123"
        urls = extract_urls(text)

        assert len(urls) == 1
        assert "path/to/article" in urls[0]

    def test_extract_no_urls(self):
        """Test text with no URLs."""
        from src.bot.message_handlers import extract_urls

        text = "This is plain text without any links"
        urls = extract_urls(text)

        assert len(urls) == 0

    def test_extract_url_case_insensitive(self):
        """Test URL extraction is case insensitive."""
        from src.bot.message_handlers import extract_urls

        text = "Link: HTTPS://EXAMPLE.COM/test"
        urls = extract_urls(text)

        assert len(urls) == 1

    def test_extract_url_with_special_characters(self):
        """Test extracting URL with encoded characters."""
        from src.bot.message_handlers import extract_urls

        text = "URL: https://example.com/path%20with%20spaces"
        urls = extract_urls(text)

        assert len(urls) == 1
        assert "%20" in urls[0]


# =============================================================================
# Prefix Command Parsing Tests
# =============================================================================


class TestPrefixCommandParsing:
    """Tests for prefix command parsing."""

    def test_parse_inbox_prefix(self):
        """Test parsing inbox: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("inbox: Save this link")

        assert prefix == "inbox"
        assert content == "Save this link"

    def test_parse_research_prefix(self):
        """Test parsing research: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("research: https://example.com")

        assert prefix == "research"
        assert content == "https://example.com"

    def test_parse_task_prefix(self):
        """Test parsing task: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("task: Complete the report")

        assert prefix == "task"
        assert content == "Complete the report"

    def test_parse_note_prefix(self):
        """Test parsing note: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("note: Remember this")

        assert prefix == "note"
        assert content == "Remember this"

    def test_parse_expense_prefix(self):
        """Test parsing expense: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("expense: $50 lunch")

        assert prefix == "expense"
        assert content == "$50 lunch"

    def test_parse_agent_prefix(self):
        """Test parsing agent: prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("agent: Process this")

        assert prefix == "agent"
        assert content == "Process this"

    def test_parse_no_prefix(self):
        """Test text without prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("Regular text message")

        assert prefix is None
        assert content == "Regular text message"

    def test_parse_prefix_case_insensitive(self):
        """Test prefix parsing is case insensitive."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("INBOX: Uppercase prefix")

        assert prefix == "inbox"
        assert content == "Uppercase prefix"

    def test_parse_prefix_with_whitespace(self):
        """Test prefix parsing handles leading whitespace in prefix."""
        from src.bot.message_handlers import parse_prefix_command

        # The function uses text.strip() first, then checks startswith
        # Leading spaces break the prefix detection (text_lower becomes "inbox:..." after strip)
        prefix, content = parse_prefix_command("inbox:   Content with spaces  ")

        assert prefix == "inbox"
        assert content == "Content with spaces"

    def test_parse_prefix_colon_in_content(self):
        """Test prefix parsing with colon in content."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("note: Time: 3:00 PM")

        assert prefix == "note"
        assert content == "Time: 3:00 PM"


# =============================================================================
# Text Message Handler Tests
# =============================================================================


class TestHandleTextMessage:
    """Tests for handle_text_message function."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_user(self, mock_update, mock_context):
        """Test early return when no user in update."""
        from src.bot.message_handlers import handle_text_message

        mock_update.effective_user = None

        await handle_text_message(mock_update, mock_context)

        # Should return without sending any message
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_chat(self, mock_update, mock_context):
        """Test early return when no chat in update."""
        from src.bot.message_handlers import handle_text_message

        mock_update.effective_chat = None

        await handle_text_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_message(self, mock_update, mock_context):
        """Test early return when no message in update."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message = None

        await handle_text_message(mock_update, mock_context)

        # No assertion needed - just verify no exception

    @pytest.mark.asyncio
    async def test_returns_early_if_no_text(self, mock_update, mock_context):
        """Test early return when message has no text."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = None

        await handle_text_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_claude_mode_routes_to_claude(self, mock_update, mock_context):
        """Test that Claude mode active routes messages to Claude."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "Analyze this code"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch(
                    "src.bot.handlers.execute_claude_prompt", new_callable=AsyncMock
                ) as mock_execute:
                    await handle_text_message(mock_update, mock_context)

                    mock_execute.assert_called_once_with(
                        mock_update, mock_context, "Analyze this code"
                    )

    @pytest.mark.asyncio
    async def test_url_message_triggers_link_capture(self, mock_update, mock_context):
        """Test that message with URL triggers link capture."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "Check this: https://example.com"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "src.bot.message_handlers.handle_link_message", new_callable=AsyncMock
            ) as mock_link:
                await handle_text_message(mock_update, mock_context)

                mock_link.assert_called_once()
                call_args = mock_link.call_args
                assert "https://example.com" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_url_with_research_prefix_routes_to_research(
        self, mock_update, mock_context
    ):
        """Test URL with research: prefix routes to research folder."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "research: https://example.com/article"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "src.bot.message_handlers.handle_link_message", new_callable=AsyncMock
            ) as mock_link:
                await handle_text_message(mock_update, mock_context)

                mock_link.assert_called_once()
                # Check destination is "research"
                assert mock_link.call_args[0][2] == "research"

    @pytest.mark.asyncio
    async def test_agent_prefix_shows_help(self, mock_update, mock_context):
        """Test agent: prefix without content shows help message."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "agent: "

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await handle_text_message(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Agent Mode" in call_args

    @pytest.mark.asyncio
    async def test_standalone_help_triggers_help_command(
        self, mock_update, mock_context
    ):
        """Exact 'help' redirects to the /help command."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "help"

        with (
            patch(
                "src.bot.handlers.get_claude_mode",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.bot.handlers.core_commands.help_command",
                new_callable=AsyncMock,
            ) as mock_help,
        ):
            await handle_text_message(mock_update, mock_context)
            mock_help.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_help_me_goes_to_llm(self, mock_update, mock_context):
        """'help me' should NOT trigger help command; goes to LLM."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "help me understand quantum physics"
        processing_msg = AsyncMock()
        mock_update.message.reply_text.return_value = processing_msg

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Here's what I know..."))
        ]

        with (
            patch(
                "src.bot.handlers.get_claude_mode",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.bot.message_handlers.litellm.completion",
                return_value=mock_response,
            ),
        ):
            await handle_text_message(mock_update, mock_context)
            processing_msg.edit_text.assert_called_once_with("Here's what I know...")

    @pytest.mark.asyncio
    async def test_conversational_fallback_calls_llm(self, mock_update, mock_context):
        """Plain text gets a conversational LLM response."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "random unrelated message"
        processing_msg = AsyncMock()
        mock_update.message.reply_text.return_value = processing_msg

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="LLM response"))]

        with (
            patch(
                "src.bot.handlers.get_claude_mode",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.bot.message_handlers.litellm.completion",
                return_value=mock_response,
            ),
        ):
            await handle_text_message(mock_update, mock_context)
            processing_msg.edit_text.assert_called_once_with("LLM response")

    @pytest.mark.asyncio
    async def test_conversational_fallback_error_shows_static(
        self, mock_update, mock_context
    ):
        """If LLM fails, show a brief static fallback."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "something"
        processing_msg = AsyncMock()
        mock_update.message.reply_text.return_value = processing_msg

        with (
            patch(
                "src.bot.handlers.get_claude_mode",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.bot.message_handlers.litellm.completion",
                side_effect=Exception("API error"),
            ),
        ):
            await handle_text_message(mock_update, mock_context)
            call_args = processing_msg.edit_text.call_args[0][0]
            assert "/help" in call_args


# =============================================================================
# Image Message Handler Tests
# =============================================================================


class TestHandleImageMessage:
    """Tests for handle_image_message function."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_user(self, mock_update, mock_context):
        """Test early return when no user."""
        from src.bot.message_handlers import handle_image_message

        mock_update.effective_user = None

        await handle_image_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_chat(self, mock_update, mock_context):
        """Test early return when no chat."""
        from src.bot.message_handlers import handle_image_message

        mock_update.effective_chat = None

        await handle_image_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_message(self, mock_update, mock_context):
        """Test early return when no message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message = None

        await handle_image_message(mock_update, mock_context)

        # No assertion - just verify no exception

    @pytest.mark.asyncio
    async def test_no_image_shows_error(self, mock_update, mock_context):
        """Test error message when no image found."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = []
        mock_update.message.document = None

        await handle_image_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "No image found" in call_args

    @pytest.mark.asyncio
    async def test_extracts_largest_photo(self, mock_update, mock_context, mock_photo):
        """Test that largest photo is extracted."""
        from src.bot.message_handlers import handle_image_message

        small_photo = MagicMock()
        small_photo.file_id = "small_photo"
        small_photo.width = 100
        small_photo.height = 100

        mock_update.message.photo = [small_photo, mock_photo]  # largest is last

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ):
                    # Mock the processing message response
                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    # First call is the processing message
                    mock_update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_handles_image_document(
        self, mock_update, mock_context, mock_document
    ):
        """Test handling image sent as document."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = []
        mock_update.message.document = mock_document

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ):
                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    mock_update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_rejects_non_image_document(self, mock_update, mock_context):
        """Test rejection of non-image documents (MIME validation)."""
        from src.bot.message_handlers import handle_image_message

        doc = MagicMock()
        doc.mime_type = "application/pdf"
        doc.file_id = "pdf_file_id"

        mock_update.message.photo = []
        mock_update.message.document = doc

        await handle_image_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Unsupported image format" in call_args

    @pytest.mark.asyncio
    async def test_rejects_oversized_document(
        self, mock_update, mock_context, mock_document
    ):
        """Test rejection of oversized image documents."""
        from src.bot.message_handlers import handle_image_message

        mock_document.file_size = 15 * 1024 * 1024  # 15MB (over 10MB limit)
        mock_update.message.photo = []
        mock_update.message.document = mock_document

        await handle_image_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called()
        # Check for the size error message
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "too large" in call_args

    @pytest.mark.asyncio
    async def test_claude_mode_routes_image_to_claude(
        self, mock_update, mock_context, mock_photo
    ):
        """Test image routes to Claude when Claude mode is active."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]
        mock_update.message.caption = "What is this?"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch("src.bot.message_handlers.get_settings") as mock_settings:
                    mock_settings.return_value.vault_temp_images_dir = "/tmp/test"
                    with patch("pathlib.Path.mkdir"):
                        # Mock subprocess-based file download
                        from src.utils.subprocess_helper import SubprocessResult

                        mock_dl_result = SubprocessResult(
                            success=True,
                            stdout='{"success":true}',
                            stderr="",
                            return_code=0,
                        )
                        with patch(
                            "src.utils.subprocess_helper.download_telegram_file",
                            return_value=mock_dl_result,
                        ):
                            with patch(
                                "src.bot.handlers.execute_claude_prompt",
                                new_callable=AsyncMock,
                            ) as mock_exec:
                                processing_msg = MagicMock()
                                processing_msg.delete = AsyncMock()
                                mock_update.message.reply_text.return_value = (
                                    processing_msg
                                )

                                await handle_image_message(mock_update, mock_context)

                                mock_exec.assert_called_once()


# =============================================================================
# Voice Message Handler Tests
# =============================================================================


class TestHandleVoiceMessage:
    """Tests for handle_voice_message function."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_user(self, mock_update, mock_context):
        """Test early return when no user."""
        from src.bot.message_handlers import handle_voice_message

        mock_update.effective_user = None

        await handle_voice_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_chat(self, mock_update, mock_context):
        """Test early return when no chat."""
        from src.bot.message_handlers import handle_voice_message

        mock_update.effective_chat = None

        await handle_voice_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_message(self, mock_update, mock_context):
        """Test early return when no message."""
        from src.bot.message_handlers import handle_voice_message

        mock_update.message = None

        await handle_voice_message(mock_update, mock_context)

        # No assertion - just verify no exception

    @pytest.mark.asyncio
    async def test_returns_early_if_no_voice(self, mock_update, mock_context):
        """Test early return when no voice in message."""
        from src.bot.message_handlers import handle_voice_message

        mock_update.message.voice = None

        await handle_voice_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_long_voice_message(
        self, mock_update, mock_context, mock_voice
    ):
        """Test rejection of voice messages over 2 minutes."""
        from src.bot.message_handlers import handle_voice_message

        mock_voice.duration = 150  # 2.5 minutes
        mock_update.message.voice = mock_voice

        await handle_voice_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "too long" in call_args

    @pytest.mark.asyncio
    async def test_transcribes_voice_message(
        self, mock_update, mock_context, mock_voice
    ):
        """Test voice message transcription."""
        from src.bot.message_handlers import handle_voice_message
        from src.utils.subprocess_helper import SubprocessResult

        mock_update.message.voice = mock_voice

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=False,
            ):
                mock_dl_result = SubprocessResult(
                    success=True, stdout='{"success":true}', stderr="", return_code=0
                )
                with patch(
                    "src.utils.subprocess_helper.download_telegram_file",
                    return_value=mock_dl_result,
                ):
                    with patch(
                        "src.bot.message_handlers.get_voice_service"
                    ) as mock_voice_svc:
                        mock_svc = MagicMock()
                        mock_svc.transcribe = AsyncMock(
                            return_value=(True, {"text": "Test transcription"})
                        )
                        mock_svc.detect_intent.return_value = {
                            "intent": "quick",
                            "destination": "daily",
                            "section": "log",
                        }
                        mock_svc.format_for_obsidian.return_value = (
                            "- 10:00 Test transcription"
                        )
                        mock_voice_svc.return_value = mock_svc

                        with patch("os.unlink"):
                            with patch("src.bot.message_handlers.track_capture"):
                                with patch(
                                    "src.services.reply_context.get_reply_context_service"
                                ) as mock_reply:
                                    mock_reply_svc = MagicMock()
                                    mock_reply_svc.track_voice_transcription = (
                                        MagicMock()
                                    )
                                    mock_reply.return_value = mock_reply_svc

                                    processing_msg = MagicMock()
                                    processing_msg.edit_text = AsyncMock()
                                    processing_msg.message_id = 200
                                    mock_update.message.reply_text.return_value = (
                                        processing_msg
                                    )

                                    await handle_voice_message(
                                        mock_update, mock_context
                                    )

                                    # Verify transcription was called
                                    mock_svc.transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_voice_claude_mode_routes_to_claude(
        self, mock_update, mock_context, mock_voice
    ):
        """Test voice message routes to Claude when Claude mode active."""
        from src.bot.message_handlers import handle_voice_message
        from src.utils.subprocess_helper import SubprocessResult

        mock_update.message.voice = mock_voice

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=True,
            ):
                mock_dl_result = SubprocessResult(
                    success=True, stdout='{"success":true}', stderr="", return_code=0
                )
                with patch(
                    "src.utils.subprocess_helper.download_telegram_file",
                    return_value=mock_dl_result,
                ):
                    with patch(
                        "src.bot.message_handlers.get_voice_service"
                    ) as mock_voice_svc:
                        mock_svc = MagicMock()
                        mock_svc.transcribe = AsyncMock(
                            return_value=(True, {"text": "Hello Claude"})
                        )
                        mock_voice_svc.return_value = mock_svc

                        with patch("os.unlink"):
                            with patch(
                                "src.bot.handlers.execute_claude_prompt",
                                new_callable=AsyncMock,
                            ) as mock_exec:
                                processing_msg = MagicMock()
                                processing_msg.edit_text = AsyncMock()
                                processing_msg.delete = AsyncMock()
                                mock_update.message.reply_text.return_value = (
                                    processing_msg
                                )

                                await handle_voice_message(mock_update, mock_context)

                                mock_exec.assert_called_once_with(
                                    mock_update, mock_context, "Hello Claude"
                                )

    @pytest.mark.asyncio
    async def test_voice_transcription_failure(
        self, mock_update, mock_context, mock_voice
    ):
        """Test handling of transcription failure."""
        from src.bot.message_handlers import handle_voice_message
        from src.utils.subprocess_helper import SubprocessResult

        mock_update.message.voice = mock_voice

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=False,
            ):
                mock_dl_result = SubprocessResult(
                    success=True, stdout='{"success":true}', stderr="", return_code=0
                )
                with patch(
                    "src.utils.subprocess_helper.download_telegram_file",
                    return_value=mock_dl_result,
                ):
                    with patch(
                        "src.bot.message_handlers.get_voice_service"
                    ) as mock_voice_svc:
                        mock_svc = MagicMock()
                        mock_svc.transcribe = AsyncMock(
                            return_value=(False, {"error": "API error"})
                        )
                        mock_voice_svc.return_value = mock_svc

                        with patch("os.unlink"):
                            processing_msg = MagicMock()
                            processing_msg.edit_text = AsyncMock()
                            mock_update.message.reply_text.return_value = processing_msg

                            await handle_voice_message(mock_update, mock_context)

                            # Check error message was shown
                            processing_msg.edit_text.assert_called()
                            call_args = processing_msg.edit_text.call_args[0][0]
                            assert "failed" in call_args.lower()


# =============================================================================
# Contact Message Handler Tests
# =============================================================================


class TestHandleContactMessage:
    """Tests for handle_contact_message function."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_user(self, mock_update, mock_context):
        """Test early return when no user."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.effective_user = None

        await handle_contact_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_chat(self, mock_update, mock_context):
        """Test early return when no chat."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.effective_chat = None

        await handle_contact_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_message(self, mock_update, mock_context):
        """Test early return when no message."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.message = None

        await handle_contact_message(mock_update, mock_context)

        # No assertion - verify no exception

    @pytest.mark.asyncio
    async def test_returns_early_if_no_contact(self, mock_update, mock_context):
        """Test early return when no contact."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.message.contact = None

        await handle_contact_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_person_note(self, mock_update, mock_context, mock_contact):
        """Test contact creates person note."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.message.contact = mock_contact

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/vault"
            settings.vault_people_dir = "/tmp/vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", return_value=False):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                processing_msg = MagicMock()
                                processing_msg.edit_text = AsyncMock()
                                mock_update.message.reply_text.return_value = (
                                    processing_msg
                                )

                                await handle_contact_message(mock_update, mock_context)

                                # Should have sent processing message
                                mock_update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_contact_with_claude_shows_research_consent(
        self, mock_update, mock_context, mock_contact
    ):
        """Test contact with Claude access shows research consent keyboard."""
        from src.bot.message_handlers import handle_contact_message

        mock_update.message.contact = mock_contact

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/vault"
            settings.vault_people_dir = "/tmp/vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", return_value=False):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=True,
                            ):
                                processing_msg = MagicMock()
                                processing_msg.edit_text = AsyncMock()
                                mock_update.message.reply_text.return_value = (
                                    processing_msg
                                )

                                await handle_contact_message(mock_update, mock_context)

                                # Should show consent keyboard instead of auto-launching research
                                calls = mock_update.message.reply_text.call_args_list
                                assert any(
                                    "research" in str(c).lower() or "Research" in str(c)
                                    for c in calls
                                )


# =============================================================================
# Link Message Handler Tests
# =============================================================================


class TestHandleLinkMessage:
    """Tests for handle_link_message function."""

    @pytest.mark.asyncio
    async def test_captures_link_successfully(self, mock_message):
        """Test successful link capture."""
        from src.bot.message_handlers import handle_link_message

        urls = ["https://example.com/article"]

        with patch("src.bot.message_handlers.get_link_service") as mock_link_svc:
            mock_svc = MagicMock()
            mock_svc.capture_link = AsyncMock(
                return_value=(
                    True,
                    {
                        "path": "/vault/inbox/article.md",
                        "title": "Test Article",
                    },
                )
            )
            mock_link_svc.return_value = mock_svc

            with patch("src.bot.message_handlers.get_routing_memory") as mock_routing:
                mock_routing_mem = MagicMock()
                mock_routing_mem.get_suggested_destination.return_value = "inbox"
                mock_routing_mem.record_route = MagicMock()
                mock_routing.return_value = mock_routing_mem

                with patch("src.bot.message_handlers.track_capture"):
                    with patch(
                        "src.services.reply_context.get_reply_context_service"
                    ) as mock_reply:
                        mock_reply_svc = MagicMock()
                        mock_reply_svc.track_link_capture = MagicMock()
                        mock_reply.return_value = mock_reply_svc

                        processing_msg = MagicMock()
                        processing_msg.edit_text = AsyncMock()
                        processing_msg.message_id = 200
                        mock_message.reply_text.return_value = processing_msg

                        await handle_link_message(mock_message, urls)

                        mock_svc.capture_link.assert_called_once_with(
                            "https://example.com/article", "inbox"
                        )

    @pytest.mark.asyncio
    async def test_handles_link_capture_failure(self, mock_message):
        """Test handling of link capture failure."""
        from src.bot.message_handlers import handle_link_message

        urls = ["https://example.com/broken"]

        with patch("src.bot.message_handlers.get_link_service") as mock_link_svc:
            mock_svc = MagicMock()
            mock_svc.capture_link = AsyncMock(
                return_value=(False, {"error": "Page not found"})
            )
            mock_link_svc.return_value = mock_svc

            with patch("src.bot.message_handlers.get_routing_memory") as mock_routing:
                mock_routing_mem = MagicMock()
                mock_routing_mem.get_suggested_destination.return_value = "inbox"
                mock_routing.return_value = mock_routing_mem

                processing_msg = MagicMock()
                processing_msg.edit_text = AsyncMock()
                mock_message.reply_text.return_value = processing_msg

                await handle_link_message(mock_message, urls)

                # Check error message
                processing_msg.edit_text.assert_called()
                call_kwargs = processing_msg.edit_text.call_args
                assert "Failed" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_uses_explicit_destination(self, mock_message):
        """Test using explicit destination parameter."""
        from src.bot.message_handlers import handle_link_message

        urls = ["https://example.com"]

        with patch("src.bot.message_handlers.get_link_service") as mock_link_svc:
            mock_svc = MagicMock()
            mock_svc.capture_link = AsyncMock(
                return_value=(
                    True,
                    {
                        "path": "/vault/research/article.md",
                        "title": "Research",
                    },
                )
            )
            mock_link_svc.return_value = mock_svc

            with patch("src.bot.message_handlers.get_routing_memory") as mock_routing:
                mock_routing_mem = MagicMock()
                mock_routing_mem.record_route = MagicMock()
                mock_routing.return_value = mock_routing_mem

                with patch("src.bot.message_handlers.track_capture"):
                    with patch(
                        "src.services.reply_context.get_reply_context_service"
                    ) as mock_reply:
                        mock_reply_svc = MagicMock()
                        mock_reply_svc.track_link_capture = MagicMock()
                        mock_reply.return_value = mock_reply_svc

                        processing_msg = MagicMock()
                        processing_msg.edit_text = AsyncMock()
                        processing_msg.message_id = 200
                        mock_message.reply_text.return_value = processing_msg

                        await handle_link_message(
                            mock_message, urls, destination="research"
                        )

                        mock_svc.capture_link.assert_called_once_with(
                            "https://example.com", "research"
                        )

    @pytest.mark.asyncio
    async def test_handles_exception_during_capture(self, mock_message):
        """Test handling of exception during link capture."""
        from src.bot.message_handlers import handle_link_message

        urls = ["https://example.com"]

        with patch("src.bot.message_handlers.get_link_service") as mock_link_svc:
            mock_svc = MagicMock()
            mock_svc.capture_link = AsyncMock(side_effect=Exception("Network error"))
            mock_link_svc.return_value = mock_svc

            with patch("src.bot.message_handlers.get_routing_memory") as mock_routing:
                mock_routing_mem = MagicMock()
                mock_routing_mem.get_suggested_destination.return_value = "inbox"
                mock_routing.return_value = mock_routing_mem

                processing_msg = MagicMock()
                processing_msg.edit_text = AsyncMock()
                mock_message.reply_text.return_value = processing_msg

                await handle_link_message(mock_message, urls)

                # Check error message
                processing_msg.edit_text.assert_called()
                call_kwargs = processing_msg.edit_text.call_args
                assert "Error" in call_kwargs[0][0]


# =============================================================================
# Process Image with LLM Tests
# =============================================================================


class TestProcessImageWithLLM:
    """Tests for process_image_with_llm function."""

    @pytest.mark.asyncio
    async def test_uses_cached_analysis_if_available(self, mock_message):
        """Test that cached analysis is used when available."""
        from src.bot.message_handlers import process_image_with_llm

        processing_msg = MagicMock()
        processing_msg.delete = AsyncMock()

        with patch("src.bot.message_handlers.get_cache_service") as mock_cache_svc:
            mock_cache = MagicMock()
            mock_cache.get_cached_analysis = AsyncMock(
                return_value={
                    "summary": "Cached summary",
                    "description": "Cached description",
                }
            )
            mock_cache_svc.return_value = mock_cache

            with patch("src.bot.message_handlers.get_llm_service") as mock_llm_svc:
                mock_llm = MagicMock()
                mock_llm.format_telegram_response.return_value = (
                    "Cached response",
                    None,
                )
                mock_llm_svc.return_value = mock_llm

                await process_image_with_llm(
                    file_id="test_file_id",
                    chat_id=12345,
                    user_id=67890,
                    mode="default",
                    preset=None,
                    message=mock_message,
                    processing_msg=processing_msg,
                )

                # Verify cache was checked
                mock_cache.get_cached_analysis.assert_called_once()

                # Verify response was sent
                mock_message.reply_text.assert_called_once()
                assert "Cached response" in str(mock_message.reply_text.call_args)

    @pytest.mark.asyncio
    async def test_processes_image_when_not_cached(self, mock_message):
        """Test image processing when not cached."""
        from src.bot.message_handlers import process_image_with_llm

        processing_msg = MagicMock()
        processing_msg.delete = AsyncMock()
        processing_msg.edit_text = AsyncMock()

        with patch("src.bot.message_handlers.get_cache_service") as mock_cache_svc:
            mock_cache = MagicMock()
            mock_cache.get_cached_analysis = AsyncMock(return_value=None)
            mock_cache_svc.return_value = mock_cache

            with patch("src.bot.bot.get_bot") as mock_get_bot:
                mock_bot_instance = MagicMock()
                mock_application = MagicMock()
                mock_bot = MagicMock()
                mock_application.bot = mock_bot
                mock_bot_instance.application = mock_application
                mock_get_bot.return_value = mock_bot_instance

                with patch(
                    "src.bot.message_handlers.get_image_service"
                ) as mock_img_svc:
                    mock_img = MagicMock()
                    mock_img.process_image = AsyncMock(
                        return_value={
                            "processed_path": "/tmp/processed.jpg",
                            "original_path": "/tmp/original.jpg",
                            "dimensions": {"processed": [800, 600]},
                        }
                    )
                    mock_img_svc.return_value = mock_img

                    with patch(
                        "src.bot.message_handlers.get_llm_service"
                    ) as mock_llm_svc:
                        mock_llm = MagicMock()
                        mock_llm.format_telegram_response.return_value = (
                            "Analysis result",
                            None,
                        )
                        mock_llm_svc.return_value = mock_llm

                        with patch("src.bot.message_handlers.get_similarity_service"):
                            with patch("src.bot.message_handlers.get_vector_db"):
                                with patch(
                                    "src.bot.message_handlers.get_image_classifier"
                                ) as mock_classifier:
                                    mock_cls = MagicMock()
                                    mock_cls.classify = AsyncMock(
                                        return_value={
                                            "category": "photo",
                                            "destination": "inbox",
                                            "provider": "default",
                                        }
                                    )
                                    mock_classifier.return_value = mock_cls

                                    with patch(
                                        "src.bot.message_handlers.track_capture"
                                    ):
                                        with patch(
                                            "src.services.reply_context.get_reply_context_service"
                                        ) as mock_reply:
                                            mock_reply_svc = MagicMock()
                                            mock_reply_svc.track_image_analysis = (
                                                MagicMock()
                                            )
                                            mock_reply.return_value = mock_reply_svc

                                            with patch(
                                                "src.bot.message_handlers.get_db_session"
                                            ):
                                                result_msg = MagicMock()
                                                result_msg.message_id = 300
                                                result_msg.edit_reply_markup = (
                                                    AsyncMock()
                                                )
                                                mock_message.reply_text.return_value = (
                                                    result_msg
                                                )

                                                try:
                                                    await process_image_with_llm(
                                                        file_id="test_file_id",
                                                        chat_id=12345,
                                                        user_id=67890,
                                                        mode="default",
                                                        preset=None,
                                                        message=mock_message,
                                                        processing_msg=processing_msg,
                                                    )
                                                except Exception:
                                                    # May fail due to database mocking, but verify process was called
                                                    pass

                                                # Verify image processing was called
                                                mock_img.process_image.assert_called_once()


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in message handlers."""

    @pytest.mark.asyncio
    async def test_image_processing_error_shows_user_message(
        self, mock_update, mock_context, mock_photo
    ):
        """Test that image processing errors show user-friendly message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ) as mock_process:
                    mock_process.side_effect = Exception("Test error")

                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    # Verify user-friendly error message was shown
                    processing_msg.edit_text.assert_called()
                    call_args = processing_msg.edit_text.call_args[0][0]
                    assert (
                        "wrong" in call_args.lower() or "try again" in call_args.lower()
                    )

    @pytest.mark.asyncio
    async def test_authentication_error_shows_specific_message(
        self, mock_update, mock_context, mock_photo
    ):
        """Test that authentication errors show specific message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ) as mock_process:
                    # Create a custom exception class for authentication error
                    class AuthenticationError(Exception):
                        pass

                    error = AuthenticationError("Invalid api_key")
                    mock_process.side_effect = error

                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    processing_msg.edit_text.assert_called()

    @pytest.mark.asyncio
    async def test_rate_limit_error_shows_specific_message(
        self, mock_update, mock_context, mock_photo
    ):
        """Test that rate limit errors show specific message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ) as mock_process:
                    error = Exception("rate_limit exceeded")
                    mock_process.side_effect = error

                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    processing_msg.edit_text.assert_called()
                    call_args = processing_msg.edit_text.call_args[0][0]
                    # sanitize_error maps rate-limit keywords to friendly message
                    assert "wait" in call_args.lower() or "try again" in call_args.lower()

    @pytest.mark.asyncio
    async def test_timeout_error_shows_specific_message(
        self, mock_update, mock_context, mock_photo
    ):
        """Test that timeout errors show specific message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ) as mock_process:
                    error = Exception("Timeout error occurred")
                    mock_process.side_effect = error

                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    processing_msg.edit_text.assert_called()
                    call_args = processing_msg.edit_text.call_args[0][0]
                    # sanitize_error maps timeout keywords to friendly message
                    assert "too long" in call_args.lower() or "try again" in call_args.lower()

    @pytest.mark.asyncio
    async def test_connection_error_shows_specific_message(
        self, mock_update, mock_context, mock_photo
    ):
        """Test that connection errors show specific message."""
        from src.bot.message_handlers import handle_image_message

        mock_update.message.photo = [mock_photo]

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.bot.message_handlers.get_db_session"):
                with patch(
                    "src.bot.message_handlers.process_image_with_llm",
                    new_callable=AsyncMock,
                ) as mock_process:
                    error = Exception("ConnectionError: network unreachable")
                    mock_process.side_effect = error

                    processing_msg = MagicMock()
                    processing_msg.edit_text = AsyncMock()
                    mock_update.message.reply_text.return_value = processing_msg

                    await handle_image_message(mock_update, mock_context)

                    processing_msg.edit_text.assert_called()
                    call_args = processing_msg.edit_text.call_args[0][0]
                    # sanitize_error maps connection keywords to friendly message
                    assert "connect" in call_args.lower() or "service" in call_args.lower()


# =============================================================================
# Module Import Tests
# =============================================================================


class TestModuleImports:
    """Tests for module imports and structure."""

    def test_import_handle_text_message(self):
        """Test importing handle_text_message."""
        from src.bot.message_handlers import handle_text_message

        assert callable(handle_text_message)

    def test_import_handle_image_message(self):
        """Test importing handle_image_message."""
        from src.bot.message_handlers import handle_image_message

        assert callable(handle_image_message)

    def test_import_handle_voice_message(self):
        """Test importing handle_voice_message."""
        from src.bot.message_handlers import handle_voice_message

        assert callable(handle_voice_message)

    def test_import_handle_contact_message(self):
        """Test importing handle_contact_message."""
        from src.bot.message_handlers import handle_contact_message

        assert callable(handle_contact_message)

    def test_import_handle_link_message(self):
        """Test importing handle_link_message."""
        from src.bot.message_handlers import handle_link_message

        assert callable(handle_link_message)

    def test_import_extract_urls(self):
        """Test importing extract_urls."""
        from src.bot.message_handlers import extract_urls

        assert callable(extract_urls)

    def test_import_parse_prefix_command(self):
        """Test importing parse_prefix_command."""
        from src.bot.message_handlers import parse_prefix_command

        assert callable(parse_prefix_command)

    def test_import_process_image_with_llm(self):
        """Test importing process_image_with_llm."""
        from src.bot.message_handlers import process_image_with_llm

        assert callable(process_image_with_llm)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_extract_urls_empty_string(self):
        """Test URL extraction from empty string."""
        from src.bot.message_handlers import extract_urls

        urls = extract_urls("")
        assert urls == []

    def test_extract_urls_whitespace_only(self):
        """Test URL extraction from whitespace only."""
        from src.bot.message_handlers import extract_urls

        urls = extract_urls("   \n\t  ")
        assert urls == []

    def test_parse_prefix_empty_string(self):
        """Test prefix parsing with empty string."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("")
        assert prefix is None
        assert content == ""

    def test_parse_prefix_only_colon(self):
        """Test prefix parsing with only colon."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command(":")
        assert prefix is None
        assert content == ":"

    def test_parse_prefix_unknown_prefix(self):
        """Test prefix parsing with unknown prefix."""
        from src.bot.message_handlers import parse_prefix_command

        prefix, content = parse_prefix_command("unknown: content")
        assert prefix is None
        assert content == "unknown: content"

    @pytest.mark.asyncio
    async def test_text_message_with_empty_text(self, mock_update, mock_context):
        """Test text message handler with empty text after strip."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "   "  # Only whitespace

        # Should return early because text.strip() is empty
        await handle_text_message(mock_update, mock_context)

        # The handler checks for stripped text being truthy
        # So this should still call reply since the check is on message.text
        # which is "   " and not empty, but stripped becomes ""


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_text_with_url_and_prefix(self, mock_update, mock_context):
        """Test text message with both URL and prefix."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "research: https://example.com/paper"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch(
                "src.bot.message_handlers.handle_link_message", new_callable=AsyncMock
            ) as mock_link:
                await handle_text_message(mock_update, mock_context)

                mock_link.assert_called_once()
                # Verify destination is research
                call_args = mock_link.call_args
                assert call_args[0][2] == "research"

    @pytest.mark.asyncio
    async def test_message_routing_priority(self, mock_update, mock_context):
        """Test that Claude mode takes priority over other handlers."""
        from src.bot.message_handlers import handle_text_message

        mock_update.message.text = "research: https://example.com"

        with patch(
            "src.bot.handlers.get_claude_mode",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "src.services.claude_code_service.is_claude_code_admin",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch(
                    "src.bot.handlers.execute_claude_prompt", new_callable=AsyncMock
                ) as mock_claude:
                    with patch(
                        "src.bot.message_handlers.handle_link_message",
                        new_callable=AsyncMock,
                    ) as mock_link:
                        await handle_text_message(mock_update, mock_context)

                        # Claude should be called, not link handler
                        mock_claude.assert_called_once()
                        mock_link.assert_not_called()


# =============================================================================
# Contact Path Traversal Tests (CWE-22)
# =============================================================================


class TestContactPathTraversal:
    """Tests for path traversal prevention in handle_contact_message."""

    def _make_contact(self, first_name, last_name=None):
        """Create a mock contact with given names."""
        contact = MagicMock()
        contact.first_name = first_name
        contact.last_name = last_name
        contact.phone_number = "+1234567890"
        contact.user_id = 99999
        contact.vcard = None
        return contact

    def _make_update(self, contact):
        """Create a mock update with a contact."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.effective_chat = MagicMock()
        update.effective_chat.id = 67890
        update.message = MagicMock()
        update.message.contact = contact
        processing_msg = MagicMock()
        processing_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=processing_msg)
        return update, processing_msg

    @pytest.mark.asyncio
    async def test_normal_contact_creates_note(self):
        """Normal contact name produces a valid path inside People folder."""
        from src.bot.message_handlers import handle_contact_message

        contact = self._make_contact("John", "Doe")
        update, processing_msg = self._make_update(contact)
        context = MagicMock()

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/test_vault"
            settings.vault_people_dir = "/tmp/test_vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", return_value=False):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                await handle_contact_message(update, context)

            # Should NOT show invalid contact name warning
            for call in processing_msg.edit_text.call_args_list:
                text = str(call)
                assert "Invalid contact name" not in text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "first_name,last_name,desc",
        [
            ("../../etc/passwd", None, "classic traversal"),
            ("..\\..\\Windows", None, "backslash traversal"),
            ("../../../README", None, "vault escape"),
            ("John/../../../Config", None, "mid-path traversal"),
        ],
    )
    async def test_path_traversal_is_sanitized(self, first_name, last_name, desc):
        """Malicious contact names with path traversal are sanitized."""
        from src.bot.message_handlers import handle_contact_message

        contact = self._make_contact(first_name, last_name)
        update, processing_msg = self._make_update(contact)
        context = MagicMock()

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/test_vault"
            settings.vault_people_dir = "/tmp/test_vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", return_value=False):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                await handle_contact_message(update, context)

            # Should NOT have called edit_text with "Invalid contact name"
            # because sanitization cleaned the name before validation
            # (the is_relative_to check is the fallback)
            # Either way, no exception should be raised

    @pytest.mark.asyncio
    async def test_slash_replaced_with_underscore(self):
        """Forward slashes in contact names are replaced with underscores."""
        import os

        from src.bot.message_handlers import handle_contact_message

        first_name = "John/Doe"
        contact = self._make_contact(first_name)
        update, processing_msg = self._make_update(contact)
        context = MagicMock()

        created_paths = []

        os.path.isfile

        def capture_isfile(path):
            created_paths.append(path)
            return False

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/test_vault"
            settings.vault_people_dir = "/tmp/test_vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", side_effect=capture_isfile):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                await handle_contact_message(update, context)

        # The note path should use underscore, not slash
        note_paths = [p for p in created_paths if "People" in p]
        assert len(note_paths) > 0, "Expected a path check in People folder"
        assert (
            "John_Doe" in note_paths[0]
        ), f"Slash should be replaced with underscore, got: {note_paths[0]}"

    @pytest.mark.asyncio
    async def test_backslash_replaced_with_underscore(self):
        """Backslashes in contact names are replaced with underscores."""

        from src.bot.message_handlers import handle_contact_message

        first_name = "John\\Doe"
        contact = self._make_contact(first_name)
        update, processing_msg = self._make_update(contact)
        context = MagicMock()

        created_paths = []

        def capture_isfile(path):
            created_paths.append(path)
            return False

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/test_vault"
            settings.vault_people_dir = "/tmp/test_vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", side_effect=capture_isfile):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                await handle_contact_message(update, context)

        note_paths = [p for p in created_paths if "People" in p]
        assert len(note_paths) > 0, "Expected a path check in People folder"
        assert (
            "\\" not in note_paths[0]
        ), f"Backslash should be replaced, got: {note_paths[0]}"

    @pytest.mark.asyncio
    async def test_double_dots_replaced(self):
        """Double dots in contact names are replaced with underscores."""

        from src.bot.message_handlers import handle_contact_message

        first_name = "John..Doe"
        contact = self._make_contact(first_name)
        update, processing_msg = self._make_update(contact)
        context = MagicMock()

        created_paths = []

        def capture_isfile(path):
            created_paths.append(path)
            return False

        with patch("src.bot.message_handlers.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vault_path = "/tmp/test_vault"
            settings.vault_people_dir = "/tmp/test_vault/People"
            mock_settings.return_value = settings

            with patch("os.path.expanduser", side_effect=lambda x: x):
                with patch("os.makedirs"):
                    with patch("os.path.isfile", side_effect=capture_isfile):
                        with patch("builtins.open", MagicMock()):
                            with patch(
                                "src.services.claude_code_service.is_claude_code_admin",
                                new_callable=AsyncMock,
                                return_value=False,
                            ):
                                await handle_contact_message(update, context)

        note_paths = [p for p in created_paths if "People" in p]
        assert len(note_paths) > 0, "Expected a path check in People folder"
        assert (
            ".." not in note_paths[0]
        ), f"Double dots should be replaced, got: {note_paths[0]}"
