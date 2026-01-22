"""
Tests for the Session Naming Service.

Tests cover:
- Session name generation from prompts
- Fallback behavior when API fails
- Name sanitization and validation
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.session_naming import generate_session_name


class TestGenerateSessionName:
    """Tests for generate_session_name function."""

    @pytest.fixture
    def mock_anthropic_response(self):
        """Create a mock Anthropic response."""
        response = MagicMock()
        response.content = [MagicMock(text="test-session-name")]
        return response

    @pytest.mark.asyncio
    async def test_generates_valid_kebab_case_name(self, mock_anthropic_response):
        """Test that generated names are valid kebab-case."""
        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Test prompt for session naming")

            assert name == "test-session-name"
            assert name.islower()
            assert re.match(r"^[a-z0-9-]+$", name)

    @pytest.mark.asyncio
    async def test_sanitizes_special_characters(self):
        """Test that special characters are removed from generated names."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test@Session#Name!")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            # Special chars should be removed
            assert "@" not in name
            assert "#" not in name
            assert "!" not in name
            assert name == "testsessionname"

    @pytest.mark.asyncio
    async def test_removes_multiple_hyphens(self):
        """Test that multiple consecutive hyphens are collapsed."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test---session---name")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert "---" not in name
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_removes_leading_trailing_hyphens(self):
        """Test that leading and trailing hyphens are removed."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="-test-session-name-")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert not name.startswith("-")
            assert not name.endswith("-")
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_limits_name_length(self):
        """Test that names are limited to 50 characters."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="a" * 100)]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert len(name) <= 50

    @pytest.mark.asyncio
    async def test_truncates_long_prompt(self):
        """Test that very long prompts are truncated before sending to API."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="truncated-prompt")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            long_prompt = "x" * 1000
            await generate_session_name(long_prompt)

            # Verify the prompt was truncated to 500 chars
            call_args = mock_client.messages.create.call_args
            sent_message = call_args.kwargs["messages"][0]["content"]
            assert len(sent_message) <= 500


class TestFallbackBehavior:
    """Tests for fallback behavior when API fails."""

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self):
        """Test fallback name generation when API call fails."""
        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Help me analyze this video")

            # Should use fallback logic - first few meaningful words
            assert name  # Should not be empty
            assert re.match(r"^[a-z0-9-]+$", name)

    @pytest.mark.asyncio
    async def test_fallback_filters_common_words(self):
        """Test that fallback filters articles and prepositions."""
        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_get_client.return_value = mock_client

            name = await generate_session_name("The quick fox in the forest")

            # Common words like 'the', 'in' should be filtered
            assert "the" not in name.split("-")
            assert "in" not in name.split("-")

    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self):
        """Test fallback when API returns empty name."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Test prompt")

            # Should use fallback
            assert name  # Should not be empty

    @pytest.mark.asyncio
    async def test_fallback_unnamed_session(self):
        """Test that empty prompts result in 'unnamed-session'."""
        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_get_client.return_value = mock_client

            # Prompt with only filtered words
            name = await generate_session_name("the a an to for in on")

            # After filtering common words, should fall back to 'unnamed-session'
            assert name == "unnamed-session"


class TestNameValidation:
    """Tests for name validation rules."""

    @pytest.mark.asyncio
    async def test_name_is_lowercase(self):
        """Test that generated names are always lowercase."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="UPPERCASE-NAME")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert name.islower()
            assert name == "uppercase-name"

    @pytest.mark.asyncio
    async def test_spaces_converted_to_hyphens(self):
        """Test that spaces are converted to hyphens."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test session name")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert " " not in name
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_name_contains_only_valid_chars(self):
        """Test that names only contain a-z, 0-9, and hyphens."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test123-name456")]

        with patch(
            "src.services.session_naming.get_anthropic_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            name = await generate_session_name("Any prompt")

            assert re.match(r"^[a-z0-9-]+$", name)
            assert name == "test123-name456"
