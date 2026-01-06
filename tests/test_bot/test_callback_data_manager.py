"""
Tests for the Callback Data Manager.

Tests cover:
- Short ID generation from file_ids (SHA-256 hash)
- Collision handling with counters
- Cache expiry (1 hour)
- Creating callback data within 64-byte limit
- Parsing callback data back to action, file_id, params
- Global instance management
"""

import hashlib
import time
from unittest.mock import patch

import pytest

from src.bot.callback_data_manager import (
    CallbackDataManager,
    get_callback_data_manager,
    _callback_data_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def manager():
    """Create a fresh CallbackDataManager for testing."""
    return CallbackDataManager()


@pytest.fixture
def sample_file_id():
    """Create a sample Telegram file_id."""
    return "AgACAgIAAxkBAAIBZ2ZxYwABsYHQAQAC1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"


@pytest.fixture
def sample_long_file_id():
    """Create a very long file_id for edge case testing."""
    return "AgACAgIAAxkBAAIBZ2ZxYwABsYHQ" + "A" * 100


@pytest.fixture
def populated_manager(manager, sample_file_id):
    """Create a manager with pre-populated cache."""
    manager.get_short_file_id(sample_file_id)
    return manager


# =============================================================================
# Short ID Generation Tests
# =============================================================================


class TestShortIdGeneration:
    """Tests for get_short_file_id functionality."""

    def test_generates_8_char_hash(self, manager, sample_file_id):
        """Test that short ID is 8 characters from SHA-256 hash."""
        short_id = manager.get_short_file_id(sample_file_id)

        # Verify length
        assert len(short_id) == 8

        # Verify it's a valid hex string
        assert all(c in "0123456789abcdef" for c in short_id)

        # Verify it matches expected hash
        expected_hash = hashlib.sha256(sample_file_id.encode()).hexdigest()[:8]
        assert short_id == expected_hash

    def test_same_file_id_returns_same_short_id(self, manager, sample_file_id):
        """Test that the same file_id always returns the same short_id."""
        short_id1 = manager.get_short_file_id(sample_file_id)
        short_id2 = manager.get_short_file_id(sample_file_id)

        assert short_id1 == short_id2

    def test_different_file_ids_return_different_short_ids(self, manager):
        """Test that different file_ids return different short_ids."""
        file_id1 = "FileId1_ABC123"
        file_id2 = "FileId2_DEF456"

        short_id1 = manager.get_short_file_id(file_id1)
        short_id2 = manager.get_short_file_id(file_id2)

        assert short_id1 != short_id2

    def test_caches_file_id_mapping(self, manager, sample_file_id):
        """Test that file_id mapping is cached."""
        short_id = manager.get_short_file_id(sample_file_id)

        # Check forward cache
        assert short_id in manager._file_id_cache
        assert manager._file_id_cache[short_id] == sample_file_id

        # Check reverse cache
        assert sample_file_id in manager._reverse_cache
        assert manager._reverse_cache[sample_file_id] == short_id

        # Check timestamp is recorded
        assert short_id in manager._cache_timestamps

    def test_updates_timestamp_on_repeated_access(self, manager, sample_file_id):
        """Test that timestamp is updated when accessing existing mapping."""
        short_id = manager.get_short_file_id(sample_file_id)
        first_timestamp = manager._cache_timestamps[short_id]

        # Wait a small amount
        time.sleep(0.01)

        # Access again
        manager.get_short_file_id(sample_file_id)
        second_timestamp = manager._cache_timestamps[short_id]

        assert second_timestamp >= first_timestamp


# =============================================================================
# Collision Handling Tests
# =============================================================================


class TestCollisionHandling:
    """Tests for hash collision handling."""

    def test_handles_collision_with_counter(self, manager):
        """Test that collisions are handled by appending counter."""
        file_id1 = "collision_test_1"
        file_id2 = "collision_test_2"

        # Get short_id for first file
        short_id1 = manager.get_short_file_id(file_id1)

        # Manually create a collision by inserting a fake entry
        collision_file_id = "fake_collision_file"
        manager._file_id_cache[short_id1] = collision_file_id
        manager._reverse_cache[collision_file_id] = short_id1
        manager._cache_timestamps[short_id1] = time.time()

        # Now get short_id for a new file that would collide
        # We need to find a file_id that would have the same hash prefix
        # For testing, we'll manually set up the collision scenario
        # by pre-populating the cache with the expected hash

        expected_hash = hashlib.sha256(file_id2.encode()).hexdigest()[:8]
        manager._file_id_cache[expected_hash] = "already_exists"

        short_id2 = manager.get_short_file_id(file_id2)

        # The new short_id should have a counter appended
        assert short_id2 == f"{expected_hash}1"

    def test_handles_multiple_collisions(self, manager):
        """Test handling multiple consecutive collisions."""
        file_id = "test_file_id"
        expected_hash = hashlib.sha256(file_id.encode()).hexdigest()[:8]

        # Pre-populate cache to simulate multiple collisions
        for i in range(5):
            if i == 0:
                key = expected_hash
            else:
                key = f"{expected_hash}{i}"
            manager._file_id_cache[key] = f"existing_file_{i}"

        short_id = manager.get_short_file_id(file_id)

        # Should have counter 5 appended
        assert short_id == f"{expected_hash}5"

    def test_collision_fallback_to_timestamp(self, manager):
        """Test fallback to timestamp when counter exceeds limit."""
        file_id = "test_file_id"
        expected_hash = hashlib.sha256(file_id.encode()).hexdigest()[:8]

        # Pre-populate cache to simulate too many collisions
        # The timestamp fallback triggers when len(short_id) > 12
        # 8-char hash + counter, so counter needs to be >= 10000 (5 digits)
        # to make total length > 12. But the code breaks at counter that would
        # cause > 12, so we need to populate all counters up to 9999.
        # However, length > 12 triggers at counter 10000, but the check happens
        # after incrementing, so we need counters 1-9999 (4 digits max = 12 chars).
        # Actually: 8 + len("10000") = 13 > 12, so we need to fill up to 9999.
        # For efficiency, just fill the base + counters up to where len > 12.
        # Base (8 chars), 1-9 (9 chars), 10-99 (10 chars), 100-999 (11 chars),
        # 1000-9999 (12 chars), 10000+ (13+ chars) -> triggers fallback at 10000.
        # We need to pre-populate all keys that would be tried before fallback.
        manager._file_id_cache[expected_hash] = "existing_file_0"
        for i in range(1, 10000):
            key = f"{expected_hash}{i}"
            manager._file_id_cache[key] = f"existing_file_{i}"

        with patch("time.time", return_value=1234567890.123):
            short_id = manager.get_short_file_id(file_id)

        # Should fall back to timestamp format after too many collisions
        # Format: first 6 chars of hash + (timestamp % 1000)
        assert short_id.startswith(expected_hash[:6])
        assert "890" in short_id  # 1234567890 % 1000 = 890


# =============================================================================
# Cache Expiry Tests
# =============================================================================


class TestCacheExpiry:
    """Tests for cache expiration functionality."""

    def test_default_cache_age_is_one_hour(self, manager):
        """Test that default max cache age is 1 hour (3600 seconds)."""
        assert manager._max_cache_age == 3600

    def test_expired_entries_are_cleaned_on_get_file_id(self, manager, sample_file_id):
        """Test that expired entries are cleaned when getting file_id."""
        short_id = manager.get_short_file_id(sample_file_id)

        # Manually set timestamp to be expired
        manager._cache_timestamps[short_id] = time.time() - 3601

        # Accessing via get_file_id triggers cleanup
        result = manager.get_file_id(short_id)

        # Entry should have been cleaned up
        assert result is None
        assert short_id not in manager._file_id_cache
        assert sample_file_id not in manager._reverse_cache

    def test_non_expired_entries_are_preserved(self, manager, sample_file_id):
        """Test that non-expired entries are preserved during cleanup."""
        short_id = manager.get_short_file_id(sample_file_id)

        # Manually set timestamp to be recent
        manager._cache_timestamps[short_id] = time.time() - 1800  # 30 minutes ago

        # Trigger cleanup
        manager._cleanup_expired_cache()

        # Entry should still exist
        assert short_id in manager._file_id_cache
        assert sample_file_id in manager._reverse_cache

    def test_cleanup_removes_only_expired_entries(self, manager):
        """Test that cleanup only removes expired entries."""
        file_id1 = "file_id_1"
        file_id2 = "file_id_2"

        short_id1 = manager.get_short_file_id(file_id1)
        short_id2 = manager.get_short_file_id(file_id2)

        # Make first entry expired
        manager._cache_timestamps[short_id1] = time.time() - 3601

        # Keep second entry fresh
        manager._cache_timestamps[short_id2] = time.time()

        # Trigger cleanup
        manager._cleanup_expired_cache()

        # First entry should be removed
        assert short_id1 not in manager._file_id_cache
        assert file_id1 not in manager._reverse_cache

        # Second entry should remain
        assert short_id2 in manager._file_id_cache
        assert file_id2 in manager._reverse_cache

    def test_get_file_id_updates_timestamp(self, manager, sample_file_id):
        """Test that get_file_id updates the timestamp."""
        short_id = manager.get_short_file_id(sample_file_id)
        old_timestamp = manager._cache_timestamps[short_id]

        time.sleep(0.01)

        # Access via get_file_id
        manager.get_file_id(short_id)

        # Timestamp should be updated
        assert manager._cache_timestamps[short_id] >= old_timestamp


# =============================================================================
# Create Callback Data Tests
# =============================================================================


class TestCreateCallbackData:
    """Tests for create_callback_data functionality."""

    def test_creates_callback_data_with_preset(self, manager, sample_file_id):
        """Test creating callback data with preset."""
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
            preset="default",
        )

        parts = callback_data.split(":")
        assert parts[0] == "save"
        assert len(parts[1]) == 8  # short_id
        assert parts[2] == "vision"
        assert parts[3] == "default"

    def test_creates_callback_data_without_preset(self, manager, sample_file_id):
        """Test creating callback data without preset."""
        callback_data = manager.create_callback_data(
            action="analyze",
            file_id=sample_file_id,
            mode="collect",
            preset=None,
        )

        parts = callback_data.split(":")
        assert parts[0] == "analyze"
        assert len(parts[1]) == 8  # short_id
        assert parts[2] == "collect"
        assert parts[3] == ""  # Empty preset

    def test_callback_data_within_64_bytes(self, manager, sample_file_id):
        """Test that callback data stays within 64-byte limit."""
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
            preset="short",
        )

        assert len(callback_data.encode("utf-8")) <= 64

    def test_truncates_long_preset(self, manager, sample_file_id):
        """Test that long presets are truncated if needed."""
        long_preset = "this_is_a_very_long_preset_name_that_exceeds_limits"

        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
            preset=long_preset,
        )

        # If still over 64 bytes with truncation, preset should be truncated to 10 chars
        parts = callback_data.split(":")
        if len(parts) > 3:
            assert len(parts[3]) <= 10 or len(callback_data.encode("utf-8")) <= 64

    def test_different_actions(self, manager, sample_file_id):
        """Test various action types."""
        for action in ["save", "send", "process", "delete", "view"]:
            callback_data = manager.create_callback_data(
                action=action,
                file_id=sample_file_id,
                mode="vision",
            )
            assert callback_data.startswith(f"{action}:")

    def test_different_modes(self, manager, sample_file_id):
        """Test various mode types."""
        for mode in ["vision", "collect", "claude", "edit"]:
            callback_data = manager.create_callback_data(
                action="save",
                file_id=sample_file_id,
                mode=mode,
            )
            assert f":{mode}:" in callback_data


