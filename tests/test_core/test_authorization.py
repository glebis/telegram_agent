"""
Tests for hierarchical authorization model.

Tests tier resolution, @require_tier decorator, tool filtering, and
backward compatibility (no OWNER_USER_ID = all users are OWNER).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.authorization import (
    AuthTier,
    get_allowed_tools_for_tier,
    get_user_tier,
    require_tier,
)

# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------


class TestAuthTierOrdering:
    """AuthTier enum has correct ordering (higher value = more privilege)."""

    def test_owner_is_highest(self):
        assert AuthTier.OWNER.value > AuthTier.ADMIN.value

    def test_admin_above_user(self):
        assert AuthTier.ADMIN.value > AuthTier.USER.value

    def test_user_above_group(self):
        assert AuthTier.USER.value > AuthTier.GROUP.value

    def test_comparison_operators(self):
        assert AuthTier.OWNER >= AuthTier.ADMIN
        assert AuthTier.ADMIN >= AuthTier.USER
        assert AuthTier.USER >= AuthTier.GROUP
        assert not (AuthTier.GROUP >= AuthTier.USER)


class TestGetUserTier:
    """Tests for get_user_tier() resolution logic."""

    @patch("src.core.authorization.get_settings")
    def test_owner_by_user_id(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222,333",
            allowed_user_ids="444,555",
        )
        assert get_user_tier(user_id=111, chat_id=111) == AuthTier.OWNER

    @patch("src.core.authorization.get_settings")
    def test_admin_by_user_id(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222,333",
            allowed_user_ids="444,555",
        )
        assert get_user_tier(user_id=222, chat_id=222) == AuthTier.ADMIN
        assert get_user_tier(user_id=333, chat_id=333) == AuthTier.ADMIN

    @patch("src.core.authorization.get_settings")
    def test_user_in_allowlist(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="444,555",
        )
        assert get_user_tier(user_id=444, chat_id=444) == AuthTier.USER

    @patch("src.core.authorization.get_settings")
    def test_user_when_allowlist_empty(self, mock_settings):
        """All authenticated users are USER when allowlist is empty."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="",
        )
        # Unknown user with empty allowlist should be USER (not GROUP) in private chat
        assert get_user_tier(user_id=999, chat_id=999) == AuthTier.USER

    @patch("src.core.authorization.get_settings")
    def test_group_chat_default(self, mock_settings):
        """Group chats (negative chat_id) default to GROUP tier for unknown users."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="444",
        )
        # Negative chat_id = group/supergroup
        assert get_user_tier(user_id=999, chat_id=-100123456) == AuthTier.GROUP

    @patch("src.core.authorization.get_settings")
    def test_owner_in_group_chat_still_owner(self, mock_settings):
        """Owner keeps OWNER tier even in group chats."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=111, chat_id=-100123456) == AuthTier.OWNER

    @patch("src.core.authorization.get_settings")
    def test_admin_in_group_chat_still_admin(self, mock_settings):
        """Admin keeps ADMIN tier even in group chats."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=222, chat_id=-100123456) == AuthTier.ADMIN

    @patch("src.core.authorization.get_settings")
    def test_unknown_user_with_allowlist_in_private_chat(self, mock_settings):
        """User not in allowlist in a private chat gets GROUP tier."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="444,555",
        )
        assert get_user_tier(user_id=999, chat_id=999) == AuthTier.GROUP


# ---------------------------------------------------------------------------
# Backward compatibility: no OWNER_USER_ID => all users are OWNER
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """When OWNER_USER_ID is not set, every authenticated user is treated as OWNER."""

    @patch("src.core.authorization.get_settings")
    def test_no_owner_set_treats_all_as_owner(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=None,
            admin_user_ids="",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=999, chat_id=999) == AuthTier.OWNER

    @patch("src.core.authorization.get_settings")
    def test_no_owner_set_group_chat_still_owner(self, mock_settings):
        """Even in group chats, no owner set means OWNER for all."""
        mock_settings.return_value = MagicMock(
            owner_user_id=None,
            admin_user_ids="",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=999, chat_id=-100123456) == AuthTier.OWNER

    @patch("src.core.authorization.get_settings")
    def test_owner_zero_treated_as_unset(self, mock_settings):
        """owner_user_id=0 should be treated as unset (falsy)."""
        mock_settings.return_value = MagicMock(
            owner_user_id=0,
            admin_user_ids="",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=999, chat_id=999) == AuthTier.OWNER


# ---------------------------------------------------------------------------
# @require_tier decorator
# ---------------------------------------------------------------------------


