"""
Cleanup utilities for orphaned temp files.

Cleans up temporary files created during image/voice/document processing.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Default max age for temp files (1 hour)
DEFAULT_MAX_AGE_HOURS = 1


def get_temp_directories() -> List[Path]:
    """Get list of temp directories to clean."""
    settings = get_settings()
    base_dir = Path(settings.claude_code_work_dir).expanduser()

    return [
        base_dir / "temp_images",
        base_dir / "temp_docs",
        base_dir / "temp_audio",
    ]


def cleanup_old_files(
    directory: Path,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    dry_run: bool = False,
) -> Tuple[int, int, int]:
    """
    Clean up files older than max_age_hours in directory.

    Args:
        directory: Directory to clean
        max_age_hours: Maximum age of files in hours
        dry_run: If True, don't actually delete files

    Returns:
        Tuple of (files_found, files_deleted, bytes_freed)
    """
    if not directory.exists():
        logger.debug(f"Directory does not exist: {directory}")
        return (0, 0, 0)

    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    files_found = 0
    files_deleted = 0
    bytes_freed = 0

    try:
        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue

            files_found += 1

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_time:
                    file_size = file_path.stat().st_size

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would delete: {file_path} ({file_size} bytes)"
                        )
                    else:
                        file_path.unlink()
                        logger.info(f"Deleted: {file_path} ({file_size} bytes)")

                    files_deleted += 1
                    bytes_freed += file_size

            except Exception as e:
                logger.warning(f"Error processing {file_path}: {e}")

    except Exception as e:
        logger.error(f"Error scanning directory {directory}: {e}")

    return (files_found, files_deleted, bytes_freed)


def cleanup_all_temp_files(
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    dry_run: bool = False,
) -> dict:
    """
    Clean up all temp directories.

    Args:
        max_age_hours: Maximum age of files in hours
        dry_run: If True, don't actually delete files

    Returns:
        Dict with cleanup statistics
    """
    total_found = 0
    total_deleted = 0
    total_bytes = 0
    results = {}

    for directory in get_temp_directories():
        found, deleted, bytes_freed = cleanup_old_files(
            directory, max_age_hours, dry_run
        )

        results[str(directory)] = {
            "found": found,
            "deleted": deleted,
            "bytes_freed": bytes_freed,
        }

        total_found += found
        total_deleted += deleted
        total_bytes += bytes_freed

    summary = {
        "directories": results,
        "total_found": total_found,
        "total_deleted": total_deleted,
        "total_bytes_freed": total_bytes,
        "dry_run": dry_run,
    }

    logger.info(
        f"Cleanup complete: {total_deleted}/{total_found} files deleted, "
        f"{total_bytes / 1024:.1f} KB freed"
    )

    return summary


async def run_periodic_cleanup(
    interval_hours: float = 1.0,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
):
    """
    Run periodic cleanup as a background task.

    Args:
        interval_hours: How often to run cleanup
        max_age_hours: Max age of files to keep
    """
    logger.info(
        f"Starting periodic cleanup: every {interval_hours}h, max age {max_age_hours}h"
    )

    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            cleanup_all_temp_files(max_age_hours=max_age_hours)
        except asyncio.CancelledError:
            logger.info("Periodic cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)


# CLI entry point for manual cleanup
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clean up temp files")
    parser.add_argument("--max-age", type=float, default=1.0, help="Max age in hours")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't delete, just show"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = cleanup_all_temp_files(max_age_hours=args.max_age, dry_run=args.dry_run)
    print(
        f"\nSummary: {result['total_deleted']} files deleted, "
        f"{result['total_bytes_freed'] / 1024:.1f} KB freed"
    )
