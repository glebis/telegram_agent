"""Tests for /memory command handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.memory_commands import memory_command
from src.services.workspace_service import DEFAULT_TEMPLATE


def _make_update(text="/memory", user_id=123, chat_id=456):
    """Create a mock Update with given message text."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "testuser"
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture(autouse=True)
def _patch_deps(tmp_path, monkeypatch):
    """Patch workspace dir and initialize_user_chat."""
    monkeypatch.setattr(
        "src.services.workspace_service.WORKSPACES_DIR", tmp_path
    )


@pytest.mark.asyncio
async def test_memory_show_empty():
    """/memory with no workspace shows helpful message."""
    update = _make_update("/memory")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    call_args = send_mock.call_args
    assert "No memory set" in call_args[0][1]


@pytest.mark.asyncio
async def test_memory_show_with_content():
    """/memory shows existing content."""
    update = _make_update("/memory")
    ctx = MagicMock()

    # Pre-create workspace with content
    from src.services.workspace_service import update_memory

    update_memory(456, "Always respond concisely")

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    call_args = send_mock.call_args
    assert "Always respond concisely" in call_args[0][1]


@pytest.mark.asyncio
async def test_memory_edit_updates_content():
    """/memory edit replaces content."""
    update = _make_update("/memory edit Be brief and direct")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    from src.services.workspace_service import get_memory

    assert get_memory(456) == "Be brief and direct"
    assert "updated" in send_mock.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_memory_edit_empty_shows_usage():
    """/memory edit with no text shows usage."""
    update = _make_update("/memory edit")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    assert "Usage" in send_mock.call_args[0][1]


@pytest.mark.asyncio
async def test_memory_add_appends_content():
    """/memory add appends to existing memory."""
    from src.services.workspace_service import ensure_workspace

    ensure_workspace(456)

    update = _make_update("/memory add Prefer Python examples")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    from src.services.workspace_service import get_memory

    content = get_memory(456)
    assert "Prefer Python examples" in content
    assert content.startswith(DEFAULT_TEMPLATE)
    assert "appended" in send_mock.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_memory_export_sends_document():
    """/memory export sends the CLAUDE.md file."""
    from src.services.workspace_service import ensure_workspace

    ensure_workspace(456)

    update = _make_update("/memory export")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ), patch("requests.post") as req_mock, patch.dict(
        "os.environ", {"TELEGRAM_BOT_TOKEN": "fake-token"}
    ):
        await memory_command(update, ctx)

    req_mock.assert_called_once()
    call_kwargs = req_mock.call_args
    assert "sendDocument" in call_kwargs[0][0]


@pytest.mark.asyncio
async def test_memory_reset_restores_default():
    """/memory reset restores the default template."""
    from src.services.workspace_service import update_memory

    update_memory(456, "custom content")

    update = _make_update("/memory reset")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ) as send_mock:
        await memory_command(update, ctx)

    from src.services.workspace_service import get_memory

    assert get_memory(456) == DEFAULT_TEMPLATE
    assert "reset" in send_mock.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_memory_colon_syntax():
    """/memory:edit works with colon subcommand syntax."""
    update = _make_update("/memory:edit Colon style")
    ctx = MagicMock()

    with patch(
        "src.bot.handlers.memory_commands.initialize_user_chat",
        new_callable=AsyncMock,
    ), patch(
        "src.bot.handlers.memory_commands.send_message_sync"
    ):
        await memory_command(update, ctx)

    from src.services.workspace_service import get_memory

    assert get_memory(456) == "Colon style"
