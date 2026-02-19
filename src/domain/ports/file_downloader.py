"""FileDownloader port -- abstracts Telegram file download."""

from typing import Any, Dict, Protocol, Tuple, runtime_checkable


@runtime_checkable
class FileDownloader(Protocol):
    """Downloads a file by its platform-specific ID.

    Returns (file_bytes, metadata_dict).
    """

    async def download_file(self, file_id: str) -> Tuple[bytes, Dict[str, Any]]: ...