class TestRequireTier:
    """Tests for the @require_tier decorator."""

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_allows_sufficient_tier(self, mock_settings):
        """OWNER can access ADMIN-tier commands."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="",
            allowed_user_ids="",
        )
        called = False

        @require_tier(AuthTier.ADMIN)
        async def handler(update, context):
            nonlocal called
            called = True

        update = _make_update(user_id=111, chat_id=111)
        context = MagicMock()
        await handler(update, context)
        assert called is True

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_blocks_insufficient_tier(self, mock_settings):
        """GROUP cannot access ADMIN-tier commands."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="333",
        )
        called = False

        @require_tier(AuthTier.ADMIN)
        async def handler(update, context):
            nonlocal called
            called = True

        update = _make_update(user_id=999, chat_id=-100123456)
        context = MagicMock()
        await handler(update, context)
        assert called is False

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_sends_not_authorized_message(self, mock_settings):
        """Decorator sends a polite denial message when tier is insufficient."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="333",
        )

        @require_tier(AuthTier.OWNER)
        async def handler(update, context):
            pass

        update = _make_update(user_id=333, chat_id=333)
        context = MagicMock()
        await handler(update, context)

        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert (
            "not authorized" in call_text.lower() or "permission" in call_text.lower()
        )

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_exact_tier_match_allowed(self, mock_settings):
        """ADMIN can access ADMIN-tier commands (exact match)."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="",
        )
        called = False

        @require_tier(AuthTier.ADMIN)
        async def handler(update, context):
            nonlocal called
            called = True

        update = _make_update(user_id=222, chat_id=222)
        context = MagicMock()
        await handler(update, context)
        assert called is True

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_no_update_user_returns_early(self, mock_settings):
        """Decorator returns without calling handler if no effective_user."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="",
            allowed_user_ids="",
        )
        called = False

        @require_tier(AuthTier.USER)
        async def handler(update, context):
            nonlocal called
            called = True

        update = MagicMock()
        update.effective_user = None
        update.effective_chat = MagicMock(id=111)
        context = MagicMock()
        await handler(update, context)
        assert called is False

    @patch("src.core.authorization.get_settings")
    @pytest.mark.asyncio
    async def test_no_message_attribute_graceful(self, mock_settings):
        """If update has no message (e.g. callback), decorator handles gracefully."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="",
            allowed_user_ids="333",
        )

        @require_tier(AuthTier.OWNER)
        async def handler(update, context):
            pass

        update = _make_update(user_id=333, chat_id=333)
        update.message = None  # No message object
        context = MagicMock()
        # Should not raise
        await handler(update, context)


# ---------------------------------------------------------------------------
# Claude tool filtering
# ---------------------------------------------------------------------------


class TestGetAllowedToolsForTier:
    """Tests for per-tier Claude tool restrictions."""

    def test_owner_unrestricted(self):
        result = get_allowed_tools_for_tier(AuthTier.OWNER)
        assert result is None  # None = unrestricted

    def test_admin_full_access(self):
        result = get_allowed_tools_for_tier(AuthTier.ADMIN)
        assert result is None  # Full tool access

    def test_user_safe_subset(self):
        result = get_allowed_tools_for_tier(AuthTier.USER)
        assert result is not None
        assert "Read" in result
        assert "Glob" in result
        assert "Grep" in result
        assert "Write" in result
        assert "Edit" in result
        # Should NOT include dangerous tools
        assert "Bash" not in result

    def test_group_read_only(self):
        result = get_allowed_tools_for_tier(AuthTier.GROUP)
        assert result is not None
        assert "Read" in result
        assert "Glob" in result
        assert "Grep" in result
        # Should NOT include write tools
        assert "Write" not in result
        assert "Edit" not in result
        assert "Bash" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: malformed config, spaces in IDs, etc."""

    @patch("src.core.authorization.get_settings")
    def test_admin_ids_with_spaces(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids=" 222 , 333 ",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=222, chat_id=222) == AuthTier.ADMIN
        assert get_user_tier(user_id=333, chat_id=333) == AuthTier.ADMIN

    @patch("src.core.authorization.get_settings")
    def test_empty_admin_ids(self, mock_settings):
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="",
            allowed_user_ids="",
        )
        # User 222 is not admin
        assert get_user_tier(user_id=222, chat_id=222) == AuthTier.USER

    @patch("src.core.authorization.get_settings")
    def test_user_who_is_both_admin_and_allowed(self, mock_settings):
        """User in both admin and allowed lists gets ADMIN (higher tier)."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="222",
            allowed_user_ids="222,333",
        )
        assert get_user_tier(user_id=222, chat_id=222) == AuthTier.ADMIN

    @patch("src.core.authorization.get_settings")
    def test_owner_who_is_also_admin(self, mock_settings):
        """Owner in admin list still gets OWNER (highest tier)."""
        mock_settings.return_value = MagicMock(
            owner_user_id=111,
            admin_user_ids="111,222",
            allowed_user_ids="",
        )
        assert get_user_tier(user_id=111, chat_id=111) == AuthTier.OWNER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_update(user_id: int, chat_id: int) -> MagicMock:
    """Create a minimal mock Telegram Update with user and chat."""
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id)
    update.effective_chat = MagicMock(id=chat_id)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update
