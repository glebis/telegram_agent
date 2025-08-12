import hashlib
import logging
from typing import Dict, Optional, Tuple, List
import time

logger = logging.getLogger(__name__)


class CallbackDataManager:
    """Manages callback data to stay within Telegram's 64-byte limit"""

    def __init__(self):
        # In-memory storage for file_id mappings
        # In production, this should use Redis or database
        self._file_id_cache: Dict[str, str] = {}
        self._reverse_cache: Dict[str, str] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._max_cache_age = 3600  # 1 hour

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
        self, action: str, file_id: str, mode: str, preset: Optional[str] = None
    ) -> str:
        """Create callback data within Telegram's 64-byte limit"""
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

        logger.debug(
            f"Created callback data: {callback_data} ({len(callback_data.encode('utf-8'))} bytes)"
        )
        return callback_data

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
            logger.error(f"Failed to retrieve file_id for short_id: {short_id}")
            # Try to use the short_id as the file_id directly (for backward compatibility)
            # This helps if the short_id is actually a full file_id from before we implemented shortening
            if len(short_id) > 20:  # Telegram file_ids are typically long
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


# Global instance
_callback_data_manager: Optional[CallbackDataManager] = None


def get_callback_data_manager() -> CallbackDataManager:
    """Get the global callback data manager instance"""
    global _callback_data_manager
    if _callback_data_manager is None:
        _callback_data_manager = CallbackDataManager()
    return _callback_data_manager
