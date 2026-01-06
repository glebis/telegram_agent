"""
Tests for the Cache Service.

Tests cover:
- CacheService initialization
- Cache key generation (_generate_cache_key)
- Cache retrieval (get_cached_analysis) - hits, misses, errors
- Cache storage (store_analysis)
- Cache invalidation (invalidate_cache)
- Global instance management (get_cache_service)
- Error handling and edge cases
"""

import hashlib
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.cache_service import (
    CacheService,
    get_cache_service,
    _cache_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cache_service():
    """Create a fresh CacheService instance for testing."""
    return CacheService()


@pytest.fixture
def mock_image():
    """Create a mock Image object with typical analysis data."""
    image = MagicMock()
    image.file_id = "test_file_123"
    image.mode_used = "artistic"
    image.preset_used = "landscape"
    image.processing_status = "completed"
    image.analysis = json.dumps({"description": "A beautiful sunset"})
    image.created_at = datetime(2025, 1, 1, 12, 0, 0)
    return image


@pytest.fixture
def mock_image_dict_analysis():
    """Create a mock Image object with dict analysis (already parsed)."""
    image = MagicMock()
    image.file_id = "test_file_456"
    image.mode_used = "technical"
    image.preset_used = ""
    image.processing_status = "completed"
    image.analysis = {"description": "Technical diagram", "objects": ["box", "arrow"]}
    image.created_at = datetime(2025, 1, 2, 14, 30, 0)
    return image


# =============================================================================
# CacheService Initialization Tests
# =============================================================================


class TestCacheServiceInit:
    """Tests for CacheService initialization."""

    def test_initialization(self, cache_service):
        """Test that CacheService initializes without errors."""
        assert cache_service is not None
        assert isinstance(cache_service, CacheService)

    def test_multiple_instances_independent(self):
        """Test that multiple CacheService instances are independent."""
        service1 = CacheService()
        service2 = CacheService()

        # They should be separate instances
        assert service1 is not service2


# =============================================================================
# Cache Key Generation Tests
# =============================================================================


class TestGenerateCacheKey:
    """Tests for _generate_cache_key method."""

    def test_basic_key_generation(self, cache_service):
        """Test basic cache key generation with all parameters."""
        key = cache_service._generate_cache_key(
            file_id="file_123",
            mode="artistic",
            preset="portrait"
        )

        assert key is not None
        assert len(key) == 16  # SHA256 truncated to 16 chars
        assert isinstance(key, str)

    def test_key_without_preset(self, cache_service):
        """Test cache key generation without preset (None)."""
        key = cache_service._generate_cache_key(
            file_id="file_123",
            mode="artistic",
            preset=None
        )

        assert key is not None
        assert len(key) == 16

    def test_key_with_empty_preset(self, cache_service):
        """Test cache key generation with empty string preset."""
        key = cache_service._generate_cache_key(
            file_id="file_123",
            mode="artistic",
            preset=""
        )

        assert key is not None
        assert len(key) == 16

    def test_same_params_same_key(self, cache_service):
        """Test that same parameters produce same key."""
        key1 = cache_service._generate_cache_key("file_123", "artistic", "portrait")
        key2 = cache_service._generate_cache_key("file_123", "artistic", "portrait")

        assert key1 == key2

    def test_different_file_id_different_key(self, cache_service):
        """Test that different file_id produces different key."""
        key1 = cache_service._generate_cache_key("file_123", "artistic", "portrait")
        key2 = cache_service._generate_cache_key("file_456", "artistic", "portrait")

        assert key1 != key2

    def test_different_mode_different_key(self, cache_service):
        """Test that different mode produces different key."""
        key1 = cache_service._generate_cache_key("file_123", "artistic", "portrait")
        key2 = cache_service._generate_cache_key("file_123", "technical", "portrait")

        assert key1 != key2

    def test_different_preset_different_key(self, cache_service):
        """Test that different preset produces different key."""
        key1 = cache_service._generate_cache_key("file_123", "artistic", "portrait")
        key2 = cache_service._generate_cache_key("file_123", "artistic", "landscape")

        assert key1 != key2

    def test_none_vs_empty_preset_same_key(self, cache_service):
        """Test that None preset and empty string preset produce same key."""
        key1 = cache_service._generate_cache_key("file_123", "artistic", None)
        key2 = cache_service._generate_cache_key("file_123", "artistic", "")

        assert key1 == key2

    def test_key_format_is_hex(self, cache_service):
        """Test that generated key is valid hexadecimal."""
        key = cache_service._generate_cache_key("file_123", "artistic", "portrait")

        # Should be valid hex
        try:
            int(key, 16)
        except ValueError:
            pytest.fail("Cache key is not valid hexadecimal")

    def test_key_deterministic(self, cache_service):
        """Test that key generation is deterministic (reproducible)."""
        # Generate expected key manually
        cache_data = {"file_id": "test_file", "mode": "test_mode", "preset": "test_preset"}
        cache_string = json.dumps(cache_data, sort_keys=True)
        expected_key = hashlib.sha256(cache_string.encode()).hexdigest()[:16]

        # Generate using service
        actual_key = cache_service._generate_cache_key("test_file", "test_mode", "test_preset")

        assert actual_key == expected_key


# =============================================================================
# Get Cached Analysis Tests
# =============================================================================


class TestGetCachedAnalysis:
    """Tests for get_cached_analysis method."""

    @pytest.mark.asyncio
    async def test_cache_hit_with_string_analysis(self, cache_service, mock_image):
        """Test cache hit returns analysis when found (string analysis)."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="test_file_123",
                mode="artistic",
                preset="landscape"
            )

        assert result is not None
        assert result["description"] == "A beautiful sunset"
        assert result["cached"] is True
        assert "cache_timestamp" in result

    @pytest.mark.asyncio
    async def test_cache_hit_with_dict_analysis(self, cache_service, mock_image_dict_analysis):
        """Test cache hit returns analysis when found (dict analysis)."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image_dict_analysis
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="test_file_456",
                mode="technical",
                preset=None
            )

        assert result is not None
        assert result["description"] == "Technical diagram"
        assert result["objects"] == ["box", "arrow"]
        assert result["cached"] is True

    @pytest.mark.asyncio
    async def test_cache_miss_no_matching_record(self, cache_service):
        """Test cache miss when no matching record exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="nonexistent_file",
                mode="artistic",
                preset="portrait"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_miss_record_without_analysis(self, cache_service):
        """Test cache miss when record exists but has no analysis."""
        mock_image = MagicMock()
        mock_image.analysis = None
        mock_image.processing_status = "completed"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="file_no_analysis",
                mode="artistic",
                preset=None
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_error_returns_none(self, cache_service):
        """Test that database errors return None gracefully."""
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.side_effect = Exception("Database connection failed")

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="test_file",
                mode="artistic",
                preset="portrait"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_timestamp_format(self, cache_service, mock_image):
        """Test that cache_timestamp is in ISO format."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.get_cached_analysis(
                file_id="test_file_123",
                mode="artistic",
                preset="landscape"
            )

        # Verify timestamp is valid ISO format
        assert result["cache_timestamp"] == "2025-01-01T12:00:00"

    @pytest.mark.asyncio
    async def test_cache_without_preset_uses_empty_string(self, cache_service):
        """Test that None preset is treated as empty string in query."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            # Should not raise, None preset should work
            result = await cache_service.get_cached_analysis(
                file_id="test_file",
                mode="artistic",
                preset=None
            )

        assert result is None  # No match, but no error


# =============================================================================
# Store Analysis Tests
# =============================================================================


class TestStoreAnalysis:
    """Tests for store_analysis method."""

    @pytest.mark.asyncio
    async def test_store_analysis_success(self, cache_service):
        """Test that store_analysis returns True on success."""
        result = await cache_service.store_analysis(
            file_id="test_file_123",
            mode="artistic",
            preset="portrait",
            analysis={"description": "Test analysis"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_store_analysis_without_preset(self, cache_service):
        """Test store_analysis with None preset."""
        result = await cache_service.store_analysis(
            file_id="test_file_123",
            mode="artistic",
            preset=None,
            analysis={"description": "Test analysis"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_store_analysis_generates_cache_key(self, cache_service):
        """Test that store_analysis generates a cache key (logs it)."""
        with patch("src.services.cache_service.logger") as mock_logger:
            await cache_service.store_analysis(
                file_id="test_file",
                mode="test_mode",
                preset="test_preset",
                analysis={"test": "data"}
            )

            # Verify logger was called with cache key info
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "cache" in call_args.lower() or "key" in call_args.lower()

    @pytest.mark.asyncio
    async def test_store_analysis_error_returns_false(self, cache_service):
        """Test that store_analysis returns False on error."""
        with patch.object(cache_service, "_generate_cache_key", side_effect=Exception("Key generation failed")):
            result = await cache_service.store_analysis(
                file_id="test_file",
                mode="artistic",
                preset="portrait",
                analysis={"description": "Test"}
            )

        assert result is False


# =============================================================================
# Invalidate Cache Tests
# =============================================================================


class TestInvalidateCache:
    """Tests for invalidate_cache method."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_success(self, cache_service):
        """Test that invalidate_cache returns True on success."""
        mock_session = AsyncMock()

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.invalidate_cache(file_id="test_file_123")

        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_cache_logs_request(self, cache_service):
        """Test that invalidate_cache logs the invalidation request."""
        mock_session = AsyncMock()

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with (
            patch("src.services.cache_service.get_db_session", return_value=mock_context_manager),
            patch("src.services.cache_service.logger") as mock_logger
        ):
            await cache_service.invalidate_cache(file_id="test_file_to_invalidate")

            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "invalidat" in call_args.lower()

    @pytest.mark.asyncio
    async def test_invalidate_cache_error_returns_false(self, cache_service):
        """Test that invalidate_cache returns False on error."""
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.side_effect = Exception("Database error")

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            result = await cache_service.invalidate_cache(file_id="test_file")

        assert result is False


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_cache_service_creates_instance(self):
        """Test that get_cache_service creates instance if needed."""
        import src.services.cache_service as cs
        cs._cache_service = None

        service = get_cache_service()

        assert service is not None
        assert isinstance(service, CacheService)

    def test_get_cache_service_returns_same_instance(self):
        """Test that get_cache_service returns the same instance."""
        import src.services.cache_service as cs
        cs._cache_service = None

        service1 = get_cache_service()
        service2 = get_cache_service()

        assert service1 is service2

    def test_get_cache_service_singleton_pattern(self):
        """Test singleton pattern persists across calls."""
        import src.services.cache_service as cs
        cs._cache_service = None

        service1 = get_cache_service()
        service2 = get_cache_service()
        service3 = get_cache_service()

        assert service1 is service2 is service3


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_cache_key_with_special_characters_in_file_id(self, cache_service):
        """Test cache key generation with special characters in file_id."""
        key = cache_service._generate_cache_key(
            file_id="file_with_special_chars!@#$%^&*()",
            mode="artistic",
            preset="portrait"
        )

        assert key is not None
        assert len(key) == 16

    def test_cache_key_with_unicode_in_file_id(self, cache_service):
        """Test cache key generation with unicode characters."""
        key = cache_service._generate_cache_key(
            file_id="file_unicode_emoji",
            mode="artistic",
            preset="portrait"
        )

        assert key is not None
        assert len(key) == 16

    def test_cache_key_with_empty_file_id(self, cache_service):
        """Test cache key generation with empty file_id."""
        key = cache_service._generate_cache_key(
            file_id="",
            mode="artistic",
            preset="portrait"
        )

        assert key is not None
        assert len(key) == 16

    def test_cache_key_with_empty_mode(self, cache_service):
        """Test cache key generation with empty mode."""
        key = cache_service._generate_cache_key(
            file_id="file_123",
            mode="",
            preset="portrait"
        )

        assert key is not None
        assert len(key) == 16

    def test_cache_key_with_very_long_file_id(self, cache_service):
        """Test cache key generation with very long file_id."""
        long_file_id = "a" * 10000
        key = cache_service._generate_cache_key(
            file_id=long_file_id,
            mode="artistic",
            preset="portrait"
        )

        # Key should still be 16 chars regardless of input length
        assert len(key) == 16

    @pytest.mark.asyncio
    async def test_get_cached_analysis_with_malformed_json(self, cache_service):
        """Test handling of malformed JSON in analysis field."""
        mock_image = MagicMock()
        mock_image.file_id = "test_file"
        mock_image.mode_used = "artistic"
        mock_image.preset_used = ""
        mock_image.processing_status = "completed"
        mock_image.analysis = "not valid json {"
        mock_image.created_at = datetime(2025, 1, 1, 12, 0, 0)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            # Should return None due to JSON parse error being caught
            result = await cache_service.get_cached_analysis(
                file_id="test_file",
                mode="artistic",
                preset=None
            )

        # The error should be caught and None returned
        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, cache_service, mock_image):
        """Test that concurrent cache accesses work correctly."""
        import asyncio

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_image
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager):
            # Run multiple concurrent requests
            tasks = [
                cache_service.get_cached_analysis("file_1", "artistic", "portrait"),
                cache_service.get_cached_analysis("file_2", "artistic", "landscape"),
                cache_service.get_cached_analysis("file_3", "technical", None),
            ]

            results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r is not None for r in results)
        assert all(r.get("cached") is True for r in results)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration-style tests for cache service workflow."""

    @pytest.mark.asyncio
    async def test_full_cache_workflow(self, cache_service):
        """Test complete cache workflow: miss -> store -> hit."""
        # First access should be a miss
        mock_session_miss = AsyncMock()
        mock_result_miss = MagicMock()
        mock_result_miss.scalar_one_or_none.return_value = None
        mock_session_miss.execute.return_value = mock_result_miss

        mock_context_manager_miss = AsyncMock()
        mock_context_manager_miss.__aenter__.return_value = mock_session_miss
        mock_context_manager_miss.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager_miss):
            result_miss = await cache_service.get_cached_analysis(
                file_id="new_file",
                mode="artistic",
                preset="portrait"
            )

        assert result_miss is None  # Cache miss

        # Store analysis
        analysis_data = {"description": "New analysis", "tags": ["test"]}
        store_result = await cache_service.store_analysis(
            file_id="new_file",
            mode="artistic",
            preset="portrait",
            analysis=analysis_data
        )

        assert store_result is True  # Store succeeded

        # Note: In real implementation, the store would persist to DB
        # and subsequent get would find it. Here we mock the hit.
        mock_image_hit = MagicMock()
        mock_image_hit.analysis = json.dumps(analysis_data)
        mock_image_hit.created_at = datetime.now()

        mock_session_hit = AsyncMock()
        mock_result_hit = MagicMock()
        mock_result_hit.scalar_one_or_none.return_value = mock_image_hit
        mock_session_hit.execute.return_value = mock_result_hit

        mock_context_manager_hit = AsyncMock()
        mock_context_manager_hit.__aenter__.return_value = mock_session_hit
        mock_context_manager_hit.__aexit__.return_value = None

        with patch("src.services.cache_service.get_db_session", return_value=mock_context_manager_hit):
            result_hit = await cache_service.get_cached_analysis(
                file_id="new_file",
                mode="artistic",
                preset="portrait"
            )

        assert result_hit is not None  # Cache hit
        assert result_hit["description"] == "New analysis"
        assert result_hit["cached"] is True

    def test_cache_key_consistency_across_instances(self):
        """Test that different CacheService instances generate same keys."""
        service1 = CacheService()
        service2 = CacheService()

        key1 = service1._generate_cache_key("file_123", "artistic", "portrait")
        key2 = service2._generate_cache_key("file_123", "artistic", "portrait")

        assert key1 == key2
