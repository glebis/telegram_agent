"""
Tests for the Job Queue Service.

Tests cover:
- JobQueueService initialization
- submit_pdf_convert method
- submit_pdf_save method
- submit_custom_command method
- get_queue_status method
- YAML file creation and content verification
- Edge cases (missing directories, custom paths)
- Security: job ID validation at submission
- Security: command allowlist enforcement at submission
- Security: secure file path handling
"""

import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.services.job_queue_service import JobQueueService, validate_job_id


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_queue_dir():
    """Create a temporary directory structure for the job queue."""
    with tempfile.TemporaryDirectory() as temp_dir:
        queue_dir = Path(temp_dir) / "agent_tasks"
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / "pending").mkdir(exist_ok=True)
        (queue_dir / "in_progress").mkdir(exist_ok=True)
        (queue_dir / "completed").mkdir(exist_ok=True)
        (queue_dir / "failed").mkdir(exist_ok=True)
        yield queue_dir


@pytest.fixture
def job_queue_service(temp_queue_dir):
    """Create a JobQueueService instance with a temporary queue directory."""
    return JobQueueService(queue_dir=temp_queue_dir)


@pytest.fixture
def minimal_queue_dir():
    """Create a minimal temporary directory (pending only, no other dirs)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        queue_dir = Path(temp_dir) / "agent_tasks"
        # Don't create any subdirectories - let the service handle it
        yield queue_dir


# =============================================================================
# JobQueueService Initialization Tests
# =============================================================================


class TestJobQueueServiceInit:
    """Tests for JobQueueService initialization."""

    def test_initialization_with_custom_dir(self, temp_queue_dir):
        """Test that JobQueueService initializes with custom queue directory."""
        service = JobQueueService(queue_dir=temp_queue_dir)

        assert service.queue_dir == temp_queue_dir
        assert service.pending_dir == temp_queue_dir / "pending"
        assert service.pending_dir.exists()

    def test_initialization_creates_pending_dir(self, minimal_queue_dir):
        """Test that initialization creates pending directory if it doesn't exist."""
        # Ensure the directory doesn't exist yet
        assert not minimal_queue_dir.exists()

        service = JobQueueService(queue_dir=minimal_queue_dir)

        assert service.pending_dir.exists()
        assert service.pending_dir == minimal_queue_dir / "pending"

    def test_default_queue_dir(self):
        """Test that default queue_dir uses home directory."""
        with patch.object(Path, "mkdir"):
            service = JobQueueService()

            assert service.queue_dir == Path.home() / "Research/agent_tasks"

    def test_multiple_instances_independent(self, temp_queue_dir):
        """Test that multiple instances can have different queue dirs."""
        with tempfile.TemporaryDirectory() as temp_dir2:
            queue_dir2 = Path(temp_dir2) / "other_tasks"
            queue_dir2.mkdir(parents=True, exist_ok=True)

            service1 = JobQueueService(queue_dir=temp_queue_dir)
            service2 = JobQueueService(queue_dir=queue_dir2)

            assert service1.queue_dir != service2.queue_dir


# =============================================================================
# submit_pdf_convert Tests
# =============================================================================