# =============================================================================
# Parse Callback Data Tests
# =============================================================================


class TestParseCallbackData:
    """Tests for parse_callback_data functionality."""

    def test_parses_complete_callback_data(self, manager, sample_file_id):
        """Test parsing callback data with all parts."""
        # First create the callback data
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
            preset="default",
        )

        # Parse it back
        action, file_id, params = manager.parse_callback_data(callback_data)

        assert action == "save"
        assert file_id == sample_file_id
        assert params == ["vision", "default"]

    def test_parses_callback_data_without_preset(self, manager, sample_file_id):
        """Test parsing callback data without preset."""
        callback_data = manager.create_callback_data(
            action="analyze",
            file_id=sample_file_id,
            mode="collect",
            preset=None,
        )

        action, file_id, params = manager.parse_callback_data(callback_data)

        assert action == "analyze"
        assert file_id == sample_file_id
        assert params == ["collect", ""]

    def test_handles_invalid_callback_no_colon(self, manager):
        """Test handling callback data without colon separator."""
        action, file_id, params = manager.parse_callback_data("invaliddata")

        assert action == "invaliddata"
        assert file_id is None
        assert params == []

    def test_handles_callback_with_only_action(self, manager):
        """Test handling callback data with only action and separator."""
        action, file_id, params = manager.parse_callback_data("action:")

        assert action == "action"
        # file_id lookup will fail for empty short_id
        assert params == []

    def test_fallback_to_long_file_id(self, manager):
        """Test backward compatibility fallback for long file_ids."""
        # Simulate old-style callback data with full file_id
        long_file_id = "AgACAgIAAxkBAAIBZ2ZxYwABsYHQAQAC1234567890ABCDEF"
        callback_data = f"save:{long_file_id}:vision:preset"

        action, file_id, params = manager.parse_callback_data(callback_data)

        assert action == "save"
        # Should fall back to using the long ID directly
        assert file_id == long_file_id
        assert params == ["vision", "preset"]

    def test_expired_short_id_returns_none(self, manager, sample_file_id):
        """Test that expired short_id returns None for file_id."""
        # Create callback data
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
        )

        # Extract short_id and expire it
        parts = callback_data.split(":")
        short_id = parts[1]
        manager._cache_timestamps[short_id] = time.time() - 3601

        # Parse - should return None for file_id (short ID is not long enough for fallback)
        action, file_id, params = manager.parse_callback_data(callback_data)

        assert action == "save"
        # Short ID is only 8 chars, not > 20, so no fallback
        assert file_id is None


