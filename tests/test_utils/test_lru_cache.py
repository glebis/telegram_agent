"""
Tests for the LRU Cache utility.

Tests cover:
- Basic cache operations (get, set, contains, pop, clear)
- LRU eviction behavior (least recently used items evicted first)
- Cache capacity and overflow handling
- Dictionary-style access (__getitem__, __setitem__)
- Thread safety for concurrent operations
- Edge cases (empty cache, single item, boundary conditions)
"""

import threading

import pytest

from src.utils.lru_cache import LRUCache

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_cache():
    """Create an empty cache with default size."""
    return LRUCache[str, str](max_size=10000)


@pytest.fixture
def small_cache():
    """Create a small cache for testing eviction."""
    return LRUCache[str, int](max_size=3)


@pytest.fixture
def populated_cache():
    """Create a cache pre-populated with items."""
    cache = LRUCache[str, int](max_size=5)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    return cache


# =============================================================================
# Initialization Tests
# =============================================================================


class TestLRUCacheInit:
    """Tests for LRUCache initialization."""

    def test_init_with_default_size(self):
        """Test cache initializes with default max_size of 10000."""
        cache = LRUCache()
        assert len(cache) == 0

    def test_init_with_custom_size(self):
        """Test cache initializes with custom max_size."""
        cache = LRUCache(max_size=5)
        assert len(cache) == 0

    def test_init_creates_empty_cache(self, empty_cache):
        """Test that new cache starts empty."""
        assert len(empty_cache) == 0
        assert empty_cache.items() == []


# =============================================================================
# Basic Set Operation Tests
# =============================================================================


