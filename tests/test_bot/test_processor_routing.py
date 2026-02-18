"""
Characterization tests for CombinedMessageProcessor routing logic.

Tests the routing decision tree in process() to ensure behavior is preserved
during the god-object refactoring (issue #152).

Routing priority:
1. Plugin message processors (highest)
2. Commands (/claude, /meta, /dev)
3. Collect mode (add to queue or trigger)
4. Reply context handling (todo, life weeks, etc.)
5. Claude mode checks
6. Content-type routing: images > voice > videos > polls > contacts > documents > text
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class FakeBufferedMessage:
    """Minimal BufferedMessage for routing tests."""

    message_id: int
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: str = "text"
    text: Optional[str] = None
    caption: Optional[str] = None
    file_id: Optional[str] = None
    is_claude_command: bool = False
    is_meta_command: bool = False
    is_dev_command: bool = False
    command_type: Optional[str] = None
    message: MagicMock = field(default_factory=MagicMock)
    update: MagicMock = field(default_factory=MagicMock)
    context: MagicMock = field(default_factory=MagicMock)
    forward_from_chat_username: Optional[str] = None
    forward_message_id: Optional[int] = None
    poll_question: Optional[str] = None
    poll_options: Optional[list] = None
    poll_type: Optional[str] = None
    poll_total_voter_count: Optional[int] = None


@dataclass
class FakeCombinedMessage:
    """Minimal CombinedMessage for routing tests."""

    chat_id: int
    user_id: int
    messages: List[FakeBufferedMessage] = field(default_factory=list)
    combined_text: str = ""
    images: List[FakeBufferedMessage] = field(default_factory=list)
    voices: List[FakeBufferedMessage] = field(default_factory=list)
    videos: List[FakeBufferedMessage] = field(default_factory=list)
    documents: List[FakeBufferedMessage] = field(default_factory=list)
    contacts: List[FakeBufferedMessage] = field(default_factory=list)
    polls: List[FakeBufferedMessage] = field(default_factory=list)
    reply_to_message_id: Optional[int] = None
    reply_to_message_text: Optional[str] = None
    reply_to_message_type: Optional[str] = None
    reply_to_message_from_bot: bool = False
    reply_to_message_date: Optional[datetime] = None
    overflow_count: int = 0

    def has_images(self) -> bool:
        return len(self.images) > 0

    def has_voice(self) -> bool:
        return len(self.voices) > 0

    def has_videos(self) -> bool:
        return len(self.videos) > 0

    def has_documents(self) -> bool:
        return len(self.documents) > 0

    def has_polls(self) -> bool:
        return len(self.polls) > 0

    def has_command(self) -> bool:
        return any(
            m.is_claude_command or m.is_meta_command or m.is_dev_command
            for m in self.messages
        )

    def has_claude_command(self) -> bool:
        return any(m.is_claude_command for m in self.messages)

    def get_command_message(self) -> Optional[FakeBufferedMessage]:
        for m in self.messages:
            if m.is_claude_command or m.is_meta_command or m.is_dev_command:
                return m
        return None

    def get_claude_command_message(self) -> Optional[FakeBufferedMessage]:
        for m in self.messages:
            if m.is_claude_command:
                return m
        return None

    def get_forward_context(self) -> Optional[str]:
        return None

    def get_link_comment_context(self) -> Optional[str]:
        return None

    @property
    def primary_update(self):
        return self.messages[0].update if self.messages else MagicMock()

    @property
    def primary_context(self):
        return self.messages[0].context if self.messages else MagicMock()

    @property
    def primary_message(self):
        return self.messages[0].message if self.messages else MagicMock()


def _make_text_msg(chat_id=123, user_id=456, text="hello"):
    """Create a simple text-only CombinedMessage."""
    msg = FakeBufferedMessage(message_id=1, text=text)
    return FakeCombinedMessage(
        chat_id=chat_id,
        user_id=user_id,
        messages=[msg],
        combined_text=text,
    )


def _make_image_msg(chat_id=123, user_id=456, text="", n_images=1):
    """Create a CombinedMessage with images."""
    msgs = []
    images = []
    for i in range(n_images):
        img = FakeBufferedMessage(
            message_id=i + 1,
            message_type="photo",
            file_id=f"photo_{i}",
        )
        images.append(img)
        msgs.append(img)
    return FakeCombinedMessage(
        chat_id=chat_id,
        user_id=user_id,
        messages=msgs,
        combined_text=text,
        images=images,
    )


def _make_voice_msg(chat_id=123, user_id=456, text=""):
    """Create a CombinedMessage with a voice message."""
    voice = FakeBufferedMessage(message_id=1, message_type="voice", file_id="voice_1")
    return FakeCombinedMessage(
        chat_id=chat_id,
        user_id=user_id,
        messages=[voice],
        combined_text=text,
        voices=[voice],
    )


def _make_command_msg(
    chat_id=123, user_id=456, command_type="claude", text="/claude do stuff"
):
    """Create a CombinedMessage with a command."""
    msg = FakeBufferedMessage(
        message_id=1,
        text=text,
        is_claude_command=(command_type == "claude"),
        is_meta_command=(command_type == "meta"),
        is_dev_command=(command_type == "dev"),
        command_type=command_type,
    )
    return FakeCombinedMessage(
        chat_id=chat_id,
        user_id=user_id,
        messages=[msg],
        combined_text=text,
    )


# ── Patches needed to instantiate CombinedMessageProcessor ──


@pytest.fixture
def mock_reply_service():
    """Mock reply context service."""
    with patch("src.bot.combined_processor.get_reply_context_service") as mock_factory:
        service = MagicMock()
        service.get_context.return_value = None
        mock_factory.return_value = service
        yield service


@pytest.fixture
def mock_persist():
    """Mock message persistence (fire-and-forget)."""
    with patch(
        "src.bot.combined_processor.persist_message", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_task_tracker():
    """Mock task tracker to capture background tasks."""
    with patch("src.bot.combined_processor.create_tracked_task") as mock:
        # Close coroutines to avoid RuntimeWarning
        def close_coro(coro, name=None):
            coro.close()
            return MagicMock()

        mock.side_effect = close_coro
        yield mock


@pytest.fixture
def mock_plugin_manager():
    """Mock plugin manager that doesn't handle messages.

    get_plugin_manager is lazily imported inside process(), so patch at source.
    """
    with patch("src.plugins.get_plugin_manager") as mock_factory:
        pm = MagicMock()
        pm.route_message = AsyncMock(return_value=False)
        mock_factory.return_value = pm
        yield pm


@pytest.fixture
def mock_collect_service():
    """Mock collect service (not collecting by default).

    get_collect_service is lazily imported inside process(), so patch at source.
    """
    with patch("src.services.collect_service.get_collect_service") as mock_factory:
        service = MagicMock()
        service.is_collecting = AsyncMock(return_value=False)
        service.check_trigger_keywords.return_value = False
        service.start_session = AsyncMock()
        service.add_item = AsyncMock()
        service.get_session = AsyncMock(return_value=None)
        mock_factory.return_value = service
        yield service


@pytest.fixture
def mock_claude_mode():
    """Mock Claude mode as inactive by default.

    is_claude_code_admin and _claude_mode_cache are lazily imported inside process().
    """
    with (
        patch(
            "src.services.claude_code_service.is_claude_code_admin",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_admin,
        patch("src.bot.handlers._claude_mode_cache", {}) as mock_cache,
    ):
        yield mock_admin, mock_cache


@pytest.fixture
def processor(
    mock_reply_service,
    mock_persist,
    mock_task_tracker,
    mock_plugin_manager,
    mock_collect_service,
    mock_claude_mode,
):
    """Create a CombinedMessageProcessor with all dependencies mocked."""
    from src.bot.combined_processor import CombinedMessageProcessor

    return CombinedMessageProcessor()


# ═══════════════════════════════════════════════════════════════
# 1. Plugin routing (highest priority)
# ═══════════════════════════════════════════════════════════════


class TestPluginRouting:
    """Plugin router takes highest priority."""

    @pytest.mark.asyncio
    async def test_plugin_handles_message_stops_routing(
        self, processor, mock_plugin_manager, mock_task_tracker
    ):
        """When a plugin handles a message, no further routing occurs."""
        mock_plugin_manager.route_message = AsyncMock(return_value=True)
        combined = _make_text_msg()

        await processor.process(combined)

        mock_plugin_manager.route_message.assert_awaited_once()
        # No content-type routing should happen (no background tasks created
        # beyond persist_message tasks)

    @pytest.mark.asyncio
    async def test_plugin_declines_falls_through(self, processor, mock_plugin_manager):
        """When plugin declines, routing continues."""
        mock_plugin_manager.route_message = AsyncMock(return_value=False)
        combined = _make_text_msg()

        with patch.object(
            processor, "_process_text", new_callable=AsyncMock
        ) as mock_text:
            await processor.process(combined)
            mock_text.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# 2. Command routing
# ═══════════════════════════════════════════════════════════════


class TestCommandRouting:
    """Commands take priority over content-type routing."""

    @pytest.mark.asyncio
    async def test_claude_command_routes_to_process_command(self, processor):
        """A /claude command routes to _process_command."""
        combined = _make_command_msg(command_type="claude")

        with patch.object(
            processor, "_process_command", new_callable=AsyncMock
        ) as mock_cmd:
            await processor.process(combined)
            mock_cmd.assert_awaited_once_with(combined)

    @pytest.mark.asyncio
    async def test_meta_command_routes_to_process_command(self, processor):
        """A /meta command routes to _process_command."""
        combined = _make_command_msg(command_type="meta", text="/meta fix bug")

        with patch.object(
            processor, "_process_command", new_callable=AsyncMock
        ) as mock_cmd:
            await processor.process(combined)
            mock_cmd.assert_awaited_once_with(combined)

    @pytest.mark.asyncio
    async def test_command_takes_priority_over_images(self, processor):
        """A command message with images should route to command, not images."""
        msg = FakeBufferedMessage(
            message_id=1,
            text="/claude analyze",
            is_claude_command=True,
            command_type="claude",
        )
        img = FakeBufferedMessage(message_id=2, file_id="photo_1")
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[msg, img],
            combined_text="/claude analyze",
            images=[img],
        )

        with (
            patch.object(
                processor, "_process_command", new_callable=AsyncMock
            ) as mock_cmd,
            patch.object(
                processor, "_process_with_images", new_callable=AsyncMock
            ) as mock_img,
        ):
            await processor.process(combined)
            mock_cmd.assert_awaited_once()
            mock_img.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# 3. Collect mode routing
# ═══════════════════════════════════════════════════════════════


class TestCollectModeRouting:
    """Collect mode intercepts messages before content-type routing."""

    @pytest.mark.asyncio
    async def test_collecting_adds_to_queue(self, processor, mock_collect_service):
        """When collecting, messages go to collect queue."""
        mock_collect_service.is_collecting = AsyncMock(return_value=True)
        combined = _make_text_msg(text="some note")

        with patch.object(
            processor, "_add_to_collect_queue", new_callable=AsyncMock
        ) as mock_add:
            await processor.process(combined)
            mock_add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collecting_trigger_processes_queue(
        self, processor, mock_collect_service
    ):
        """When collecting and trigger keyword detected, process queue."""
        mock_collect_service.is_collecting = AsyncMock(return_value=True)
        mock_collect_service.check_trigger_keywords.return_value = True
        combined = _make_text_msg(text="now respond")

        with patch.object(
            processor, "_process_collect_trigger", new_callable=AsyncMock
        ) as mock_trigger:
            await processor.process(combined)
            mock_trigger.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_collecting_falls_through(self, processor, mock_collect_service):
        """When not collecting, routing continues to content handlers."""
        mock_collect_service.is_collecting = AsyncMock(return_value=False)
        combined = _make_text_msg()

        with patch.object(
            processor, "_process_text", new_callable=AsyncMock
        ) as mock_text:
            await processor.process(combined)
            mock_text.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# 4. Content-type routing priority
# ═══════════════════════════════════════════════════════════════


class TestContentTypeRouting:
    """Content-type routing follows strict priority: images > voice > video > polls > contacts > docs > text."""

    @pytest.mark.asyncio
    async def test_text_routes_to_process_text(self, processor):
        """Text-only message routes to _process_text."""
        combined = _make_text_msg()

        with patch.object(
            processor, "_process_text", new_callable=AsyncMock
        ) as mock_text:
            await processor.process(combined)
            mock_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_images_route_to_process_with_images(self, processor):
        """Image message routes to _process_with_images."""
        combined = _make_image_msg()

        with patch.object(
            processor, "_process_with_images", new_callable=AsyncMock
        ) as mock_img:
            await processor.process(combined)
            mock_img.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_voice_routes_to_process_with_voice(self, processor):
        """Voice message routes to _process_with_voice."""
        combined = _make_voice_msg()

        with patch.object(
            processor, "_process_with_voice", new_callable=AsyncMock
        ) as mock_voice:
            await processor.process(combined)
            mock_voice.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_video_routes_to_process_with_videos(self, processor):
        """Video message routes to _process_with_videos."""
        video = FakeBufferedMessage(message_id=1, file_id="video_1")
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[video],
            videos=[video],
        )

        with patch.object(
            processor, "_process_with_videos", new_callable=AsyncMock
        ) as mock_vid:
            await processor.process(combined)
            mock_vid.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_polls_route_to_process_with_polls(self, processor):
        """Poll message routes to _process_with_polls."""
        poll = FakeBufferedMessage(
            message_id=1, poll_question="Best color?", poll_options=["Red", "Blue"]
        )
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[poll],
            polls=[poll],
        )

        with patch.object(
            processor, "_process_with_polls", new_callable=AsyncMock
        ) as mock_poll:
            await processor.process(combined)
            mock_poll.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_contacts_route_to_process_contacts(self, processor):
        """Contact message routes to _process_contacts."""
        contact = FakeBufferedMessage(message_id=1)
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[contact],
            contacts=[contact],
        )

        with patch.object(
            processor, "_process_contacts", new_callable=AsyncMock
        ) as mock_contact:
            await processor.process(combined)
            mock_contact.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_documents_route_to_process_documents(self, processor):
        """Document message routes to _process_documents."""
        doc = FakeBufferedMessage(message_id=1, file_id="doc_1")
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[doc],
            documents=[doc],
        )

        with patch.object(
            processor, "_process_documents", new_callable=AsyncMock
        ) as mock_doc:
            await processor.process(combined)
            mock_doc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_images_take_priority_over_voice(self, processor):
        """Images have higher priority than voice in routing."""
        img = FakeBufferedMessage(message_id=1, file_id="photo_1")
        voice = FakeBufferedMessage(message_id=2, file_id="voice_1")
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[img, voice],
            images=[img],
            voices=[voice],
        )

        with (
            patch.object(
                processor, "_process_with_images", new_callable=AsyncMock
            ) as mock_img,
            patch.object(
                processor, "_process_with_voice", new_callable=AsyncMock
            ) as mock_voice,
        ):
            await processor.process(combined)
            mock_img.assert_awaited_once()
            mock_voice.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_voice_takes_priority_over_videos(self, processor):
        """Voice has higher priority than video in routing."""
        voice = FakeBufferedMessage(message_id=1, file_id="voice_1")
        video = FakeBufferedMessage(message_id=2, file_id="video_1")
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[voice, video],
            voices=[voice],
            videos=[video],
        )

        with (
            patch.object(
                processor, "_process_with_voice", new_callable=AsyncMock
            ) as mock_voice,
            patch.object(
                processor, "_process_with_videos", new_callable=AsyncMock
            ) as mock_vid,
        ):
            await processor.process(combined)
            mock_voice.assert_awaited_once()
            mock_vid.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_message_logs_warning(self, processor):
        """Message with no content triggers warning log."""
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[FakeBufferedMessage(message_id=1)],
        )

        # Should not raise
        await processor.process(combined)


# ═══════════════════════════════════════════════════════════════
# 5. Claude mode routing
# ═══════════════════════════════════════════════════════════════


class TestClaudeModeRouting:
    """Claude mode affects how content handlers route internally."""

    @pytest.mark.asyncio
    async def test_text_in_claude_mode_passes_claude_flag(
        self, processor, mock_claude_mode
    ):
        """Text handler receives is_claude_mode=True when Claude mode active."""
        _, cache = mock_claude_mode
        cache[123] = True
        mock_claude_mode[0].return_value = True  # is_claude_code_admin

        combined = _make_text_msg()

        with patch.object(
            processor, "_process_text", new_callable=AsyncMock
        ) as mock_text:
            await processor.process(combined)
            # Third argument should be is_claude_mode=True
            args = mock_text.call_args
            assert args[0][2] is True  # is_claude_mode

    @pytest.mark.asyncio
    async def test_text_without_claude_mode_passes_false(self, processor):
        """Text handler receives is_claude_mode=False when Claude mode inactive."""
        combined = _make_text_msg()

        with patch.object(
            processor, "_process_text", new_callable=AsyncMock
        ) as mock_text:
            await processor.process(combined)
            args = mock_text.call_args
            assert args[0][2] is False  # is_claude_mode


# ═══════════════════════════════════════════════════════════════
# 6. Overflow notification
# ═══════════════════════════════════════════════════════════════


class TestOverflowNotification:
    """Overflow notification is sent after content processing."""

    @pytest.mark.asyncio
    async def test_overflow_sends_notification(self, processor):
        """When overflow_count > 0, user gets notified."""
        msg = FakeBufferedMessage(message_id=1, text="hello")
        msg.message.reply_text = AsyncMock()
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[msg],
            combined_text="hello",
            overflow_count=3,
        )

        with patch.object(processor, "_process_text", new_callable=AsyncMock):
            await processor.process(combined)

        msg.message.reply_text.assert_awaited_once()
        call_text = msg.message.reply_text.call_args[0][0]
        assert "3" in call_text
        assert "dropped" in call_text

    @pytest.mark.asyncio
    async def test_no_overflow_no_notification(self, processor):
        """When overflow_count is 0, no notification is sent."""
        msg = FakeBufferedMessage(message_id=1, text="hello")
        msg.message.reply_text = AsyncMock()
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[msg],
            combined_text="hello",
            overflow_count=0,
        )

        with patch.object(processor, "_process_text", new_callable=AsyncMock):
            await processor.process(combined)

        msg.message.reply_text.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# 7. Error handling
# ═══════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Error handling in the routing layer."""

    @pytest.mark.asyncio
    async def test_content_handler_error_sends_user_notification(self, processor):
        """When a content handler raises, user gets error message."""
        msg = FakeBufferedMessage(message_id=1, text="hello")
        msg.message.reply_text = AsyncMock()
        combined = FakeCombinedMessage(
            chat_id=123,
            user_id=456,
            messages=[msg],
            combined_text="hello",
        )

        with patch.object(
            processor,
            "_process_text",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await processor.process(combined)

        msg.message.reply_text.assert_awaited()
        call_text = msg.message.reply_text.call_args[0][0]
        assert "Error" in call_text

    @pytest.mark.asyncio
    async def test_cancelled_error_reraises(self, processor):
        """CancelledError is re-raised, not swallowed."""
        combined = _make_text_msg()

        with patch.object(
            processor,
            "_process_text",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            with pytest.raises(asyncio.CancelledError):
                await processor.process(combined)
