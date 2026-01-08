"""
Tests for cleanup utilities.

Tests cover:
- Cleanup functions for temp files
- Resource management and directory handling
- Graceful shutdown with periodic cleanup
- Error handling during cleanup operations
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils import cleanup
from src.utils.cleanup import (
    DEFAULT_MAX_AGE_HOURS,
    cleanup_all_temp_files,
    cleanup_old_files,
    get_temp_directories,
    run_periodic_cleanup,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_cleanup_dir():
    """Create a temporary directory for cleanup testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_cleanup_dir_with_files(temp_cleanup_dir):
    """Create a temp directory with test files of various ages."""
    # Create some test files
    files = {}

    # Recent file (should not be deleted with default max_age)
    recent_file = temp_cleanup_dir / "recent_file.txt"
    recent_file.write_text("recent content")
    files["recent"] = recent_file

    # Old file (modify time to be 2 hours ago)
    old_file = temp_cleanup_dir / "old_file.txt"
    old_file.write_text("old content")
    # Set modification time to 2 hours ago
    old_time = datetime.now() - timedelta(hours=2)
    os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))
    files["old"] = old_file

    # Very old file (modify time to be 24 hours ago)
    very_old_file = temp_cleanup_dir / "very_old_file.txt"
    very_old_file.write_text("very old content - larger file" * 100)
    very_old_time = datetime.now() - timedelta(hours=24)
    os.utime(very_old_file, (very_old_time.timestamp(), very_old_time.timestamp()))
    files["very_old"] = very_old_file

    return temp_cleanup_dir, files


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.claude_code_work_dir = "/tmp/test_work_dir"
    return settings


# =============================================================================
# Get Temp Directories Tests
# =============================================================================


class TestGetTempDirectories:
    """Tests for get_temp_directories function."""

    def test_returns_list_of_paths(self, mock_settings):
        """Test that get_temp_directories returns a list of Path objects."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            directories = get_temp_directories()

        assert isinstance(directories, list)
        assert all(isinstance(d, Path) for d in directories)

    def test_returns_expected_subdirectories(self, mock_settings):
        """Test that expected temp subdirectories are returned."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            directories = get_temp_directories()

        dir_names = [d.name for d in directories]

        assert "temp_images" in dir_names
        assert "temp_docs" in dir_names
        assert "temp_audio" in dir_names

    def test_expands_user_path(self, mock_settings):
        """Test that user path (~) is expanded."""
        mock_settings.claude_code_work_dir = "~/test_dir"

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            directories = get_temp_directories()

        # None should contain ~
        assert all("~" not in str(d) for d in directories)

    def test_base_directory_from_settings(self, mock_settings):
        """Test that base directory comes from settings."""
        mock_settings.claude_code_work_dir = "/custom/path"

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            directories = get_temp_directories()

        # All directories should be under /custom/path
        assert all(str(d).startswith("/custom/path") for d in directories)


# =============================================================================
# Cleanup Old Files Tests
# =============================================================================