class TestSetOperation:
    """Tests for cache set() method."""

    def test_set_single_item(self, empty_cache):
        """Test setting a single item in cache."""
        empty_cache.set("key1", "value1")

        assert len(empty_cache) == 1
        assert "key1" in empty_cache

    def test_set_multiple_items(self, empty_cache):
        """Test setting multiple items in cache."""
        empty_cache.set("key1", "value1")
        empty_cache.set("key2", "value2")
        empty_cache.set("key3", "value3")

        assert len(empty_cache) == 3

    def test_set_overwrites_existing_key(self, empty_cache):
        """Test that setting existing key overwrites value."""
        empty_cache.set("key1", "old_value")
        empty_cache.set("key1", "new_value")

        assert len(empty_cache) == 1
        assert empty_cache.get("key1") == "new_value"

    def test_set_moves_existing_key_to_end(self, small_cache):
        """Test that setting existing key moves it to most recently used."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Update 'a' - should move to end
        small_cache.set("a", 10)

        # Add 'd' - should evict 'b' (now oldest), not 'a'
        small_cache.set("d", 4)

        assert "a" in small_cache
        assert "b" not in small_cache
        assert "c" in small_cache
        assert "d" in small_cache

    def test_setitem_syntax(self, empty_cache):
        """Test dictionary-style item assignment."""
        empty_cache["key1"] = "value1"

        assert len(empty_cache) == 1
        assert empty_cache.get("key1") == "value1"


# =============================================================================
# Basic Get Operation Tests
# =============================================================================


class TestGetOperation:
    """Tests for cache get() method."""

    def test_get_existing_item(self, populated_cache):
        """Test getting an existing item."""
        value = populated_cache.get("a")
        assert value == 1

    def test_get_nonexistent_item_returns_none(self, populated_cache):
        """Test getting nonexistent item returns None by default."""
        value = populated_cache.get("nonexistent")
        assert value is None

    def test_get_nonexistent_item_returns_default(self, populated_cache):
        """Test getting nonexistent item returns custom default."""
        value = populated_cache.get("nonexistent", default=-1)
        assert value == -1

    def test_get_moves_item_to_end(self, small_cache):
        """Test that getting an item moves it to most recently used."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Access 'a' - should move to end
        small_cache.get("a")

        # Add 'd' - should evict 'b' (now oldest), not 'a'
        small_cache.set("d", 4)

        assert "a" in small_cache
        assert "b" not in small_cache
        assert "c" in small_cache
        assert "d" in small_cache

    def test_getitem_syntax_existing(self, populated_cache):
        """Test dictionary-style item access for existing item."""
        value = populated_cache["a"]
        assert value == 1

    def test_getitem_syntax_nonexistent_raises(self, populated_cache):
        """Test dictionary-style access raises KeyError for nonexistent."""
        with pytest.raises(KeyError):
            _ = populated_cache["nonexistent"]

    def test_getitem_moves_item_to_end(self, small_cache):
        """Test that __getitem__ moves item to most recently used."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Access 'a' via __getitem__
        _ = small_cache["a"]

        # Add 'd' - should evict 'b', not 'a'
        small_cache.set("d", 4)

        assert "a" in small_cache
        assert "b" not in small_cache


# =============================================================================
# Contains Operation Tests
# =============================================================================


class TestContainsOperation:
    """Tests for cache __contains__ method."""

    def test_contains_existing_item(self, populated_cache):
        """Test that contains returns True for existing item."""
        assert "a" in populated_cache
        assert "b" in populated_cache
        assert "c" in populated_cache

    def test_contains_nonexistent_item(self, populated_cache):
        """Test that contains returns False for nonexistent item."""
        assert "nonexistent" not in populated_cache
        assert "d" not in populated_cache

    def test_contains_on_empty_cache(self, empty_cache):
        """Test contains on empty cache always returns False."""
        assert "anything" not in empty_cache


# =============================================================================
# Pop Operation Tests
# =============================================================================


class TestPopOperation:
    """Tests for cache pop() method."""

    def test_pop_existing_item(self, populated_cache):
        """Test popping an existing item removes and returns it."""
        value = populated_cache.pop("a")

        assert value == 1
        assert "a" not in populated_cache
        assert len(populated_cache) == 2

    def test_pop_nonexistent_returns_none(self, populated_cache):
        """Test popping nonexistent item returns None by default."""
        value = populated_cache.pop("nonexistent")
        assert value is None

    def test_pop_nonexistent_returns_default(self, populated_cache):
        """Test popping nonexistent item returns custom default."""
        value = populated_cache.pop("nonexistent", default=-999)
        assert value == -999

    def test_pop_all_items(self, populated_cache):
        """Test popping all items empties the cache."""
        populated_cache.pop("a")
        populated_cache.pop("b")
        populated_cache.pop("c")

        assert len(populated_cache) == 0


# =============================================================================
# Clear Operation Tests
# =============================================================================


class TestClearOperation:
    """Tests for cache clear() method."""

    def test_clear_populated_cache(self, populated_cache):
        """Test clearing a populated cache."""
        populated_cache.clear()

        assert len(populated_cache) == 0
        assert "a" not in populated_cache
        assert "b" not in populated_cache
        assert "c" not in populated_cache

    def test_clear_empty_cache(self, empty_cache):
        """Test clearing an already empty cache is safe."""
        empty_cache.clear()
        assert len(empty_cache) == 0

    def test_cache_usable_after_clear(self, populated_cache):
        """Test that cache is usable after clearing."""
        populated_cache.clear()
        populated_cache.set("new_key", 100)

        assert len(populated_cache) == 1
        assert populated_cache.get("new_key") == 100


# =============================================================================
# Length Operation Tests
# =============================================================================


class TestLengthOperation:
    """Tests for cache __len__ method."""

    def test_len_empty_cache(self, empty_cache):
        """Test length of empty cache is 0."""
        assert len(empty_cache) == 0

    def test_len_after_inserts(self, empty_cache):
        """Test length increases with inserts."""
        assert len(empty_cache) == 0

        empty_cache.set("a", 1)
        assert len(empty_cache) == 1

        empty_cache.set("b", 2)
        assert len(empty_cache) == 2

    def test_len_after_overwrite(self, empty_cache):
        """Test length doesn't increase on overwrite."""
        empty_cache.set("a", 1)
        empty_cache.set("a", 2)

        assert len(empty_cache) == 1

    def test_len_after_eviction(self, small_cache):
        """Test length remains at max after eviction."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)
        small_cache.set("d", 4)  # Should evict 'a'

        assert len(small_cache) == 3


# =============================================================================
# Items Operation Tests
# =============================================================================


class TestItemsOperation:
    """Tests for cache items() method."""

    def test_items_empty_cache(self, empty_cache):
        """Test items() on empty cache returns empty list."""
        items = empty_cache.items()

        assert isinstance(items, list)
        assert len(items) == 0

    def test_items_returns_snapshot(self, populated_cache):
        """Test items() returns a snapshot copy."""
        items1 = populated_cache.items()
        items2 = populated_cache.items()

        # Should be different list objects
        assert items1 is not items2
        # But contain same content
        assert items1 == items2

    def test_items_contains_all_entries(self, populated_cache):
        """Test items() contains all cache entries."""
        items = populated_cache.items()

        assert len(items) == 3
        keys = [k for k, v in items]
        assert "a" in keys
        assert "b" in keys
        assert "c" in keys

    def test_items_order_reflects_usage(self, small_cache):
        """Test items() order reflects LRU order (oldest first)."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        items = small_cache.items()
        keys = [k for k, v in items]

        # OrderedDict maintains insertion order, oldest first
        assert keys == ["a", "b", "c"]

        # Access 'a' to move to end
        small_cache.get("a")

        items_after = small_cache.items()
        keys_after = [k for k, v in items_after]

        # Now 'a' should be at the end
        assert keys_after == ["b", "c", "a"]


