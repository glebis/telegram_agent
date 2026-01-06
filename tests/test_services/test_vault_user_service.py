"""
Tests for the Vault User Service.

Tests cover:
- Handle normalization (_normalize_handle)
- YAML frontmatter parsing (_parse_frontmatter)
- Handle extraction from various YAML formats (_extract_handle_from_yaml)
- User lookup in vault (lookup_telegram_user)
- Forward context building (build_forward_context)
- Caching behavior
- Edge cases and error handling
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_vault_dir():
    """Create a temporary vault directory with People folder."""
    with tempfile.TemporaryDirectory() as temp_dir:
        people_dir = Path(temp_dir) / "vault" / "People"
        people_dir.mkdir(parents=True, exist_ok=True)
        yield people_dir


@pytest.fixture
def sample_note_content():
    """Create sample note content with frontmatter."""
    return '''---
tags:
  - people
telegram: "@TestUser"
email: test@example.com
---

# @Test User

Some content about the user.
'''


@pytest.fixture
def clear_cache():
    """Clear the user cache before and after tests."""
    from src.services.vault_user_service import _user_cache
    _user_cache.clear()
    yield
    _user_cache.clear()


# =============================================================================
# _normalize_handle Tests
# =============================================================================


class TestNormalizeHandle:
    """Tests for handle normalization."""

    def test_normalize_with_at_symbol(self):
        """Test normalizing handle with @ symbol."""
        from src.services.vault_user_service import _normalize_handle

        result = _normalize_handle("@TestUser")
        assert result == "testuser"

    def test_normalize_without_at_symbol(self):
        """Test normalizing handle without @ symbol."""
        from src.services.vault_user_service import _normalize_handle

        result = _normalize_handle("TestUser")
        assert result == "testuser"

    def test_normalize_already_lowercase(self):
        """Test normalizing already lowercase handle."""
        from src.services.vault_user_service import _normalize_handle

        result = _normalize_handle("testuser")
        assert result == "testuser"

    def test_normalize_mixed_case(self):
        """Test normalizing mixed case handle."""
        from src.services.vault_user_service import _normalize_handle

        result = _normalize_handle("@TeStUsEr123")
        assert result == "testuser123"

    def test_normalize_multiple_at_symbols(self):
        """Test normalizing handle with multiple @ symbols (lstrip removes all leading @)."""
        from src.services.vault_user_service import _normalize_handle

        result = _normalize_handle("@@TestUser")
        assert result == "testuser"  # lstrip removes all leading @ characters


# =============================================================================
# _parse_frontmatter Tests
# =============================================================================


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        from src.services.vault_user_service import _parse_frontmatter

        content = '''---
telegram: "@TestUser"
email: test@example.com
---

# Content here
'''
        result = _parse_frontmatter(content)

        assert result["telegram"] == '"@TestUser"'
        assert result["email"] == "test@example.com"

    def test_parse_frontmatter_no_yaml(self):
        """Test parsing content without frontmatter."""
        from src.services.vault_user_service import _parse_frontmatter

        content = "# Just a heading\n\nSome content."
        result = _parse_frontmatter(content)

        assert result == {}

    def test_parse_frontmatter_missing_end_delimiter(self):
        """Test parsing frontmatter without closing delimiter."""
        from src.services.vault_user_service import _parse_frontmatter

        content = '''---
telegram: "@TestUser"
# Missing closing delimiter
'''
        result = _parse_frontmatter(content)

        assert result == {}

    def test_parse_frontmatter_empty_content(self):
        """Test parsing empty content."""
        from src.services.vault_user_service import _parse_frontmatter

        result = _parse_frontmatter("")
        assert result == {}

    def test_parse_frontmatter_only_delimiters(self):
        """Test parsing frontmatter with only delimiters."""
        from src.services.vault_user_service import _parse_frontmatter

        content = "---\n---\nContent"
        result = _parse_frontmatter(content)

        assert result == {}

    def test_parse_frontmatter_multiline_values(self):
        """Test parsing frontmatter with simple key-value pairs."""
        from src.services.vault_user_service import _parse_frontmatter

        content = '''---
key1: value1
key2: value2
---
'''
        result = _parse_frontmatter(content)

        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_parse_frontmatter_with_colons_in_value(self):
        """Test parsing values containing colons."""
        from src.services.vault_user_service import _parse_frontmatter

        content = '''---
url: https://example.com
---
'''
        result = _parse_frontmatter(content)

        assert result["url"] == "https://example.com"


# =============================================================================
# _extract_handle_from_yaml Tests
# =============================================================================


class TestExtractHandleFromYaml:
    """Tests for extracting handles from various YAML formats."""

    def test_extract_handle_with_at_symbol(self):
        """Test extracting handle with @ symbol in quotes."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml('"@AndrewKislov"')
        assert result == "AndrewKislov"

    def test_extract_handle_single_quotes(self):
        """Test extracting handle with single quotes."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("'@IvanDrobyshev'")
        assert result == "IvanDrobyshev"

    def test_extract_handle_markdown_link(self):
        """Test extracting handle from markdown link format."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("[@alex_named](https://t.me/@alex_named)")
        assert result == "alex_named"

    def test_extract_handle_markdown_link_with_at(self):
        """Test extracting handle from markdown link with @ in display text."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("[@@testuser](https://t.me/testuser)")
        assert result == "@testuser"

    def test_extract_handle_empty_string(self):
        """Test extracting handle from empty string."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("")
        assert result is None

    def test_extract_handle_empty_quotes(self):
        """Test extracting handle from empty quoted value."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml('""')
        assert result is None

    def test_extract_handle_single_empty_quotes(self):
        """Test extracting handle from empty single-quoted value."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("''")
        assert result is None

    def test_extract_handle_plain_at_handle(self):
        """Test extracting plain handle with @ prefix."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("@plainuser")
        assert result == "plainuser"

    def test_extract_handle_plain_without_at(self):
        """Test extracting plain handle without @ prefix."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml("plainuser")
        assert result == "plainuser"

    def test_extract_handle_whitespace(self):
        """Test extracting handle with surrounding whitespace."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml('  "@user"  ')
        assert result == "user"

    def test_extract_handle_none_input(self):
        """Test extracting handle from None input."""
        from src.services.vault_user_service import _extract_handle_from_yaml

        result = _extract_handle_from_yaml(None)
        assert result is None


# =============================================================================
# lookup_telegram_user Tests
# =============================================================================


class TestLookupTelegramUser:
    """Tests for user lookup in vault."""

    def test_lookup_user_found(self, temp_vault_dir, clear_cache):
        """Test looking up a user that exists in vault."""
        from src.services.vault_user_service import lookup_telegram_user

        # Create a note with telegram handle
        note_path = temp_vault_dir / "@Andrew Kislov.md"
        note_path.write_text('''---
telegram: "@AndrewKislov"
---

# Andrew Kislov
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("AndrewKislov")

        assert result == "Andrew Kislov"

    def test_lookup_user_with_at_symbol(self, temp_vault_dir, clear_cache):
        """Test looking up user with @ in query."""
        from src.services.vault_user_service import lookup_telegram_user

        note_path = temp_vault_dir / "@Test User.md"
        note_path.write_text('''---
telegram: "@testuser"
---

# Test User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("@testuser")

        assert result == "Test User"

    def test_lookup_user_case_insensitive(self, temp_vault_dir, clear_cache):
        """Test case-insensitive user lookup."""
        from src.services.vault_user_service import lookup_telegram_user

        note_path = temp_vault_dir / "@John Smith.md"
        note_path.write_text('''---
telegram: "@JohnSmith"
---

# John Smith
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("JOHNSMITH")

        assert result == "John Smith"

    def test_lookup_user_not_found(self, temp_vault_dir, clear_cache):
        """Test looking up user that doesn't exist."""
        from src.services.vault_user_service import lookup_telegram_user

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("nonexistent_user")

        assert result is None

    def test_lookup_user_empty_handle(self, clear_cache):
        """Test looking up with empty handle."""
        from src.services.vault_user_service import lookup_telegram_user

        result = lookup_telegram_user("")
        assert result is None

    def test_lookup_user_none_handle(self, clear_cache):
        """Test looking up with None handle."""
        from src.services.vault_user_service import lookup_telegram_user

        result = lookup_telegram_user(None)
        assert result is None

    def test_lookup_user_vault_path_not_exists(self, clear_cache):
        """Test lookup when vault path doesn't exist."""
        from src.services.vault_user_service import lookup_telegram_user

        fake_path = Path("/nonexistent/path/People")

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=fake_path):
            result = lookup_telegram_user("someuser")

        assert result is None

    def test_lookup_user_markdown_link_format(self, temp_vault_dir, clear_cache):
        """Test lookup with markdown link format in frontmatter."""
        from src.services.vault_user_service import lookup_telegram_user

        note_path = temp_vault_dir / "@Alex Named.md"
        note_path.write_text('''---
telegram: "[@alex_named](https://t.me/@alex_named)"
---

# Alex Named
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("alex_named")

        assert result == "Alex Named"


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    def test_cache_hit(self, temp_vault_dir, clear_cache):
        """Test that cached results are returned."""
        from src.services.vault_user_service import lookup_telegram_user, _user_cache

        note_path = temp_vault_dir / "@Cached User.md"
        note_path.write_text('''---
telegram: "@cacheduser"
---

# Cached User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # First lookup - should populate cache
            result1 = lookup_telegram_user("cacheduser")
            assert result1 == "Cached User"

            # Verify cache is populated
            assert "cacheduser" in _user_cache

            # Second lookup - should use cache (even if we delete the file)
            note_path.unlink()
            result2 = lookup_telegram_user("cacheduser")
            assert result2 == "Cached User"

    def test_cache_expired(self, temp_vault_dir, clear_cache):
        """Test that expired cache entries are refreshed."""
        from src.services.vault_user_service import (
            lookup_telegram_user,
            _user_cache,
            CACHE_TTL_MINUTES,
        )

        note_path = temp_vault_dir / "@Expiring User.md"
        note_path.write_text('''---
telegram: "@expiringuser"
---

# Expiring User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # First lookup
            result1 = lookup_telegram_user("expiringuser")
            assert result1 == "Expiring User"

            # Manually expire cache entry
            _user_cache["expiringuser"] = (
                "Expiring User",
                datetime.now() - timedelta(minutes=CACHE_TTL_MINUTES + 1)
            )

            # Update the note content
            note_path.write_text('''---
telegram: "@expiringuser"
---

# Updated Expiring User
''')

            # Create new note with matching handle but different name
            new_note_path = temp_vault_dir / "@Updated User.md"
            new_note_path.write_text('''---
telegram: "@expiringuser"
---

# Updated User
''')
            note_path.unlink()

            # Lookup should refresh from disk
            result2 = lookup_telegram_user("expiringuser")
            # Should find the updated note
            assert result2 == "Updated User"

    def test_cache_negative_result(self, temp_vault_dir, clear_cache):
        """Test that negative results are cached."""
        from src.services.vault_user_service import lookup_telegram_user, _user_cache

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # Lookup non-existent user
            result = lookup_telegram_user("nonexistent")
            assert result is None

            # Verify None is cached
            assert "nonexistent" in _user_cache
            assert _user_cache["nonexistent"][0] is None


# =============================================================================
# build_forward_context Tests
# =============================================================================


class TestBuildForwardContext:
    """Tests for building forward context strings."""

    def test_forward_from_username_with_vault_match(self, temp_vault_dir, clear_cache):
        """Test forward context when user exists in vault."""
        from src.services.vault_user_service import build_forward_context

        note_path = temp_vault_dir / "@Forwarded User.md"
        note_path.write_text('''---
telegram: "@forwarduser"
---

# Forwarded User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = build_forward_context({
                "forward_from_username": "forwarduser"
            })

        assert result == "Message forwarded from [[@Forwarded User]]:"

    def test_forward_from_username_no_vault_match(self, temp_vault_dir, clear_cache):
        """Test forward context when user not in vault."""
        from src.services.vault_user_service import build_forward_context

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = build_forward_context({
                "forward_from_username": "unknown_user"
            })

        assert result == "Message forwarded from @unknown_user:"

    def test_forward_sender_name_only(self, clear_cache):
        """Test forward context with privacy-protected sender name."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_sender_name": "John Doe"
        })

        assert result == "Message forwarded from John Doe:"

    def test_forward_from_channel_with_link(self, clear_cache):
        """Test forward context from channel with message link."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_chat_title": "Tech News Channel",
            "forward_from_chat_username": "technews",
            "forward_message_id": 12345
        })

        assert result == 'Message forwarded from channel "Tech News Channel" (https://t.me/technews/12345):'

    def test_forward_from_channel_no_link(self, clear_cache):
        """Test forward context from channel without username."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_chat_title": "Private Channel"
        })

        assert result == 'Message forwarded from channel "Private Channel":'

    def test_forward_from_first_name_only(self, clear_cache):
        """Test forward context with only first name."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_first_name": "Alice"
        })

        assert result == "Message forwarded from Alice:"

    def test_forward_empty_info(self, clear_cache):
        """Test forward context with empty info dict."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({})
        assert result is None

    def test_forward_priority_username_over_sender_name(self, temp_vault_dir, clear_cache):
        """Test that username takes priority over sender_name."""
        from src.services.vault_user_service import build_forward_context

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = build_forward_context({
                "forward_from_username": "priorityuser",
                "forward_sender_name": "Should Not Show"
            })

        assert "@priorityuser" in result
        assert "Should Not Show" not in result

    def test_forward_priority_channel_over_first_name(self, clear_cache):
        """Test that channel takes priority over first_name when sender_name absent."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_chat_title": "Priority Channel",
            "forward_from_first_name": "ShouldNotShow"
        })

        assert "Priority Channel" in result
        assert "ShouldNotShow" not in result


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_lookup_handles_read_error(self, temp_vault_dir, clear_cache):
        """Test that file read errors are handled gracefully."""
        from src.services.vault_user_service import lookup_telegram_user

        # Create a note file
        note_path = temp_vault_dir / "@Error User.md"
        note_path.write_text('''---
telegram: "@erroruser"
---
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # Mock the read_text to raise an error
            with patch.object(Path, "read_text", side_effect=PermissionError("Permission denied")):
                # Should not raise, just return None
                result = lookup_telegram_user("erroruser")

        # Note: The actual glob iteration happens before read_text, so this test
        # verifies the exception handling within the loop
        assert result is None

    def test_lookup_handles_invalid_encoding(self, temp_vault_dir, clear_cache):
        """Test that invalid file encoding is handled."""
        from src.services.vault_user_service import lookup_telegram_user

        # Create a file with binary content
        note_path = temp_vault_dir / "@Binary User.md"
        note_path.write_bytes(b'\xff\xfe---\ntelegram: "@binary"\n---')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # Should handle encoding errors gracefully
            result = lookup_telegram_user("binaryuser")

        # Should continue scanning other files (or return None if none match)
        assert result is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_lookup_workflow(self, temp_vault_dir, clear_cache):
        """Test complete workflow from lookup to context building."""
        from src.services.vault_user_service import lookup_telegram_user, build_forward_context

        # Create multiple notes
        (temp_vault_dir / "@Alice Smith.md").write_text('''---
telegram: "@alicesmith"
email: alice@example.com
---

# Alice Smith
''')

        (temp_vault_dir / "@Bob Jones.md").write_text('''---
telegram: "[@bobjones](https://t.me/bobjones)"
---

# Bob Jones
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            # Test lookup
            alice = lookup_telegram_user("alicesmith")
            bob = lookup_telegram_user("bobjones")

            assert alice == "Alice Smith"
            assert bob == "Bob Jones"

            # Test forward context
            forward_alice = build_forward_context({"forward_from_username": "alicesmith"})
            forward_bob = build_forward_context({"forward_from_username": "bobjones"})

            assert forward_alice == "Message forwarded from [[@Alice Smith]]:"
            assert forward_bob == "Message forwarded from [[@Bob Jones]]:"

    def test_multiple_notes_same_handle(self, temp_vault_dir, clear_cache):
        """Test behavior when multiple notes have same handle (first match wins)."""
        from src.services.vault_user_service import lookup_telegram_user

        # Create two notes with same telegram handle (edge case)
        (temp_vault_dir / "@First User.md").write_text('''---
telegram: "@duplicatehandle"
---

# First User
''')

        (temp_vault_dir / "@Second User.md").write_text('''---
telegram: "@duplicatehandle"
---

# Second User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("duplicatehandle")

        # Should return one of them (whichever glob finds first)
        assert result in ["First User", "Second User"]

    def test_notes_without_telegram_field(self, temp_vault_dir, clear_cache):
        """Test that notes without telegram field are skipped."""
        from src.services.vault_user_service import lookup_telegram_user

        # Create note without telegram field
        (temp_vault_dir / "@No Telegram.md").write_text('''---
email: user@example.com
---

# No Telegram
''')

        # Create note with telegram field
        (temp_vault_dir / "@Has Telegram.md").write_text('''---
telegram: "@hastelegram"
---

# Has Telegram
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("hastelegram")

        assert result == "Has Telegram"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_note_filename_without_at_prefix(self, temp_vault_dir, clear_cache):
        """Test that notes without @ prefix in filename are ignored."""
        from src.services.vault_user_service import lookup_telegram_user

        # Note without @ prefix (should be ignored by glob pattern)
        (temp_vault_dir / "Regular Note.md").write_text('''---
telegram: "@regularuser"
---

# Regular Note
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("regularuser")

        # Should not find since filename doesn't match @*.md pattern
        assert result is None

    def test_handle_with_underscore(self, temp_vault_dir, clear_cache):
        """Test handles with underscores."""
        from src.services.vault_user_service import lookup_telegram_user

        (temp_vault_dir / "@Under Score User.md").write_text('''---
telegram: "@under_score_user"
---

# Under Score User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("under_score_user")

        assert result == "Under Score User"

    def test_handle_with_numbers(self, temp_vault_dir, clear_cache):
        """Test handles with numbers."""
        from src.services.vault_user_service import lookup_telegram_user

        (temp_vault_dir / "@User123.md").write_text('''---
telegram: "@user123"
---

# User123
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("user123")

        assert result == "User123"

    def test_frontmatter_with_nested_yaml(self, temp_vault_dir, clear_cache):
        """Test frontmatter with nested YAML structures."""
        from src.services.vault_user_service import lookup_telegram_user

        (temp_vault_dir / "@Nested User.md").write_text('''---
tags:
  - people
  - contact
telegram: "@nesteduser"
social:
  twitter: "@nestedtwitter"
---

# Nested User
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("nesteduser")

        assert result == "Nested User"

    def test_empty_vault_directory(self, temp_vault_dir, clear_cache):
        """Test lookup in empty vault directory."""
        from src.services.vault_user_service import lookup_telegram_user

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("anyuser")

        assert result is None

    def test_note_with_empty_frontmatter(self, temp_vault_dir, clear_cache):
        """Test note with empty frontmatter."""
        from src.services.vault_user_service import lookup_telegram_user

        (temp_vault_dir / "@Empty Frontmatter.md").write_text('''---
---

# Empty Frontmatter
''')

        with patch("src.services.vault_user_service._get_vault_people_path", return_value=temp_vault_dir):
            result = lookup_telegram_user("emptyuser")

        assert result is None

    def test_build_forward_context_all_fields_none(self, clear_cache):
        """Test build_forward_context when all fields are None."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_username": None,
            "forward_sender_name": None,
            "forward_from_chat_title": None,
            "forward_from_first_name": None
        })

        assert result is None

    def test_build_forward_context_empty_strings(self, clear_cache):
        """Test build_forward_context with empty string values."""
        from src.services.vault_user_service import build_forward_context

        result = build_forward_context({
            "forward_from_username": "",
            "forward_sender_name": "",
            "forward_from_chat_title": "",
            "forward_from_first_name": ""
        })

        # Empty username will trigger lookup but return None, falling through to next option
        assert result is None
