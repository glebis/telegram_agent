"""Simple LRU cache implementation for bounded in-memory caching."""

import threading
from collections import OrderedDict
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """
    Thread-safe LRU cache with maximum size limit.

    When the cache exceeds max_size, the least recently used items are evicted.
    """

    def __init__(self, max_size: int = 10000):
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Get item and move to end (most recently used)."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return default

    def set(self, key: K, value: V) -> None:
        """Set item and evict oldest if over capacity."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value

            # Evict oldest items if over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._cache

    def __setitem__(self, key: K, value: V) -> None:
        self.set(key, value)

    def __getitem__(self, key: K) -> V:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            raise KeyError(key)

    def pop(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Remove and return item."""
        with self._lock:
            return self._cache.pop(key, default)

    def clear(self) -> None:
        """Clear all items."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def items(self):
        """Return snapshot of items."""
        with self._lock:
            return list(self._cache.items())
