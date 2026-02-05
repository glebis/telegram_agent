import hashlib
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies at module level
_get_db_session = None


def get_db_session():
    """Lazy import of get_db_session to avoid circular imports."""
    global _get_db_session
    if _get_db_session is None:
        from src.core.database import get_db_session as _gds

        _get_db_session = _gds
    return _get_db_session()


class CallbackDataManager:
    """Manages callback data to stay within Telegram's 64-byte limit.

    Callback data is stored in memory for fast access and persisted to SQLite
    so that inline keyboard buttons survive bot restarts.
    """

    # Persisted TTL: 7 days (buttons should work for at least a week)
    PERSISTED_TTL = 7 * 24 * 3600  # 604800 seconds

    def __init__(self):
        # In-memory storage for file_id mappings
        self._file_id_cache: Dict[str, str] = {}
        self._reverse_cache: Dict[str, str] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._max_cache_age = self.PERSISTED_TTL  # 7 days

        # Generic data storage for arbitrary callback data (paths, etc.)
        self._data_cache: Dict[str, Dict] = {}
        self._data_timestamps: Dict[str, float] = {}

        # Pending writes queue: list of (data_type, short_id, payload)
        # Flushed periodically or on demand to avoid sync/async mismatch
        self._pending_writes: List[Tuple[str, str, str]] = []

    def get_short_file_id(self, file_id: str) -> str:
        """Get a short identifier for a file_id"""
        # Check if we already have a mapping
        if file_id in self._reverse_cache:
            short_id = self._reverse_cache[file_id]
            # Update timestamp
            self._cache_timestamps[short_id] = time.time()
            return short_id

        # Create a short hash of the file_id
        # Use first 8 characters of SHA-256 hash for uniqueness
        hash_obj = hashlib.sha256(file_id.encode())
        short_id = hash_obj.hexdigest()[:8]

        # Handle potential collisions by appending a counter
        counter = 0
        original_short_id = short_id
        while short_id in self._file_id_cache:
            counter += 1
            short_id = f"{original_short_id}{counter}"
            if len(short_id) > 12:  # Keep it reasonably short
                # If we have too many collisions, use timestamp
                short_id = f"{original_short_id[:6]}{int(time.time()) % 1000}"
                break

        # Store the mapping
        self._file_id_cache[short_id] = file_id
        self._reverse_cache[file_id] = short_id
        self._cache_timestamps[short_id] = time.time()

        # Queue DB write
        self._pending_writes.append(("file_id", short_id, file_id))

        logger.debug(f"Created short_id {short_id} for file_id {file_id[:20]}...")
        return short_id

    def get_file_id(self, short_id: str) -> Optional[str]:
        """Get the original file_id from a short identifier"""
        self._cleanup_expired_cache()

        file_id = self._file_id_cache.get(short_id)
        if file_id:
            # Update timestamp on access
            self._cache_timestamps[short_id] = time.time()
            logger.debug(f"Retrieved file_id for short_id {short_id}")
        else:
            logger.warning(f"No file_id found for short_id {short_id}")

        return file_id

    def create_callback_data(
        self,
        action: str,
        file_id: str = None,
        mode: str = None,
        preset: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Create callback data within Telegram's 64-byte limit.

        If file_id, mode, and preset are provided, uses the legacy format.
        If kwargs are provided, stores them in the data cache and returns a short ID.
        """
        # If we have arbitrary kwargs, use the generic data storage
        if kwargs and file_id is None:
            return self._create_generic_callback(action, kwargs)

        # Legacy format for reanalyze callbacks
        short_id = self.get_short_file_id(file_id)

        if preset:
            callback_data = f"{action}:{short_id}:{mode}:{preset}"
        else:
            callback_data = f"{action}:{short_id}:{mode}:"

        # Ensure we're within the 64-byte limit
        if len(callback_data.encode("utf-8")) > 64:
            logger.warning(f"Callback data still too long: {len(callback_data)} bytes")
            # Truncate preset if necessary
            if preset and len(preset) > 10:
                preset = preset[:10]
                callback_data = f"{action}:{short_id}:{mode}:{preset}"

        byte_len = len(callback_data.encode("utf-8"))
        logger.debug(f"Created callback data: {callback_data} ({byte_len} bytes)")
        return callback_data

    def _create_generic_callback(self, action: str, data: Dict) -> str:
        """Create callback data for arbitrary data by storing in cache."""
        # Create a unique short ID for this data
        data_str = f"{action}:{str(sorted(data.items()))}"
        hash_obj = hashlib.sha256(data_str.encode())
        short_id = hash_obj.hexdigest()[:12]

        # Store the data
        full_data = {"action": action, **data}
        self._data_cache[short_id] = full_data
        self._data_timestamps[short_id] = time.time()

        # Queue DB write (serialize the full data as JSON)
        self._pending_writes.append(("generic", short_id, json.dumps(full_data)))

        # Format: cb:{short_id} - "cb" for "callback" to identify generic callbacks
        callback_data = f"cb:{short_id}"
        logger.debug(f"Created generic callback: {callback_data} for action={action}")
        return callback_data

    def get_generic_data(self, short_id: str) -> Optional[Dict]:
        """Retrieve generic callback data by short ID."""
        self._cleanup_generic_cache()

        data = self._data_cache.get(short_id)
        if data:
            self._data_timestamps[short_id] = time.time()
            logger.debug(f"Retrieved generic data for {short_id}: {data}")
        else:
            logger.warning(f"No data found for short_id: {short_id}")
        return data

    def _cleanup_generic_cache(self):
        """Remove expired entries from generic data cache."""
        current_time = time.time()
        expired_keys = [
            key
            for key, ts in self._data_timestamps.items()
            if current_time - ts > self._max_cache_age
        ]
        for key in expired_keys:
            self._data_cache.pop(key, None)
            self._data_timestamps.pop(key, None)
        if expired_keys:
            logger.info(
                f"Cleaned up {len(expired_keys)} expired generic callback entries"
            )

    def parse_callback_data(
        self, callback_data: str
    ) -> Tuple[str, Optional[str], List[str]]:
        """Parse callback data and return action, file_id, and remaining params"""
        logger.info(f"Parsing callback data: {callback_data}")
        parts = callback_data.split(":", 1)

        if len(parts) < 2:
            logger.warning(f"Invalid callback data format (no colon): {callback_data}")
            return callback_data, None, []

        action = parts[0]
        remaining = parts[1].split(":")

        if len(remaining) < 1:
            logger.warning(f"Invalid callback data format (no params): {callback_data}")
            return action, None, []

        short_id = remaining[0]
        file_id = self.get_file_id(short_id)

        if not file_id:
            logger.debug(f"No cached file_id for short_id: {short_id}")
            # Try to use the short_id as the file_id directly (for backward compatibility)
            # This helps if the short_id is actually a full file_id from before we implemented shortening
            # Real Telegram file_ids are typically 60+ chars and contain special chars like - and _
            # Plain action names (e.g. "cycle_correction_level") should NOT be treated as file_ids
            if len(short_id) > 40 and not short_id.replace("_", "").isalpha():
                logger.info(
                    f"Using short_id as file_id (likely a full file_id): {short_id[:20]}..."
                )
                file_id = short_id
        else:
            logger.info(
                f"Successfully retrieved file_id for short_id {short_id}: {file_id[:20]}..."
            )

        # Return remaining parameters
        params = remaining[1:] if len(remaining) > 1 else []
        logger.info(
            f"Parsed callback data: action={action}, file_id={file_id[:20] if file_id else None}..., params={params}"
        )

        return action, file_id, params

    def _cleanup_expired_cache(self):
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = []

        for short_id, timestamp in self._cache_timestamps.items():
            if current_time - timestamp > self._max_cache_age:
                expired_keys.append(short_id)

        for key in expired_keys:
            file_id = self._file_id_cache.pop(key, None)
            if file_id:
                self._reverse_cache.pop(file_id, None)
            self._cache_timestamps.pop(key, None)

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired callback data entries")

    def clear_cache(self):
        """Clear all cached data"""
        self._file_id_cache.clear()
        self._reverse_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cleared callback data cache")

    # =========================================================================
    # Database persistence methods
    # =========================================================================

    async def load_from_db(self) -> None:
        """Load persisted callback data from SQLite into memory caches.

        Called once on startup to hydrate caches so that inline keyboard
        buttons created before a restart still work.
        """
        from src.models.callback_data import CallbackData

        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(CallbackData))
                rows = result.scalars().all()

                file_id_count = 0
                generic_count = 0
                now = time.time()

                for row in rows:
                    # Skip entries older than the persisted TTL
                    if row.created_at:
                        age = now - row.created_at.timestamp()
                        if age > self.PERSISTED_TTL:
                            continue

                    if row.data_type == "file_id":
                        self._file_id_cache[row.short_id] = row.payload
                        self._reverse_cache[row.payload] = row.short_id
                        self._cache_timestamps[row.short_id] = now
                        file_id_count += 1
                    elif row.data_type == "generic":
                        try:
                            self._data_cache[row.short_id] = json.loads(row.payload)
                            self._data_timestamps[row.short_id] = now
                            generic_count += 1
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse generic callback"
                                f" data for {row.short_id}"
                            )

                logger.info(
                    f"Loaded {file_id_count} file_id and {generic_count} generic "
                    f"callback entries from database"
                )
        except Exception as e:
            logger.error(f"Failed to load callback data from database: {e}")

    async def flush_pending_writes(self) -> None:
        """Flush all pending writes to the database.

        Uses upsert semantics: if a short_id already exists, update the payload.
        """
        if not self._pending_writes:
            return

        from src.models.callback_data import CallbackData

        # Take a snapshot and clear the queue
        writes = self._pending_writes[:]
        self._pending_writes.clear()

        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                for data_type, short_id, payload in writes:
                    # Check if row already exists
                    result = await session.execute(
                        select(CallbackData).where(CallbackData.short_id == short_id)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.payload = payload
                        existing.data_type = data_type
                    else:
                        session.add(
                            CallbackData(
                                short_id=short_id,
                                data_type=data_type,
                                payload=payload,
                            )
                        )

                await session.commit()
                logger.debug(f"Flushed {len(writes)} callback data writes to database")
        except Exception as e:
            logger.error(f"Failed to flush callback data to database: {e}")
            # Put failed writes back on the queue for retry
            self._pending_writes.extend(writes)

    async def cleanup_expired_from_db(self) -> None:
        """Remove expired entries from the database.

        Deletes rows whose short_id is no longer in the in-memory cache
        (i.e., they were expired by _cleanup_expired_cache).
        """
        from src.models.callback_data import CallbackData

        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(CallbackData))
                rows = result.scalars().all()

                removed = 0
                now = time.time()
                for row in rows:
                    # Remove if expired from in-memory cache or older than TTL
                    in_file_cache = row.short_id in self._file_id_cache
                    in_data_cache = row.short_id in self._data_cache

                    is_expired = False
                    if row.created_at:
                        age = now - row.created_at.timestamp()
                        is_expired = age > self.PERSISTED_TTL

                    if (not in_file_cache and not in_data_cache) or is_expired:
                        await session.delete(row)
                        removed += 1

                await session.commit()
                if removed:
                    logger.info(
                        f"Removed {removed} expired callback data entries from database"
                    )
        except Exception as e:
            logger.error(f"Failed to cleanup expired callback data from database: {e}")


# Global instance
_callback_data_manager: Optional[CallbackDataManager] = None


def get_callback_data_manager() -> CallbackDataManager:
    """Get the global callback data manager instance"""
    global _callback_data_manager
    if _callback_data_manager is None:
        _callback_data_manager = CallbackDataManager()
    return _callback_data_manager