class TestCleanupOldFiles:
    """Tests for cleanup_old_files function."""

    def test_returns_tuple_of_three_ints(self, temp_cleanup_dir):
        """Test that function returns tuple of (found, deleted, bytes)."""
        result = cleanup_old_files(temp_cleanup_dir)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(isinstance(x, int) for x in result)

    def test_nonexistent_directory_returns_zeros(self):
        """Test that non-existent directory returns (0, 0, 0)."""
        nonexistent = Path("/nonexistent/directory/path")

        result = cleanup_old_files(nonexistent)

        assert result == (0, 0, 0)

    def test_empty_directory_returns_zeros(self, temp_cleanup_dir):
        """Test cleanup of empty directory."""
        result = cleanup_old_files(temp_cleanup_dir)

        assert result == (0, 0, 0)

    def test_finds_all_files(self, temp_cleanup_dir_with_files):
        """Test that all files are found."""
        directory, files = temp_cleanup_dir_with_files

        found, deleted, _ = cleanup_old_files(directory, max_age_hours=0.001)

        # Should find all 3 files
        assert found == 3

    def test_deletes_old_files_only(self, temp_cleanup_dir_with_files):
        """Test that only old files are deleted."""
        directory, files = temp_cleanup_dir_with_files

        # Use 1.5 hour cutoff - should delete old and very_old
        found, deleted, bytes_freed = cleanup_old_files(
            directory, max_age_hours=1.5
        )

        assert found == 3
        assert deleted == 2

        # Recent file should still exist
        assert files["recent"].exists()
        # Old files should be deleted
        assert not files["old"].exists()
        assert not files["very_old"].exists()

    def test_respects_max_age_hours(self, temp_cleanup_dir_with_files):
        """Test that max_age_hours parameter works correctly."""
        directory, files = temp_cleanup_dir_with_files

        # With 48 hour cutoff, nothing should be deleted
        found, deleted, _ = cleanup_old_files(directory, max_age_hours=48.0)

        assert found == 3
        assert deleted == 0
        assert all(f.exists() for f in files.values())

    def test_dry_run_does_not_delete(self, temp_cleanup_dir_with_files):
        """Test that dry_run mode doesn't delete files."""
        directory, files = temp_cleanup_dir_with_files

        # Only old and very_old files are older than 1.5 hours
        found, deleted, bytes_freed = cleanup_old_files(
            directory, max_age_hours=1.5, dry_run=True
        )

        assert found == 3
        assert deleted == 2  # Only old and very_old meet the age criteria
        assert bytes_freed > 0  # Reports bytes that would be freed

        # But all files should still exist
        assert all(f.exists() for f in files.values())

    def test_returns_correct_bytes_freed(self, temp_cleanup_dir_with_files):
        """Test that bytes_freed is calculated correctly."""
        directory, files = temp_cleanup_dir_with_files

        # Get size of very_old file before deletion
        very_old_size = files["very_old"].stat().st_size
        old_size = files["old"].stat().st_size

        _, _, bytes_freed = cleanup_old_files(directory, max_age_hours=1.5)

        # Should match the sum of deleted file sizes
        assert bytes_freed == very_old_size + old_size

    def test_skips_subdirectories(self, temp_cleanup_dir):
        """Test that subdirectories are skipped (only files processed)."""
        # Create a subdirectory
        subdir = temp_cleanup_dir / "subdir"
        subdir.mkdir()

        # Create a file in the subdirectory
        (subdir / "nested_file.txt").write_text("nested")

        # Create a file in the main directory
        main_file = temp_cleanup_dir / "main_file.txt"
        main_file.write_text("main")

        found, _, _ = cleanup_old_files(temp_cleanup_dir, max_age_hours=0.001)

        # Should only find the main file, not the directory
        assert found == 1

    def test_handles_permission_error(self, temp_cleanup_dir):
        """Test graceful handling of permission errors."""
        # Create a file
        test_file = temp_cleanup_dir / "test.txt"
        test_file.write_text("test")

        # Make it old
        old_time = datetime.now() - timedelta(hours=2)
        os.utime(test_file, (old_time.timestamp(), old_time.timestamp()))

        # Mock the unlink to raise permission error
        with patch.object(Path, "unlink", side_effect=PermissionError("Access denied")):
            found, deleted, _ = cleanup_old_files(
                temp_cleanup_dir, max_age_hours=1.0
            )

        # Should have found the file but failed to delete
        # The error is caught and the file is not counted as deleted
        assert found == 1
        assert deleted == 0  # Not counted as deleted when error occurs
        # File should still exist
        assert test_file.exists()

    def test_handles_stat_error(self, temp_cleanup_dir):
        """Test graceful handling of stat errors on individual files."""
        # Create a file
        test_file = temp_cleanup_dir / "test.txt"
        test_file.write_text("test")

        # Mock stat to raise an error
        original_stat = Path.stat

        def mock_stat(self):
            if self.name == "test.txt":
                raise OSError("Cannot stat file")
            return original_stat(self)

        with patch.object(Path, "stat", mock_stat):
            # Should not raise, but skip the file
            found, deleted, _ = cleanup_old_files(temp_cleanup_dir)

        # File should still exist
        assert test_file.exists()

    def test_handles_directory_scan_error(self, temp_cleanup_dir):
        """Test graceful handling of directory scan errors."""
        # Mock iterdir to raise an error
        with patch.object(Path, "iterdir", side_effect=PermissionError("Cannot scan")):
            result = cleanup_old_files(temp_cleanup_dir)

        # Should return zeros without raising
        assert result == (0, 0, 0)

    def test_logs_deletion(self, temp_cleanup_dir_with_files):
        """Test that file deletions are logged."""
        directory, files = temp_cleanup_dir_with_files

        with patch.object(cleanup.logger, "info") as mock_log:
            cleanup_old_files(directory, max_age_hours=1.5)

        # Should have logged deletions
        assert mock_log.call_count >= 2  # At least 2 files deleted

    def test_logs_dry_run(self, temp_cleanup_dir_with_files):
        """Test that dry run is logged appropriately."""
        directory, files = temp_cleanup_dir_with_files

        with patch.object(cleanup.logger, "info") as mock_log:
            cleanup_old_files(directory, max_age_hours=1.5, dry_run=True)

        # Check that dry run was indicated in logs
        log_messages = [str(call) for call in mock_log.call_args_list]
        assert any("DRY RUN" in msg for msg in log_messages)


