"""
Tests for the Claude Code Service.

Tests cover:
- Stats passthrough in execute_prompt
- Session management
- Error handling
- Admin permissions
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Stats Passthrough Tests
# =============================================================================


class TestClaudeCodeServiceStatsPassthrough:
    """Tests for stats passthrough in ClaudeCodeService."""

    @pytest.mark.asyncio
    async def test_done_message_passes_stats_content(self):
        """Test that done message passes stats content through."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        stats_json = json.dumps(
            {
                "duration": "30s",
                "tool_counts": {"Read": 5},
            }
        )

        # Mock execute_claude_subprocess to yield done with stats
        async def mock_subprocess(*args, **kwargs):
            yield ("text", "Hello", None)
            yield ("done", stats_json, "test-session-123")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test prompt",
            ):
                results.append((msg_type, content, session_id))

        # Find done message and verify stats are passed through
        done_msgs = [r for r in results if r[0] == "done"]
        assert len(done_msgs) == 1
        assert done_msgs[0][1] == stats_json

        # Verify stats can be parsed
        parsed = json.loads(done_msgs[0][1])
        assert parsed["duration"] == "30s"
        assert parsed["tool_counts"]["Read"] == 5

    @pytest.mark.asyncio
    async def test_done_message_with_empty_stats(self):
        """Test done message with empty stats."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            yield ("done", "{}", "session-123")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        done_msgs = [r for r in results if r[0] == "done"]
        assert done_msgs[0][1] == "{}"

    @pytest.mark.asyncio
    async def test_done_message_with_full_stats(self):
        """Test done message with comprehensive stats."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        full_stats = {
            "duration": "2m 15s",
            "duration_seconds": 135,
            "tool_counts": {
                "Read": 10,
                "Write": 3,
                "Edit": 5,
                "Grep": 4,
                "Glob": 2,
                "Bash": 6,
            },
            "files_read": ["file1.py", "file2.py"],
            "files_written": ["output.md"],
            "web_fetches": ["https://example.com"],
            "skills_used": ["tavily-search"],
            "bash_commands": ["npm install"],
        }

        async def mock_subprocess(*args, **kwargs):
            yield ("text", "Working...", None)
            yield ("tool", "Read: file1.py", None)
            yield ("text", "Done!", None)
            yield ("done", json.dumps(full_stats), "session-456")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        done_msgs = [r for r in results if r[0] == "done"]
        parsed = json.loads(done_msgs[0][1])

        assert parsed["duration"] == "2m 15s"
        assert parsed["duration_seconds"] == 135
        assert parsed["tool_counts"]["Read"] == 10
        assert "file1.py" in parsed["files_read"]
        assert "tavily-search" in parsed["skills_used"]

    @pytest.mark.asyncio
    async def test_text_messages_still_yielded(self):
        """Test that text messages are still yielded correctly."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            yield ("text", "First message", None)
            yield ("text", "Second message", None)
            yield ("done", "{}", "session")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        text_msgs = [r for r in results if r[0] == "text"]
        assert len(text_msgs) == 2
        assert text_msgs[0][1] == "First message"
        assert text_msgs[1][1] == "Second message"

    @pytest.mark.asyncio
    async def test_tool_messages_still_yielded(self):
        """Test that tool messages are still yielded correctly."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            yield ("tool", "Read: /path/file.py", None)
            yield ("tool", "Edit: /path/file.py", None)
            yield ("done", "{}", "session")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        tool_msgs = [r for r in results if r[0] == "tool"]
        assert len(tool_msgs) == 2
        assert "Read:" in tool_msgs[0][1]
        assert "Edit:" in tool_msgs[1][1]

    @pytest.mark.asyncio
    async def test_error_messages_yielded(self):
        """Test that error messages are yielded correctly."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            yield ("error", "Something went wrong", None)

        with patch(
            "src.services.claude_code_service.execute_claude_subprocess",
            side_effect=mock_subprocess,
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        error_msgs = [r for r in results if r[0] == "error"]
        assert len(error_msgs) == 1
        assert "Something went wrong" in error_msgs[0][1]

    @pytest.mark.asyncio
    async def test_session_saved_on_done(self):
        """Test that session is saved when done message received."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            yield ("done", "{}", "new-session-id")

        with patch(
            "src.services.claude_code_service.execute_claude_subprocess",
            side_effect=mock_subprocess,
        ):
            mock_save = AsyncMock()
            service._save_session = mock_save

            results = []
            async for msg in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test prompt here",
            ):
                results.append(msg)

            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args[1]
            assert call_kwargs["chat_id"] == 123
            assert call_kwargs["user_id"] == 456
            assert call_kwargs["session_id"] == "new-session-id"

    @pytest.mark.asyncio
    async def test_active_session_updated_on_done(self):
        """Test that active_sessions dict is updated on done."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()
        service.active_sessions = {}

        async def mock_subprocess(*args, **kwargs):
            yield ("done", "{}", "active-session-123")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            async for _ in service.execute_prompt(
                chat_id=999,
                user_id=456,
                prompt="Test",
            ):
                pass

        assert service.active_sessions[999] == "active-session-123"


class TestClaudeCodeServiceOnTextCallback:
    """Tests for on_text callback in execute_prompt."""

    @pytest.mark.asyncio
    async def test_on_text_callback_called(self):
        """Test that on_text callback is called for text messages."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()
        received_texts = []

        def on_text_callback(text):
            received_texts.append(text)

        async def mock_subprocess(*args, **kwargs):
            yield ("text", "Hello", None)
            yield ("text", "World", None)
            yield ("done", "{}", "session")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            async for _ in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
                on_text=on_text_callback,
            ):
                pass

        assert len(received_texts) == 2
        assert "Hello" in received_texts
        assert "World" in received_texts

    @pytest.mark.asyncio
    async def test_on_text_callback_not_called_for_tools(self):
        """Test that on_text callback is not called for tool messages."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()
        received_texts = []

        def on_text_callback(text):
            received_texts.append(text)

        async def mock_subprocess(*args, **kwargs):
            yield ("tool", "Read: file.py", None)
            yield ("text", "Result", None)
            yield ("done", "{}", "session")

        with (
            patch(
                "src.services.claude_code_service.execute_claude_subprocess",
                side_effect=mock_subprocess,
            ),
            patch.object(service, "_save_session", new_callable=AsyncMock),
        ):
            async for _ in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
                on_text=on_text_callback,
            ):
                pass

        # Only the text message, not the tool
        assert len(received_texts) == 1
        assert "Result" in received_texts


class TestClaudeCodeServiceErrorHandling:
    """Tests for error handling in ClaudeCodeService."""

    @pytest.mark.asyncio
    async def test_exception_yields_error_message(self):
        """Test that exceptions are caught and yield error messages."""
        from src.services.claude_code_service import ClaudeCodeService

        service = ClaudeCodeService()

        async def mock_subprocess(*args, **kwargs):
            raise RuntimeError("Subprocess crashed")
            yield  # Never reached, but makes it a generator

        with patch(
            "src.services.claude_code_service.execute_claude_subprocess",
            side_effect=mock_subprocess,
        ):
            results = []
            async for msg_type, content, session_id in service.execute_prompt(
                chat_id=123,
                user_id=456,
                prompt="Test",
            ):
                results.append((msg_type, content, session_id))

        assert len(results) == 1
        assert results[0][0] == "error"
        assert "Subprocess crashed" in results[0][1]


# =============================================================================
# Import Tests
# =============================================================================


class TestClaudeCodeServiceImports:
    """Test imports and module structure."""

    def test_can_import_service(self):
        """Service can be imported."""
        from src.services.claude_code_service import ClaudeCodeService

        assert ClaudeCodeService is not None

    def test_can_import_helper_functions(self):
        """Helper functions can be imported."""
        from src.services.claude_code_service import (
            get_claude_code_service,
            is_claude_code_admin,
        )

        assert callable(get_claude_code_service)
        assert callable(is_claude_code_admin)

    def test_service_singleton_pattern(self):
        """get_claude_code_service returns singleton."""
        from src.services.claude_code_service import get_claude_code_service

        service1 = get_claude_code_service()
        service2 = get_claude_code_service()

        assert service1 is service2


class TestIsClaudeCodeAdmin:
    """Tests for is_claude_code_admin function."""

    @pytest.mark.asyncio
    async def test_admin_returns_true(self):
        """Admin user returns True."""
        from src.services.claude_code_service import _admin_cache, is_claude_code_admin

        # Clear cache to ensure fresh check
        _admin_cache.clear()

        mock_contact = MagicMock()
        mock_contact.active = True

        with patch("src.services.claude_code_service.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_contact
            mock_session.execute = AsyncMock(return_value=mock_result)

            async_cm = AsyncMock()
            async_cm.__aenter__ = AsyncMock(return_value=mock_session)
            async_cm.__aexit__ = AsyncMock(return_value=None)
            mock_db.return_value = async_cm

            result = await is_claude_code_admin(111)

        assert result is True

    @pytest.mark.asyncio
    async def test_non_admin_returns_false(self):
        """Non-admin user returns False."""
        from src.services.claude_code_service import _admin_cache, is_claude_code_admin

        # Clear cache to ensure fresh check
        _admin_cache.clear()

        with patch("src.services.claude_code_service.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            async_cm = AsyncMock()
            async_cm.__aenter__ = AsyncMock(return_value=mock_session)
            async_cm.__aexit__ = AsyncMock(return_value=None)
            mock_db.return_value = async_cm

            result = await is_claude_code_admin(222)

        assert result is False

    @pytest.mark.asyncio
    async def test_inactive_admin_returns_false(self):
        """Inactive admin user returns False.

        The query filters by active==True, so an inactive user won't be found.
        """
        from src.services.claude_code_service import _admin_cache, is_claude_code_admin

        # Clear cache to ensure fresh check
        _admin_cache.clear()

        with patch("src.services.claude_code_service.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            # Query filters by active==True, so inactive user returns None
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            async_cm = AsyncMock()
            async_cm.__aenter__ = AsyncMock(return_value=mock_session)
            async_cm.__aexit__ = AsyncMock(return_value=None)
            mock_db.return_value = async_cm

            result = await is_claude_code_admin(123)

        assert result is False