class TestSubmitPdfConvert:
    """Tests for submit_pdf_convert method."""

    def test_submit_pdf_convert_basic(self, job_queue_service, temp_queue_dir):
        """Test basic PDF convert job submission."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        assert job_id is not None
        assert job_id.startswith("pdf_convert_")
        assert len(job_id) > len("pdf_convert_")

    def test_submit_pdf_convert_creates_yaml_file(self, job_queue_service, temp_queue_dir):
        """Test that PDF convert job creates a YAML file."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        assert job_file.exists()

    def test_submit_pdf_convert_yaml_content(self, job_queue_service, temp_queue_dir):
        """Test the content of the PDF convert job YAML file."""
        url = "https://example.com/test.pdf"
        chat_id = 12345
        message_id = 100

        job_id = job_queue_service.submit_pdf_convert(
            url=url,
            chat_id=chat_id,
            message_id=message_id,
            priority="high"
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["id"] == job_id
        assert job_data["type"] == "pdf_convert"
        assert job_data["priority"] == "high"
        assert job_data["params"]["url"] == url
        assert job_data["telegram_chat_id"] == chat_id
        assert job_data["telegram_message_id"] == message_id
        assert job_data["status"] == "pending"
        assert "created" in job_data

    def test_submit_pdf_convert_default_priority(self, job_queue_service, temp_queue_dir):
        """Test that PDF convert job uses medium priority by default."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["priority"] == "medium"

    def test_submit_pdf_convert_no_message_id(self, job_queue_service, temp_queue_dir):
        """Test PDF convert job without message_id."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["telegram_message_id"] is None

    def test_submit_pdf_convert_unique_ids(self, job_queue_service):
        """Test that multiple PDF convert jobs have unique IDs."""
        job_ids = set()
        for _ in range(10):
            job_id = job_queue_service.submit_pdf_convert(
                url="https://example.com/document.pdf",
                chat_id=12345
            )
            job_ids.add(job_id)

        assert len(job_ids) == 10

    def test_submit_pdf_convert_with_special_url(self, job_queue_service, temp_queue_dir):
        """Test PDF convert with URL containing special characters."""
        url = "https://example.com/path/to/doc.pdf?param=value&other=123"

        job_id = job_queue_service.submit_pdf_convert(
            url=url,
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["url"] == url

    def test_submit_pdf_convert_created_timestamp(self, job_queue_service, temp_queue_dir):
        """Test that created timestamp is valid ISO format."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        # Should be parseable as ISO format
        created_dt = datetime.fromisoformat(job_data["created"])
        assert created_dt is not None
        # Should be recent (within last minute)
        assert (datetime.now() - created_dt).total_seconds() < 60


# =============================================================================
# submit_pdf_save Tests
# =============================================================================


class TestSubmitPdfSave:
    """Tests for submit_pdf_save method."""

    def test_submit_pdf_save_basic(self, job_queue_service, temp_queue_dir):
        """Test basic PDF save job submission."""
        job_id = job_queue_service.submit_pdf_save(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        assert job_id is not None
        assert job_id.startswith("pdf_save_")

    def test_submit_pdf_save_creates_yaml_file(self, job_queue_service, temp_queue_dir):
        """Test that PDF save job creates a YAML file."""
        job_id = job_queue_service.submit_pdf_save(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        assert job_file.exists()

    def test_submit_pdf_save_yaml_content(self, job_queue_service, temp_queue_dir):
        """Test the content of the PDF save job YAML file."""
        url = "https://example.com/test.pdf"
        chat_id = 12345
        message_id = 100
        vault_path = "/custom/vault/path"

        job_id = job_queue_service.submit_pdf_save(
            url=url,
            chat_id=chat_id,
            message_id=message_id,
            vault_path=vault_path,
            priority="low"
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["id"] == job_id
        assert job_data["type"] == "pdf_save"
        assert job_data["priority"] == "low"
        assert job_data["params"]["url"] == url
        assert job_data["params"]["vault_path"] == vault_path
        assert job_data["telegram_chat_id"] == chat_id
        assert job_data["telegram_message_id"] == message_id
        assert job_data["status"] == "pending"

    def test_submit_pdf_save_default_vault_path(self, job_queue_service, temp_queue_dir):
        """Test that PDF save job uses default vault_path."""
        job_id = job_queue_service.submit_pdf_save(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["vault_path"] == "~/Research/vault"

    def test_submit_pdf_save_default_priority(self, job_queue_service, temp_queue_dir):
        """Test that PDF save job uses medium priority by default."""
        job_id = job_queue_service.submit_pdf_save(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["priority"] == "medium"

    def test_submit_pdf_save_no_message_id(self, job_queue_service, temp_queue_dir):
        """Test PDF save job without message_id."""
        job_id = job_queue_service.submit_pdf_save(
            url="https://example.com/document.pdf",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["telegram_message_id"] is None

    def test_submit_pdf_save_unique_ids(self, job_queue_service):
        """Test that multiple PDF save jobs have unique IDs."""
        job_ids = set()
        for _ in range(10):
            job_id = job_queue_service.submit_pdf_save(
                url="https://example.com/document.pdf",
                chat_id=12345
            )
            job_ids.add(job_id)

        assert len(job_ids) == 10

    def test_submit_pdf_save_all_priority_levels(self, job_queue_service, temp_queue_dir):
        """Test PDF save with all priority levels."""
        priorities = ["high", "medium", "low"]

        for priority in priorities:
            job_id = job_queue_service.submit_pdf_save(
                url="https://example.com/document.pdf",
                chat_id=12345,
                priority=priority
            )

            job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
            with open(job_file, "r") as f:
                job_data = yaml.safe_load(f)

            assert job_data["priority"] == priority


# =============================================================================
# submit_custom_command Tests
# =============================================================================


class TestSubmitCustomCommand:
    """Tests for submit_custom_command method.

    Note: All custom command tests require WORKER_COMMAND_ALLOWLIST to be set,
    since the security hardening rejects commands with no allowlist.
    """

    @pytest.fixture(autouse=True)
    def _set_allowlist(self, monkeypatch):
        """Set a permissive allowlist for functional tests."""
        monkeypatch.setenv(
            "WORKER_COMMAND_ALLOWLIST",
            "echo,ls,python,python3,long_running_script.sh"
        )

    def test_submit_custom_command_basic(self, job_queue_service, temp_queue_dir):
        """Test basic custom command job submission."""
        job_id = job_queue_service.submit_custom_command(
            command="echo 'Hello World'",
            chat_id=12345
        )

        assert job_id is not None
        assert job_id.startswith("command_")

    def test_submit_custom_command_creates_yaml_file(self, job_queue_service, temp_queue_dir):
        """Test that custom command job creates a YAML file."""
        job_id = job_queue_service.submit_custom_command(
            command="ls -la",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        assert job_file.exists()

    def test_submit_custom_command_yaml_content(self, job_queue_service, temp_queue_dir):
        """Test the content of the custom command job YAML file."""
        command = "python script.py --arg1 value1"
        chat_id = 12345
        message_id = 100
        timeout = 600

        job_id = job_queue_service.submit_custom_command(
            command=command,
            chat_id=chat_id,
            message_id=message_id,
            timeout=timeout,
            priority="high"
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["id"] == job_id
        assert job_data["type"] == "custom_command"
        assert job_data["priority"] == "high"
        assert job_data["params"]["command"] == command
        assert job_data["params"]["timeout"] == timeout
        assert job_data["telegram_chat_id"] == chat_id
        assert job_data["telegram_message_id"] == message_id
        assert job_data["status"] == "pending"

    def test_submit_custom_command_default_timeout(self, job_queue_service, temp_queue_dir):
        """Test that custom command job uses 300s timeout by default."""
        job_id = job_queue_service.submit_custom_command(
            command="echo test",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["timeout"] == 300

    def test_submit_custom_command_default_priority(self, job_queue_service, temp_queue_dir):
        """Test that custom command job uses low priority by default."""
        job_id = job_queue_service.submit_custom_command(
            command="echo test",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["priority"] == "low"

    def test_submit_custom_command_rejects_shell_chaining(self, job_queue_service, temp_queue_dir):
        """Test that shell chaining commands are rejected (was: accepted)."""
        command = "cd /tmp && ls -la | grep test && echo 'done'"

        with pytest.raises(ValueError, match="[Ss]hell operator"):
            job_queue_service.submit_custom_command(
                command=command,
                chat_id=12345
            )

    def test_submit_custom_command_rejects_shell_special_chars(self, job_queue_service, temp_queue_dir):
        """Test that commands with shell operators are rejected (was: accepted)."""
        command = 'echo "Hello $USER" && printf "Line1\\nLine2"'

        with pytest.raises(ValueError, match="[Ss]hell operator"):
            job_queue_service.submit_custom_command(
                command=command,
                chat_id=12345
            )

    def test_submit_custom_command_unique_ids(self, job_queue_service):
        """Test that multiple custom command jobs have unique IDs."""
        job_ids = set()
        for _ in range(10):
            job_id = job_queue_service.submit_custom_command(
                command="echo test",
                chat_id=12345
            )
            job_ids.add(job_id)

        assert len(job_ids) == 10

    def test_submit_custom_command_long_timeout(self, job_queue_service, temp_queue_dir):
        """Test custom command with long timeout."""
        job_id = job_queue_service.submit_custom_command(
            command="long_running_script.sh",
            chat_id=12345,
            timeout=3600  # 1 hour
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["timeout"] == 3600


# =============================================================================
# get_queue_status Tests
# =============================================================================


class TestGetQueueStatus:
    """Tests for get_queue_status method."""

    def test_get_queue_status_empty(self, job_queue_service):
        """Test queue status when all directories are empty."""
        status = job_queue_service.get_queue_status()

        assert status == {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0
        }

    def test_get_queue_status_with_pending(self, job_queue_service, temp_queue_dir):
        """Test queue status with pending jobs."""
        # Create some pending jobs
        for i in range(3):
            job_queue_service.submit_pdf_convert(
                url=f"https://example.com/doc{i}.pdf",
                chat_id=12345
            )

        status = job_queue_service.get_queue_status()

        assert status["pending"] == 3
        assert status["in_progress"] == 0
        assert status["completed"] == 0
        assert status["failed"] == 0

    def test_get_queue_status_with_in_progress(self, job_queue_service, temp_queue_dir):
        """Test queue status with in-progress jobs."""
        # Create a pending job
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        # Move it to in_progress
        source = temp_queue_dir / "pending" / f"{job_id}.yaml"
        dest = temp_queue_dir / "in_progress" / f"{job_id}.yaml"
        shutil.move(str(source), str(dest))

        status = job_queue_service.get_queue_status()

        assert status["pending"] == 0
        assert status["in_progress"] == 1

    def test_get_queue_status_with_completed(self, job_queue_service, temp_queue_dir):
        """Test queue status with completed jobs."""
        # Create a completed job file directly
        completed_file = temp_queue_dir / "completed" / "test_job.yaml"
        with open(completed_file, "w") as f:
            yaml.dump({"id": "test_job", "status": "completed"}, f)

        status = job_queue_service.get_queue_status()

        assert status["completed"] == 1

    def test_get_queue_status_with_failed(self, job_queue_service, temp_queue_dir):
        """Test queue status with failed jobs."""
        # Create a failed job file directly
        failed_file = temp_queue_dir / "failed" / "test_job.yaml"
        with open(failed_file, "w") as f:
            yaml.dump({"id": "test_job", "status": "failed"}, f)

        status = job_queue_service.get_queue_status()

        assert status["failed"] == 1

    def test_get_queue_status_mixed(self, job_queue_service, temp_queue_dir):
        """Test queue status with jobs in all states."""
        # Create pending jobs
        for i in range(2):
            job_queue_service.submit_pdf_convert(
                url=f"https://example.com/doc{i}.pdf",
                chat_id=12345
            )

        # Create in_progress job
        in_progress_file = temp_queue_dir / "in_progress" / "in_progress_job.yaml"
        with open(in_progress_file, "w") as f:
            yaml.dump({"id": "in_progress_job", "status": "in_progress"}, f)

        # Create completed jobs
        for i in range(3):
            completed_file = temp_queue_dir / "completed" / f"completed_job_{i}.yaml"
            with open(completed_file, "w") as f:
                yaml.dump({"id": f"completed_job_{i}", "status": "completed"}, f)

        # Create failed job
        failed_file = temp_queue_dir / "failed" / "failed_job.yaml"
        with open(failed_file, "w") as f:
            yaml.dump({"id": "failed_job", "status": "failed"}, f)

        status = job_queue_service.get_queue_status()

        assert status["pending"] == 2
        assert status["in_progress"] == 1
        assert status["completed"] == 3
        assert status["failed"] == 1

    def test_get_queue_status_ignores_non_yaml(self, job_queue_service, temp_queue_dir):
        """Test that status ignores non-YAML files."""
        # Create a non-YAML file in pending
        non_yaml_file = temp_queue_dir / "pending" / "readme.txt"
        with open(non_yaml_file, "w") as f:
            f.write("This is not a job file")

        # Create a valid job
        job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        status = job_queue_service.get_queue_status()

        assert status["pending"] == 1  # Only the YAML file counts


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_status_directories(self, minimal_queue_dir):
        """Test queue status when status directories don't exist."""
        service = JobQueueService(queue_dir=minimal_queue_dir)

        # in_progress, completed, failed directories don't exist
        status = service.get_queue_status()

        # Should return 0 for missing directories (glob returns empty list)
        assert status["pending"] == 0
        assert status["in_progress"] == 0
        assert status["completed"] == 0
        assert status["failed"] == 0

    def test_submit_with_large_chat_id(self, job_queue_service, temp_queue_dir):
        """Test submission with very large chat_id."""
        large_chat_id = 9223372036854775807  # Max 64-bit signed int

        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=large_chat_id
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["telegram_chat_id"] == large_chat_id

    def test_submit_with_negative_chat_id(self, job_queue_service, temp_queue_dir):
        """Test submission with negative chat_id (group chats use negative IDs)."""
        negative_chat_id = -1001234567890

        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=negative_chat_id
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["telegram_chat_id"] == negative_chat_id

    def test_submit_with_empty_url(self, job_queue_service, temp_queue_dir):
        """Test submission with empty URL."""
        job_id = job_queue_service.submit_pdf_convert(
            url="",
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["url"] == ""

    def test_submit_with_empty_command(self, job_queue_service, temp_queue_dir, monkeypatch):
        """Test submission with empty command is rejected (no executable to match)."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        with pytest.raises(ValueError):
            job_queue_service.submit_custom_command(
                command="",
                chat_id=12345
            )

    def test_submit_with_unicode_content(self, job_queue_service, temp_queue_dir, monkeypatch):
        """Test submission with Unicode characters."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        unicode_command = "echo 'Hello World'"

        job_id = job_queue_service.submit_custom_command(
            command=unicode_command,
            chat_id=12345
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        with open(job_file, "r", encoding="utf-8") as f:
            job_data = yaml.safe_load(f)

        assert job_data["params"]["command"] == unicode_command

    def test_concurrent_submissions(self, job_queue_service):
        """Test that concurrent submissions don't conflict."""
        import concurrent.futures

        def submit_job(i):
            return job_queue_service.submit_pdf_convert(
                url=f"https://example.com/doc{i}.pdf",
                chat_id=12345
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(submit_job, i) for i in range(20)]
            job_ids = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All IDs should be unique
        assert len(set(job_ids)) == 20

    def test_yaml_file_format_valid(self, job_queue_service, temp_queue_dir):
        """Test that generated YAML files are properly formatted."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345,
            message_id=100,
            priority="high"
        )

        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"

        # Should be readable as valid YAML
        with open(job_file, "r") as f:
            content = f.read()

        # Parse and re-dump to verify format
        data = yaml.safe_load(content)
        assert data is not None

        # Check that it's not using flow style (should be block style)
        assert "{" not in content or content.count("{") <= content.count("created")

    def test_job_id_format(self, job_queue_service, monkeypatch):
        """Test that job IDs follow expected format."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")

        pdf_convert_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        pdf_save_id = job_queue_service.submit_pdf_save(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        command_id = job_queue_service.submit_custom_command(
            command="echo test",
            chat_id=12345
        )

        # Check format: {type}_{YYYYMMDD}_{HHMMSS}_{uuid_hex}
        assert pdf_convert_id.startswith("pdf_convert_")
        assert pdf_save_id.startswith("pdf_save_")
        assert command_id.startswith("command_")

        # Each should have 8 hex chars at the end
        for job_id in [pdf_convert_id, pdf_save_id, command_id]:
            parts = job_id.split("_")
            assert len(parts[-1]) == 8
            # Verify it's valid hex
            int(parts[-1], 16)


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_submit_pdf_convert_logs(self, job_queue_service, temp_queue_dir):
        """Test that PDF convert submission is logged."""
        with patch("src.services.job_queue_service.logger") as mock_logger:
            job_id = job_queue_service.submit_pdf_convert(
                url="https://example.com/doc.pdf",
                chat_id=12345
            )

            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert job_id in call_args

    def test_submit_pdf_save_logs(self, job_queue_service, temp_queue_dir):
        """Test that PDF save submission is logged."""
        with patch("src.services.job_queue_service.logger") as mock_logger:
            job_id = job_queue_service.submit_pdf_save(
                url="https://example.com/doc.pdf",
                chat_id=12345
            )

            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert job_id in call_args

    def test_submit_custom_command_logs(self, job_queue_service, temp_queue_dir, monkeypatch):
        """Test that custom command submission is logged."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        with patch("src.services.job_queue_service.logger") as mock_logger:
            job_id = job_queue_service.submit_custom_command(
                command="echo test",
                chat_id=12345
            )

            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert job_id in call_args


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration-style tests for job queue workflow."""

    def test_full_job_lifecycle(self, job_queue_service, temp_queue_dir):
        """Test complete job lifecycle: submit -> in_progress -> completed."""
        # Submit job
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        # Verify pending
        status = job_queue_service.get_queue_status()
        assert status["pending"] == 1

        # Move to in_progress
        source = temp_queue_dir / "pending" / f"{job_id}.yaml"
        dest = temp_queue_dir / "in_progress" / f"{job_id}.yaml"
        shutil.move(str(source), str(dest))

        status = job_queue_service.get_queue_status()
        assert status["pending"] == 0
        assert status["in_progress"] == 1

        # Move to completed
        source = dest
        dest = temp_queue_dir / "completed" / f"{job_id}.yaml"
        shutil.move(str(source), str(dest))

        status = job_queue_service.get_queue_status()
        assert status["in_progress"] == 0
        assert status["completed"] == 1

    def test_mixed_job_types(self, job_queue_service, temp_queue_dir, monkeypatch):
        """Test submitting different job types."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")

        # Submit different job types
        pdf_convert_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        pdf_save_id = job_queue_service.submit_pdf_save(
            url="https://example.com/doc.pdf",
            chat_id=12345
        )

        command_id = job_queue_service.submit_custom_command(
            command="echo test",
            chat_id=12345
        )

        # Verify all are pending
        status = job_queue_service.get_queue_status()
        assert status["pending"] == 3

        # Verify each file exists with correct type
        for job_id, expected_type in [
            (pdf_convert_id, "pdf_convert"),
            (pdf_save_id, "pdf_save"),
            (command_id, "custom_command")
        ]:
            job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
            with open(job_file, "r") as f:
                job_data = yaml.safe_load(f)
            assert job_data["type"] == expected_type


# =============================================================================
# Security: Job ID Validation at Submission
# =============================================================================


class TestJobIdValidationService:
    """Tests for job ID validation in the service layer."""

    def test_validate_job_id_accepts_valid_slugs(self):
        """Valid slug-format IDs should pass validation."""
        valid_ids = [
            "pdf_convert_20240101_120000_abcd1234",
            "simple-job",
            "ALL_CAPS_OK",
            "a",
            "mix-of_both-123",
        ]
        for jid in valid_ids:
            assert validate_job_id(jid) is True, f"Should accept {jid!r}"

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../etc/passwd",
            "../../traversal",
            "job/subdir",
            "job\\backslash",
            "",
            "job id spaces",
            ".hidden",
            "job;semicolon",
            "job\x00null",
        ],
    )
    def test_validate_job_id_rejects_bad_ids(self, bad_id):
        """IDs with path separators, spaces, or special chars are rejected."""
        assert validate_job_id(bad_id) is False

    def test_generated_ids_are_valid(self, job_queue_service, temp_queue_dir, monkeypatch):
        """All auto-generated job IDs pass strict validation."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        ids = [
            job_queue_service.submit_pdf_convert(
                url="https://example.com/doc.pdf", chat_id=1
            ),
            job_queue_service.submit_pdf_save(
                url="https://example.com/doc.pdf", chat_id=1
            ),
            job_queue_service.submit_custom_command(
                command="echo ok", chat_id=1
            ),
        ]
        for jid in ids:
            assert validate_job_id(jid), f"Generated ID {jid!r} should be valid"

    def test_file_written_inside_queue_dir(self, job_queue_service, temp_queue_dir):
        """Submitted job files resolve within the queue directory."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf", chat_id=1
        )
        job_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        resolved = os.path.realpath(str(job_file))
        assert resolved.startswith(os.path.realpath(str(temp_queue_dir)))


# =============================================================================
# Security: Command Allowlist in Service Layer
# =============================================================================


class TestCommandAllowlistService:
    """Tests for WORKER_COMMAND_ALLOWLIST enforcement at submission."""

    def test_submit_custom_command_checks_allowlist(self, temp_queue_dir):
        """submit_custom_command rejects commands not on the allowlist."""
        with patch.dict(os.environ, {"WORKER_COMMAND_ALLOWLIST": "echo,ls"}):
            service = JobQueueService(queue_dir=temp_queue_dir)
            with pytest.raises(ValueError, match="not in allowlist"):
                service.submit_custom_command(
                    command="rm -rf /", chat_id=12345
                )

    def test_submit_custom_command_allows_listed_command(self, temp_queue_dir):
        """submit_custom_command accepts commands on the allowlist."""
        with patch.dict(os.environ, {"WORKER_COMMAND_ALLOWLIST": "echo,ls,python3"}):
            service = JobQueueService(queue_dir=temp_queue_dir)
            job_id = service.submit_custom_command(
                command="echo hello world", chat_id=12345
            )
            assert job_id is not None

    def test_submit_custom_command_rejects_when_no_allowlist(self, temp_queue_dir):
        """submit_custom_command rejects ALL commands when no allowlist is set."""
        env = os.environ.copy()
        env.pop("WORKER_COMMAND_ALLOWLIST", None)
        with patch.dict(os.environ, env, clear=True):
            service = JobQueueService(queue_dir=temp_queue_dir)
            with pytest.raises(ValueError, match="[Aa]llowlist"):
                service.submit_custom_command(
                    command="echo hello", chat_id=12345
                )

    def test_submit_custom_command_rejects_shell_operators(self, temp_queue_dir):
        """submit_custom_command rejects commands with shell chaining."""
        with patch.dict(os.environ, {"WORKER_COMMAND_ALLOWLIST": "echo"}):
            service = JobQueueService(queue_dir=temp_queue_dir)
            for cmd in [
                "echo ok && rm -rf /",
                "echo ok; rm /",
                "echo ok | cat /etc/passwd",
            ]:
                with pytest.raises(ValueError, match="[Ss]hell operator"):
                    service.submit_custom_command(command=cmd, chat_id=12345)

    def test_submit_custom_command_rejects_empty_allowlist_string(self, temp_queue_dir):
        """An empty WORKER_COMMAND_ALLOWLIST string means nothing is allowed."""
        with patch.dict(os.environ, {"WORKER_COMMAND_ALLOWLIST": ""}):
            service = JobQueueService(queue_dir=temp_queue_dir)
            with pytest.raises(ValueError, match="[Aa]llowlist"):
                service.submit_custom_command(
                    command="echo hello", chat_id=12345
                )


# =============================================================================
# Security: Secure File Path Handling in Service
# =============================================================================


class TestSecureFilePathService:
    """Tests for secure file operations in the service layer."""

    def test_job_file_uses_realpath(self, job_queue_service, temp_queue_dir):
        """Job file path is resolved with realpath before write."""
        job_id = job_queue_service.submit_pdf_convert(
            url="https://example.com/doc.pdf", chat_id=1
        )
        expected_file = temp_queue_dir / "pending" / f"{job_id}.yaml"
        assert expected_file.exists()
        # Verify it resolves to the same canonical location
        real = os.path.realpath(str(expected_file))
        assert real == str(expected_file.resolve())