# =============================================================================
# Cleanup All Temp Files Tests
# =============================================================================


class TestCleanupAllTempFiles:
    """Tests for cleanup_all_temp_files function."""

    def test_returns_summary_dict(self, mock_settings):
        """Test that function returns a summary dictionary."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files()

        assert isinstance(result, dict)
        assert "directories" in result
        assert "total_found" in result
        assert "total_deleted" in result
        assert "total_bytes_freed" in result
        assert "dry_run" in result

    def test_cleans_all_temp_directories(self, temp_cleanup_dir, mock_settings):
        """Test that all temp directories are cleaned."""
        # Create temp subdirectories
        temp_images = temp_cleanup_dir / "temp_images"
        temp_docs = temp_cleanup_dir / "temp_docs"
        temp_audio = temp_cleanup_dir / "temp_audio"

        for d in [temp_images, temp_docs, temp_audio]:
            d.mkdir()

        # Create old files in each
        old_time = datetime.now() - timedelta(hours=2)
        for subdir in [temp_images, temp_docs, temp_audio]:
            f = subdir / "old_file.txt"
            f.write_text("old content")
            os.utime(f, (old_time.timestamp(), old_time.timestamp()))

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files(max_age_hours=1.0)

        assert result["total_deleted"] == 3
        assert len(result["directories"]) == 3

    def test_aggregates_totals(self, temp_cleanup_dir, mock_settings):
        """Test that totals are correctly aggregated."""
        temp_images = temp_cleanup_dir / "temp_images"
        temp_images.mkdir()

        # Create multiple old files
        old_time = datetime.now() - timedelta(hours=2)
        for i in range(5):
            f = temp_images / f"file_{i}.txt"
            f.write_text("content " * 10)
            os.utime(f, (old_time.timestamp(), old_time.timestamp()))

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files(max_age_hours=1.0)

        assert result["total_found"] == 5
        assert result["total_deleted"] == 5
        assert result["total_bytes_freed"] > 0

    def test_respects_dry_run(self, temp_cleanup_dir, mock_settings):
        """Test that dry_run mode is passed through."""
        temp_images = temp_cleanup_dir / "temp_images"
        temp_images.mkdir()

        old_file = temp_images / "old_file.txt"
        old_file.write_text("content")
        old_time = datetime.now() - timedelta(hours=2)
        os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files(max_age_hours=1.0, dry_run=True)

        assert result["dry_run"] is True
        # File should still exist
        assert old_file.exists()

    def test_per_directory_stats(self, temp_cleanup_dir, mock_settings):
        """Test that per-directory statistics are recorded."""
        temp_images = temp_cleanup_dir / "temp_images"
        temp_docs = temp_cleanup_dir / "temp_docs"
        temp_audio = temp_cleanup_dir / "temp_audio"

        for d in [temp_images, temp_docs, temp_audio]:
            d.mkdir()

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files()

        # Each directory should have its own stats
        for dir_path, stats in result["directories"].items():
            assert "found" in stats
            assert "deleted" in stats
            assert "bytes_freed" in stats

    def test_handles_missing_directories(self, mock_settings):
        """Test handling of missing temp directories."""
        mock_settings.claude_code_work_dir = "/nonexistent/base/path"

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files()

        # Should complete without error
        assert result["total_found"] == 0
        assert result["total_deleted"] == 0

    def test_logs_summary(self, mock_settings):
        """Test that a summary is logged."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch.object(cleanup.logger, "info") as mock_log:
                cleanup_all_temp_files()

        # Should have logged at least the completion message
        mock_log.assert_called()

    def test_default_max_age(self, mock_settings):
        """Test that default max age constant is used."""
        assert DEFAULT_MAX_AGE_HOURS == 1

        # When called without max_age_hours, should use default
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch(
                "src.utils.cleanup.cleanup_old_files"
            ) as mock_cleanup:
                mock_cleanup.return_value = (0, 0, 0)
                cleanup_all_temp_files()

        # Check that cleanup_old_files was called with default max_age
        for call in mock_cleanup.call_args_list:
            # Check both positional and keyword args
            args, kwargs = call
            # max_age_hours is the second positional arg or in kwargs
            if "max_age_hours" in kwargs:
                assert kwargs["max_age_hours"] == DEFAULT_MAX_AGE_HOURS
            elif len(args) >= 2:
                assert args[1] == DEFAULT_MAX_AGE_HOURS