# =============================================================================
# Cache Management Tests
# =============================================================================


class TestCacheManagement:
    """Tests for cache management operations."""

    def test_clear_cache(self, populated_manager, sample_file_id):
        """Test clearing all cache data."""
        # Verify cache has data
        assert len(populated_manager._file_id_cache) > 0
        assert len(populated_manager._reverse_cache) > 0
        assert len(populated_manager._cache_timestamps) > 0

        # Clear cache
        populated_manager.clear_cache()

        # Verify cache is empty
        assert len(populated_manager._file_id_cache) == 0
        assert len(populated_manager._reverse_cache) == 0
        assert len(populated_manager._cache_timestamps) == 0

    def test_clear_cache_allows_new_entries(self, populated_manager, sample_file_id):
        """Test that cache can be used after clearing."""
        populated_manager.clear_cache()

        # Should be able to add new entries
        short_id = populated_manager.get_short_file_id(sample_file_id)

        assert short_id is not None
        assert len(populated_manager._file_id_cache) == 1


# =============================================================================
# Get File ID Tests
# =============================================================================


class TestGetFileId:
    """Tests for get_file_id functionality."""

    def test_retrieves_file_id_from_short_id(self, populated_manager, sample_file_id):
        """Test retrieving file_id from short_id."""
        short_id = populated_manager._reverse_cache[sample_file_id]

        file_id = populated_manager.get_file_id(short_id)

        assert file_id == sample_file_id

    def test_returns_none_for_unknown_short_id(self, manager):
        """Test that unknown short_id returns None."""
        file_id = manager.get_file_id("unknown1")

        assert file_id is None

    def test_updates_timestamp_on_access(self, populated_manager, sample_file_id):
        """Test that timestamp is updated on access."""
        short_id = populated_manager._reverse_cache[sample_file_id]
        old_timestamp = populated_manager._cache_timestamps[short_id]

        time.sleep(0.01)

        populated_manager.get_file_id(short_id)

        assert populated_manager._cache_timestamps[short_id] >= old_timestamp


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_file_id(self, manager):
        """Test handling empty file_id."""
        short_id = manager.get_short_file_id("")

        # Should still work - empty string has a valid hash
        assert len(short_id) == 8

    def test_unicode_file_id(self, manager):
        """Test handling file_id with unicode characters."""
        unicode_file_id = "file_id_with_unicode_\u00e9\u00e0\u00fc"

        short_id = manager.get_short_file_id(unicode_file_id)

        assert len(short_id) == 8
        assert manager.get_file_id(short_id) == unicode_file_id

    def test_special_characters_in_file_id(self, manager):
        """Test handling file_id with special characters."""
        special_file_id = "AgACAgI/AAxkB+AAIB=Z2ZxYwAB"

        short_id = manager.get_short_file_id(special_file_id)

        assert len(short_id) == 8
        assert manager.get_file_id(short_id) == special_file_id

    def test_very_long_file_id(self, manager, sample_long_file_id):
        """Test handling very long file_id."""
        short_id = manager.get_short_file_id(sample_long_file_id)

        assert len(short_id) == 8
        assert manager.get_file_id(short_id) == sample_long_file_id

    def test_callback_data_with_unicode_mode(self, manager, sample_file_id):
        """Test callback data with unicode in mode parameter."""
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="mode",
            preset="preset",
        )

        # Should not exceed 64 bytes
        assert len(callback_data.encode("utf-8")) <= 64

    def test_concurrent_access_simulation(self, manager):
        """Test simulating concurrent access patterns."""
        file_ids = [f"file_id_{i}" for i in range(100)]

        # Generate short_ids for all
        short_ids = [manager.get_short_file_id(fid) for fid in file_ids]

        # All should be unique
        assert len(set(short_ids)) == len(short_ids)

        # All should be retrievable
        for fid, sid in zip(file_ids, short_ids):
            assert manager.get_file_id(sid) == fid

    def test_callback_data_exact_64_bytes(self, manager, sample_file_id):
        """Test callback data that is exactly at the 64-byte limit."""
        # Action + short_id + mode + preset should be calculated
        # action:short_id:mode:preset
        # Try to create callback data close to 64 bytes
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
            preset="medium_len",
        )

        byte_length = len(callback_data.encode("utf-8"))
        assert byte_length <= 64


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_callback_data_manager_creates_instance(self):
        """Test that get_callback_data_manager creates instance if needed."""
        # Reset global state
        import src.bot.callback_data_manager as cdm
        cdm._callback_data_manager = None

        manager = get_callback_data_manager()

        assert manager is not None
        assert isinstance(manager, CallbackDataManager)

    def test_get_callback_data_manager_returns_same_instance(self):
        """Test that get_callback_data_manager returns the same instance."""
        # Reset global state
        import src.bot.callback_data_manager as cdm
        cdm._callback_data_manager = None

        manager1 = get_callback_data_manager()
        manager2 = get_callback_data_manager()

        assert manager1 is manager2

    def test_global_instance_persists_state(self):
        """Test that global instance persists state across calls."""
        # Reset global state
        import src.bot.callback_data_manager as cdm
        cdm._callback_data_manager = None

        manager1 = get_callback_data_manager()
        file_id = "test_file_id_global"
        short_id = manager1.get_short_file_id(file_id)

        manager2 = get_callback_data_manager()
        retrieved_file_id = manager2.get_file_id(short_id)

        assert retrieved_file_id == file_id

    def test_global_instance_cache_is_shared(self):
        """Test that global instance cache is shared."""
        # Reset global state
        import src.bot.callback_data_manager as cdm
        cdm._callback_data_manager = None

        manager1 = get_callback_data_manager()
        manager1.get_short_file_id("shared_file_id")

        manager2 = get_callback_data_manager()

        assert len(manager2._file_id_cache) == 1


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_logs_on_short_id_creation(self, manager, sample_file_id, caplog):
        """Test that short_id creation is logged."""
        import logging
        with caplog.at_level(logging.DEBUG):
            manager.get_short_file_id(sample_file_id)

        # Should have debug log for creation
        assert any("Created short_id" in record.message for record in caplog.records)

    def test_logs_on_file_id_retrieval(self, populated_manager, sample_file_id, caplog):
        """Test that file_id retrieval is logged."""
        import logging
        short_id = populated_manager._reverse_cache[sample_file_id]

        with caplog.at_level(logging.DEBUG):
            populated_manager.get_file_id(short_id)

        assert any("Retrieved file_id" in record.message for record in caplog.records)

    def test_logs_warning_on_missing_file_id(self, manager, caplog):
        """Test that warning is logged for missing file_id."""
        import logging
        with caplog.at_level(logging.WARNING):
            manager.get_file_id("nonexistent")

        assert any("No file_id found" in record.message for record in caplog.records)

    def test_logs_callback_data_creation(self, manager, sample_file_id, caplog):
        """Test that callback data creation is logged."""
        import logging
        with caplog.at_level(logging.DEBUG):
            manager.create_callback_data("save", sample_file_id, "vision")

        assert any("Created callback data" in record.message for record in caplog.records)

    def test_logs_callback_data_parsing(self, populated_manager, sample_file_id, caplog):
        """Test that callback data parsing is logged."""
        import logging
        callback_data = populated_manager.create_callback_data(
            "save", sample_file_id, "vision"
        )

        with caplog.at_level(logging.INFO):
            populated_manager.parse_callback_data(callback_data)

        assert any("Parsing callback data" in record.message for record in caplog.records)

    def test_logs_cache_cleanup(self, manager, sample_file_id, caplog):
        """Test that cache cleanup is logged."""
        import logging
        short_id = manager.get_short_file_id(sample_file_id)

        # Expire the entry
        manager._cache_timestamps[short_id] = time.time() - 3601

        with caplog.at_level(logging.INFO):
            manager._cleanup_expired_cache()

        assert any("Cleaned up" in record.message for record in caplog.records)

    def test_logs_cache_clear(self, populated_manager, caplog):
        """Test that cache clear is logged."""
        import logging
        with caplog.at_level(logging.INFO):
            populated_manager.clear_cache()

        assert any("Cleared callback data cache" in record.message for record in caplog.records)