# =============================================================================
# LRU Eviction Tests
# =============================================================================


class TestLRUEviction:
    """Tests for LRU eviction behavior."""

    def test_evicts_oldest_on_overflow(self, small_cache):
        """Test that oldest item is evicted when cache overflows."""
        small_cache.set("a", 1)  # Oldest
        small_cache.set("b", 2)
        small_cache.set("c", 3)
        small_cache.set("d", 4)  # This should evict 'a'

        assert "a" not in small_cache
        assert "b" in small_cache
        assert "c" in small_cache
        assert "d" in small_cache

    def test_evicts_multiple_on_large_overflow(self):
        """Test multiple evictions when adding beyond capacity."""
        cache = LRUCache[str, int](max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Evicts 'a'
        cache.set("d", 4)  # Evicts 'b'

        assert len(cache) == 2
        assert "a" not in cache
        assert "b" not in cache
        assert "c" in cache
        assert "d" in cache

    def test_access_updates_usage_order(self, small_cache):
        """Test that accessing items updates their position."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Access 'a' to make it most recently used
        small_cache.get("a")

        # Add two more items
        small_cache.set("d", 4)  # Evicts 'b'
        small_cache.set("e", 5)  # Evicts 'c'

        assert "a" in small_cache  # Was accessed, so survived
        assert "b" not in small_cache
        assert "c" not in small_cache
        assert "d" in small_cache
        assert "e" in small_cache

    def test_update_updates_usage_order(self, small_cache):
        """Test that updating items updates their position."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Update 'a' to make it most recently used
        small_cache.set("a", 100)

        # Add two more items
        small_cache.set("d", 4)  # Evicts 'b'
        small_cache.set("e", 5)  # Evicts 'c'

        assert "a" in small_cache
        assert small_cache.get("a") == 100  # Updated value
        assert "b" not in small_cache
        assert "c" not in small_cache

    def test_max_size_one(self):
        """Test cache with max_size of 1."""
        cache = LRUCache[str, int](max_size=1)

        cache.set("a", 1)
        assert len(cache) == 1
        assert "a" in cache

        cache.set("b", 2)
        assert len(cache) == 1
        assert "a" not in cache
        assert "b" in cache

    def test_eviction_order_complex_scenario(self, small_cache):
        """Test complex eviction scenario with mixed operations."""
        # Insert a, b, c
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Access b (order now: a, c, b)
        small_cache.get("b")

        # Add d (evicts a, order now: c, b, d)
        small_cache.set("d", 4)
        assert "a" not in small_cache

        # Access c (order now: b, d, c)
        small_cache.get("c")

        # Add e (evicts b, order now: d, c, e)
        small_cache.set("e", 5)
        assert "b" not in small_cache

        assert "c" in small_cache
        assert "d" in small_cache
        assert "e" in small_cache


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_cache_operations(self, empty_cache):
        """Test all operations on empty cache."""
        assert len(empty_cache) == 0
        assert empty_cache.get("any") is None
        assert empty_cache.pop("any") is None
        assert "any" not in empty_cache
        assert empty_cache.items() == []

        # Should not raise
        empty_cache.clear()

    def test_none_value(self, empty_cache):
        """Test storing None as a value."""
        empty_cache.set("key", None)

        assert "key" in empty_cache
        assert empty_cache.get("key") is None
        # Get with default should still return None (the stored value)
        assert empty_cache.get("key", "default") is None

    def test_various_key_types(self):
        """Test cache with various key types."""
        cache = LRUCache[tuple, str](max_size=10)

        cache.set((1, 2), "tuple_key")
        cache.set((3, 4, 5), "another_tuple")

        assert cache.get((1, 2)) == "tuple_key"
        assert cache.get((3, 4, 5)) == "another_tuple"

    def test_various_value_types(self, empty_cache):
        """Test cache with various value types."""
        empty_cache.set("int", 42)
        empty_cache.set("str", "hello")
        empty_cache.set("list", [1, 2, 3])
        empty_cache.set("dict", {"nested": "dict"})

        assert empty_cache.get("int") == 42
        assert empty_cache.get("str") == "hello"
        assert empty_cache.get("list") == [1, 2, 3]
        assert empty_cache.get("dict") == {"nested": "dict"}

    def test_get_does_not_affect_nonexistent_key(self, small_cache):
        """Test that getting nonexistent key doesn't affect cache state."""
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)

        # Get nonexistent key
        result = small_cache.get("nonexistent")
        assert result is None

        # Cache should be unchanged
        assert len(small_cache) == 3
        items = small_cache.items()
        keys = [k for k, v in items]
        assert keys == ["a", "b", "c"]

    def test_same_key_value_overwrite(self, empty_cache):
        """Test overwriting with same value."""
        empty_cache.set("key", "value")
        empty_cache.set("key", "value")

        assert len(empty_cache) == 1
        assert empty_cache.get("key") == "value"

    def test_large_number_of_items(self):
        """Test cache with many items."""
        cache = LRUCache[int, int](max_size=100)

        for i in range(200):
            cache.set(i, i * 10)

        # Should only have last 100 items
        assert len(cache) == 100

        # First 100 should be evicted
        for i in range(100):
            assert i not in cache

        # Last 100 should be present
        for i in range(100, 200):
            assert i in cache
            assert cache.get(i) == i * 10


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_reads(self, populated_cache):
        """Test concurrent read operations."""
        errors = []
        results = []

        def reader(key):
            try:
                for _ in range(100):
                    value = populated_cache.get(key)
                    results.append(value)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader, args=(key,))
            for key in ["a", "b", "c"]
            for _ in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r in [1, 2, 3, None] for r in results)

    def test_concurrent_writes(self):
        """Test concurrent write operations."""
        cache = LRUCache[int, int](max_size=100)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    cache.set(start + i, i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i * 1000,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Cache should still be bounded
        assert len(cache) <= 100

    def test_concurrent_reads_and_writes(self):
        """Test concurrent read and write operations."""
        cache = LRUCache[int, int](max_size=50)
        errors = []

        # Pre-populate
        for i in range(50):
            cache.set(i, i)

        def reader():
            try:
                for _ in range(100):
                    for key in range(60):
                        cache.get(key)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    cache.set(i % 60, i)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache) <= 50

    def test_concurrent_mixed_operations(self):
        """Test concurrent mixed operations (get, set, pop, clear)."""
        cache = LRUCache[int, int](max_size=20)
        errors = []

        def mixed_ops(thread_id):
            try:
                for i in range(50):
                    key = (thread_id * 100) + (i % 30)
                    op = i % 4
                    if op == 0:
                        cache.set(key, i)
                    elif op == 1:
                        cache.get(key)
                    elif op == 2:
                        cache.pop(key)
                    else:
                        len(cache)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mixed_ops, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache) <= 20

    def test_concurrent_clear(self):
        """Test clear operation during concurrent access."""
        cache = LRUCache[int, int](max_size=100)
        errors = []

        def populator():
            try:
                for _ in range(10):
                    for i in range(100):
                        cache.set(i, i)
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                for _ in range(10):
                    cache.clear()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=populator),
            threading.Thread(target=populator),
            threading.Thread(target=clearer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple operations."""

    def test_full_lifecycle(self):
        """Test complete cache lifecycle."""
        cache = LRUCache[str, int](max_size=5)

        # Empty state
        assert len(cache) == 0

        # Populate
        for i in range(5):
            cache.set(f"key_{i}", i)
        assert len(cache) == 5

        # Access some keys
        cache.get("key_0")
        cache.get("key_1")

        # Add more (triggers eviction)
        cache.set("key_5", 5)
        cache.set("key_6", 6)

        # Verify eviction
        assert "key_2" not in cache  # First to be evicted
        assert "key_3" not in cache  # Second to be evicted
        assert "key_0" in cache  # Was accessed
        assert "key_1" in cache  # Was accessed

        # Pop an item
        value = cache.pop("key_5")
        assert value == 5
        assert "key_5" not in cache

        # Clear
        cache.clear()
        assert len(cache) == 0

        # Verify usable after clear
        cache.set("new_key", 999)
        assert cache.get("new_key") == 999

    def test_cache_as_session_store(self):
        """Test cache simulating session store behavior."""
        # Simulate storing user sessions with max 100 sessions
        sessions = LRUCache[str, dict](max_size=100)

        # Add 100 sessions (fills cache)
        for i in range(100):
            sessions.set(f"user_{i}", {"login_time": i, "data": f"data_{i}"})

        assert len(sessions) == 100

        # Access first 10 sessions (simulate user activity)
        # This moves users 0-9 to the end (most recently used)
        for i in range(10):
            sessions.get(f"user_{i}")

        # Order now: 10,11,...,99, 0,1,...,9

        # Add 50 new sessions - this will evict the 50 oldest (10-59)
        for i in range(100, 150):
            sessions.set(f"user_{i}", {"login_time": i, "data": f"data_{i}"})

        assert len(sessions) == 100

        # Users 0-9 were accessed, so they moved to end and survived eviction
        for i in range(10):
            assert f"user_{i}" in sessions, f"user_{i} should be present"

        # Users 10-59 were oldest (not accessed) and should be evicted
        for i in range(10, 60):
            assert f"user_{i}" not in sessions, f"user_{i} should be evicted"

        # Users 60-99 and 100-149 should be present (50 + 50 = 100)
        for i in range(60, 100):
            assert f"user_{i}" in sessions, f"user_{i} should be present"
        for i in range(100, 150):
            assert f"user_{i}" in sessions, f"user_{i} should be present"

    def test_cache_as_lru_memoization(self):
        """Test cache used for memoization with LRU eviction."""
        call_count = 0
        cache = LRUCache[int, int](max_size=10)

        def expensive_computation(n):
            nonlocal call_count
            cached = cache.get(n)
            if cached is not None:
                return cached
            call_count += 1
            result = n * n  # Simulate expensive computation
            cache.set(n, result)
            return result

        # First calls should compute
        for i in range(10):
            result = expensive_computation(i)
            assert result == i * i

        assert call_count == 10

        # Repeated calls should use cache
        for i in range(10):
            result = expensive_computation(i)
            assert result == i * i

        assert call_count == 10  # No new computations

        # Add more unique values (will cause eviction)
        for i in range(10, 20):
            expensive_computation(i)

        # Old values should be recomputed
        for i in range(10):
            expensive_computation(i)

        # Some values had to be recomputed
        assert call_count > 20