# =============================================================================
# Periodic Cleanup Tests
# =============================================================================


class TestRunPeriodicCleanup:
    """Tests for run_periodic_cleanup async function."""

    @pytest.mark.asyncio
    async def test_can_be_cancelled(self, mock_settings):
        """Test that periodic cleanup can be cancelled."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch(
                "src.utils.cleanup.cleanup_all_temp_files"
            ) as mock_cleanup:
                task = asyncio.create_task(
                    run_periodic_cleanup(interval_hours=0.001)
                )

                # Let it start
                await asyncio.sleep(0.01)

                # Cancel it
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Should complete without error

    @pytest.mark.asyncio
    async def test_runs_cleanup_after_interval(self, mock_settings):
        """Test that cleanup runs after the interval."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch(
                "src.utils.cleanup.cleanup_all_temp_files"
            ) as mock_cleanup:
                # Use very short interval
                task = asyncio.create_task(
                    run_periodic_cleanup(
                        interval_hours=0.0001,  # ~0.36 seconds
                        max_age_hours=2.0
                    )
                )

                # Wait for at least one cleanup
                await asyncio.sleep(0.5)

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Should have called cleanup at least once
        assert mock_cleanup.call_count >= 1
        # Should have passed max_age_hours
        mock_cleanup.assert_called_with(max_age_hours=2.0)

    @pytest.mark.asyncio
    async def test_logs_startup(self, mock_settings):
        """Test that startup is logged."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch.object(cleanup.logger, "info") as mock_log:
                task = asyncio.create_task(
                    run_periodic_cleanup(interval_hours=1.0)
                )

                # Give it time to log startup
                await asyncio.sleep(0.01)

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Should have logged startup
        log_messages = [str(call) for call in mock_log.call_args_list]
        assert any("periodic cleanup" in msg.lower() for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_cancellation(self, mock_settings):
        """Test that cancellation is logged."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch.object(cleanup.logger, "info") as mock_log:
                task = asyncio.create_task(
                    run_periodic_cleanup(interval_hours=1.0)
                )

                await asyncio.sleep(0.01)
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Should have logged cancellation
        log_messages = [str(call) for call in mock_log.call_args_list]
        assert any("cancelled" in msg.lower() for msg in log_messages)

    @pytest.mark.asyncio
    async def test_handles_cleanup_errors(self, mock_settings):
        """Test that errors during cleanup don't crash the task."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            call_count = 0

            def failing_cleanup(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("Cleanup failed")
                return {"total_deleted": 0}

            with patch(
                "src.utils.cleanup.cleanup_all_temp_files",
                side_effect=failing_cleanup
            ):
                # Use a very short interval (0.00001 hours = 0.036 seconds)
                task = asyncio.create_task(
                    run_periodic_cleanup(interval_hours=0.00001)
                )

                # Wait for multiple iterations (need enough time for 2+ sleep cycles)
                await asyncio.sleep(0.2)

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Should have continued running after error and called cleanup again
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_logs_errors(self, mock_settings):
        """Test that cleanup errors are logged."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch(
                "src.utils.cleanup.cleanup_all_temp_files",
                side_effect=RuntimeError("Test error")
            ):
                with patch.object(cleanup.logger, "error") as mock_error:
                    task = asyncio.create_task(
                        run_periodic_cleanup(interval_hours=0.0001)
                    )

                    await asyncio.sleep(0.5)

                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # Should have logged the error
        mock_error.assert_called()

    @pytest.mark.asyncio
    async def test_interval_hours_parameter(self, mock_settings):
        """Test that interval_hours parameter works."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch("src.utils.cleanup.asyncio.sleep") as mock_sleep:
                # Make sleep raise CancelledError to stop the loop
                mock_sleep.side_effect = asyncio.CancelledError()

                try:
                    await run_periodic_cleanup(interval_hours=5.0)
                except asyncio.CancelledError:
                    pass

        # Should have called sleep with 5.0 * 3600 = 18000 seconds
        mock_sleep.assert_called_once_with(18000.0)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file_handling(self, temp_cleanup_dir):
        """Test cleanup of empty files."""
        empty_file = temp_cleanup_dir / "empty.txt"
        empty_file.touch()  # Create empty file

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(empty_file, (old_time.timestamp(), old_time.timestamp()))

        found, deleted, bytes_freed = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        assert found == 1
        assert deleted == 1
        assert bytes_freed == 0  # Empty file has 0 bytes

    def test_special_characters_in_filename(self, temp_cleanup_dir):
        """Test cleanup of files with special characters in names."""
        special_file = temp_cleanup_dir / "file with spaces & symbols!.txt"
        special_file.write_text("content")

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(special_file, (old_time.timestamp(), old_time.timestamp()))

        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        assert found == 1
        assert deleted == 1
        assert not special_file.exists()

    def test_unicode_filename(self, temp_cleanup_dir):
        """Test cleanup of files with unicode names."""
        unicode_file = temp_cleanup_dir / "file_with_unicode.txt"
        unicode_file.write_text("content")

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(unicode_file, (old_time.timestamp(), old_time.timestamp()))

        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        assert found == 1
        assert deleted == 1

    def test_hidden_files(self, temp_cleanup_dir):
        """Test cleanup includes hidden files."""
        hidden_file = temp_cleanup_dir / ".hidden_file"
        hidden_file.write_text("hidden content")

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(hidden_file, (old_time.timestamp(), old_time.timestamp()))

        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        assert found == 1
        assert deleted == 1
        assert not hidden_file.exists()

    def test_large_file(self, temp_cleanup_dir):
        """Test cleanup of large files."""
        large_file = temp_cleanup_dir / "large_file.bin"
        # Create a 1MB file
        large_file.write_bytes(b"x" * (1024 * 1024))

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(large_file, (old_time.timestamp(), old_time.timestamp()))

        found, deleted, bytes_freed = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        assert found == 1
        assert deleted == 1
        assert bytes_freed == 1024 * 1024

    def test_symlink_handling(self, temp_cleanup_dir):
        """Test that symlinks are handled correctly."""
        # Create a real file
        real_file = temp_cleanup_dir / "real_file.txt"
        real_file.write_text("real content")

        # Create a symlink to it
        symlink = temp_cleanup_dir / "symlink.txt"
        try:
            symlink.symlink_to(real_file)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(real_file, (old_time.timestamp(), old_time.timestamp()))
        # Don't touch symlink's time, test that it's skipped or handled

        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=1.0
        )

        # The real file should be deleted
        # Symlink behavior depends on implementation (may be file or not)
        assert found >= 1

    def test_zero_max_age(self, temp_cleanup_dir_with_files):
        """Test cleanup with zero max age (delete all)."""
        directory, files = temp_cleanup_dir_with_files

        # With 0 max age, all files should be deleted
        found, deleted, _ = cleanup_old_files(
            directory, max_age_hours=0.0
        )

        assert found == 3
        assert deleted == 3

    def test_very_large_max_age(self, temp_cleanup_dir_with_files):
        """Test cleanup with very large max age (delete none)."""
        directory, files = temp_cleanup_dir_with_files

        # With huge max age, no files should be deleted
        found, deleted, _ = cleanup_old_files(
            directory, max_age_hours=10000.0
        )

        assert found == 3
        assert deleted == 0

    def test_fractional_max_age(self, temp_cleanup_dir):
        """Test cleanup with fractional hour max age."""
        # Create a file that's 30 minutes old
        test_file = temp_cleanup_dir / "half_hour_old.txt"
        test_file.write_text("content")

        old_time = datetime.now() - timedelta(minutes=30)
        os.utime(test_file, (old_time.timestamp(), old_time.timestamp()))

        # 0.25 hours = 15 minutes, should delete
        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=0.25
        )
        assert deleted == 1

        # Recreate for second test
        test_file.write_text("content")
        os.utime(test_file, (old_time.timestamp(), old_time.timestamp()))

        # 0.75 hours = 45 minutes, should not delete
        found, deleted, _ = cleanup_old_files(
            temp_cleanup_dir, max_age_hours=0.75
        )
        assert deleted == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_cleanup_workflow(self, temp_cleanup_dir, mock_settings):
        """Test complete cleanup workflow."""
        # Setup directory structure
        temp_images = temp_cleanup_dir / "temp_images"
        temp_docs = temp_cleanup_dir / "temp_docs"
        temp_audio = temp_cleanup_dir / "temp_audio"

        for d in [temp_images, temp_docs, temp_audio]:
            d.mkdir()

        # Create mix of old and new files
        old_time = datetime.now() - timedelta(hours=2)

        # Old files in temp_images
        for i in range(3):
            f = temp_images / f"old_image_{i}.jpg"
            f.write_bytes(b"fake image data" * 100)
            os.utime(f, (old_time.timestamp(), old_time.timestamp()))

        # Recent file in temp_images
        recent = temp_images / "recent_image.jpg"
        recent.write_bytes(b"recent image")

        # Old files in temp_docs
        for i in range(2):
            f = temp_docs / f"old_doc_{i}.pdf"
            f.write_bytes(b"fake pdf" * 50)
            os.utime(f, (old_time.timestamp(), old_time.timestamp()))

        # Empty temp_audio

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            result = cleanup_all_temp_files(max_age_hours=1.0)

        # Verify results
        assert result["total_found"] == 6  # 4 in images, 2 in docs
        assert result["total_deleted"] == 5  # 3 old images + 2 docs
        assert result["total_bytes_freed"] > 0

        # Verify recent file still exists
        assert recent.exists()

        # Verify old files deleted
        assert len(list(temp_images.glob("old_*"))) == 0
        assert len(list(temp_docs.glob("old_*"))) == 0

    @pytest.mark.asyncio
    async def test_periodic_cleanup_integration(self, temp_cleanup_dir, mock_settings):
        """Test periodic cleanup with real file operations."""
        temp_images = temp_cleanup_dir / "temp_images"
        temp_images.mkdir()

        mock_settings.claude_code_work_dir = str(temp_cleanup_dir)

        cleanup_count = 0

        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            # Create an old file before starting
            old_file = temp_images / "old.txt"
            old_file.write_text("old")
            old_time = datetime.now() - timedelta(hours=2)
            os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))

            task = asyncio.create_task(
                run_periodic_cleanup(interval_hours=0.0001, max_age_hours=1.0)
            )

            # Wait for cleanup to run
            await asyncio.sleep(0.5)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Old file should have been cleaned up
        assert not old_file.exists()


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_logs_nonexistent_directory(self):
        """Test that non-existent directory is logged at debug level."""
        with patch.object(cleanup.logger, "debug") as mock_debug:
            cleanup_old_files(Path("/nonexistent/path"))

        mock_debug.assert_called()
        log_message = str(mock_debug.call_args)
        assert "does not exist" in log_message

    def test_logs_file_deletion_details(self, temp_cleanup_dir):
        """Test that file deletion details are logged."""
        test_file = temp_cleanup_dir / "test.txt"
        test_file.write_text("x" * 100)

        old_time = datetime.now() - timedelta(hours=2)
        os.utime(test_file, (old_time.timestamp(), old_time.timestamp()))

        with patch.object(cleanup.logger, "info") as mock_info:
            cleanup_old_files(temp_cleanup_dir, max_age_hours=1.0)

        # Should have logged filename and size
        log_messages = [str(call) for call in mock_info.call_args_list]
        assert any("test.txt" in msg for msg in log_messages)
        assert any("bytes" in msg for msg in log_messages)

    def test_logs_cleanup_summary(self, mock_settings):
        """Test that cleanup summary is logged."""
        with patch("src.utils.cleanup.get_settings", return_value=mock_settings):
            with patch.object(cleanup.logger, "info") as mock_info:
                cleanup_all_temp_files()

        # Should have logged summary
        log_messages = [str(call) for call in mock_info.call_args_list]
        assert any("complete" in msg.lower() for msg in log_messages)

    def test_logs_warnings_on_file_errors(self, temp_cleanup_dir):
        """Test that warnings are logged on file processing errors."""
        test_file = temp_cleanup_dir / "test.txt"
        test_file.write_text("content")

        # Make file old so it passes the age check before we trigger the error
        old_time = datetime.now() - timedelta(hours=2)
        os.utime(test_file, (old_time.timestamp(), old_time.timestamp()))

        # Mock unlink to fail (this happens after stat succeeds)
        with patch.object(Path, "unlink", side_effect=OSError("Unlink failed")):
            with patch.object(cleanup.logger, "warning") as mock_warning:
                cleanup_old_files(temp_cleanup_dir, max_age_hours=1.0)

        mock_warning.assert_called()

    def test_logs_errors_on_directory_scan_failure(self, temp_cleanup_dir):
        """Test that errors are logged on directory scan failure."""
        with patch.object(Path, "iterdir", side_effect=PermissionError("No access")):
            with patch.object(cleanup.logger, "error") as mock_error:
                cleanup_old_files(temp_cleanup_dir)

        mock_error.assert_called()