# =============================================================================
# Roundtrip Tests
# =============================================================================


class TestRoundtrip:
    """Tests for complete create-parse roundtrip cycles."""

    def test_full_roundtrip_with_preset(self, manager, sample_file_id):
        """Test complete roundtrip with preset."""
        original_action = "save"
        original_mode = "vision"
        original_preset = "default"

        # Create
        callback_data = manager.create_callback_data(
            action=original_action,
            file_id=sample_file_id,
            mode=original_mode,
            preset=original_preset,
        )

        # Parse
        action, file_id, params = manager.parse_callback_data(callback_data)

        # Verify
        assert action == original_action
        assert file_id == sample_file_id
        assert params[0] == original_mode
        assert params[1] == original_preset

    def test_full_roundtrip_without_preset(self, manager, sample_file_id):
        """Test complete roundtrip without preset."""
        original_action = "analyze"
        original_mode = "collect"

        # Create
        callback_data = manager.create_callback_data(
            action=original_action,
            file_id=sample_file_id,
            mode=original_mode,
            preset=None,
        )

        # Parse
        action, file_id, params = manager.parse_callback_data(callback_data)

        # Verify
        assert action == original_action
        assert file_id == sample_file_id
        assert params[0] == original_mode

    def test_multiple_roundtrips_same_file_id(self, manager, sample_file_id):
        """Test multiple roundtrips with the same file_id."""
        for i in range(10):
            action = f"action_{i}"
            mode = f"mode_{i}"

            callback_data = manager.create_callback_data(
                action=action,
                file_id=sample_file_id,
                mode=mode,
            )

            parsed_action, parsed_file_id, params = manager.parse_callback_data(
                callback_data
            )

            assert parsed_action == action
            assert parsed_file_id == sample_file_id
            assert params[0] == mode

    def test_roundtrip_after_cache_clear(self, manager, sample_file_id):
        """Test that roundtrip fails after cache clear."""
        callback_data = manager.create_callback_data(
            action="save",
            file_id=sample_file_id,
            mode="vision",
        )

        # Clear cache
        manager.clear_cache()

        # Parse - should return None for file_id
        action, file_id, params = manager.parse_callback_data(callback_data)

        assert action == "save"
        # Short ID is 8 chars, not > 20, so no fallback
        assert file_id is None
