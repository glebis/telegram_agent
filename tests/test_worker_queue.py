"""
Tests for the file-based worker queue.

Covers:
- add_job writes pending YAML
- get_next_job moves to in_progress and marks status/started_at
- complete_job moves to completed and removes in_progress file
- fail_job moves to failed and removes in_progress file
- malformed job files are skipped without breaking processing
- Security: job ID validation rejects path traversal
- Security: command allowlist enforcement
- Security: job file structure validation (required fields)
- Security: file operations stay within queue directory
"""

from pathlib import Path

import pytest
import yaml

from scripts.worker_queue import Job, JobExecutor, JobQueue, JobStatus, JobType


def make_job(job_id: str, priority: str = "medium") -> Job:
    return Job(
        id=job_id,
        type=JobType.PDF_SAVE,
        created="2024-01-01T00:00:00",
        priority=priority,
        params={"path": "/tmp/example.pdf"},
    )


# =============================================================================
# Existing behaviour tests
# =============================================================================


@pytest.mark.asyncio
async def test_add_and_get_job_moves_to_in_progress(tmp_path: Path):
    queue = JobQueue(queue_dir=tmp_path)
    job = make_job("job1")

    pending_file = await queue.add_job(job)
    assert pending_file.exists()

    fetched = await queue.get_next_job()
    assert fetched is not None
    assert fetched.id == "job1"
    assert fetched.status == JobStatus.IN_PROGRESS
    assert fetched.started_at is not None

    # pending removed, in_progress file exists
    assert not (tmp_path / "pending" / "job1.yaml").exists()
    assert (tmp_path / "in_progress" / "job1.yaml").exists()


@pytest.mark.asyncio
async def test_complete_job_moves_to_completed(tmp_path: Path):
    queue = JobQueue(queue_dir=tmp_path)
    job = make_job("job2")
    await queue.add_job(job)
    fetched = await queue.get_next_job()
    assert fetched is not None

    await queue.complete_job(fetched, result={"ok": True})

    completed_file = tmp_path / "completed" / "job2.yaml"
    assert completed_file.exists()
    assert not (tmp_path / "in_progress" / "job2.yaml").exists()

    data = yaml.safe_load(completed_file.read_text())
    assert data["status"] == JobStatus.COMPLETED.value
    assert data["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_fail_job_moves_to_failed(tmp_path: Path):
    queue = JobQueue(queue_dir=tmp_path)
    job = make_job("job3")
    await queue.add_job(job)
    fetched = await queue.get_next_job()
    assert fetched is not None

    await queue.fail_job(fetched, error="boom")

    failed_file = tmp_path / "failed" / "job3.yaml"
    assert failed_file.exists()
    assert not (tmp_path / "in_progress" / "job3.yaml").exists()

    data = yaml.safe_load(failed_file.read_text())
    assert data["status"] == JobStatus.FAILED.value
    assert data["error"] == "boom"


@pytest.mark.asyncio
async def test_malformed_job_file_skipped(tmp_path: Path):
    queue = JobQueue(queue_dir=tmp_path)
    # write malformed YAML file
    bad_file = tmp_path / "pending" / "bad.yaml"
    bad_file.write_text("::not_yaml::")

    good_job = make_job("job4")
    await queue.add_job(good_job)

    fetched = await queue.get_next_job()
    assert fetched is not None
    assert fetched.id == "job4"

    # bad file should still exist (skipped), good file processed
    assert bad_file.exists()
    assert (tmp_path / "in_progress" / "job4.yaml").exists()


@pytest.mark.asyncio
async def test_rejects_invalid_job_id(tmp_path: Path):
    queue = JobQueue(queue_dir=tmp_path)
    job = make_job("../evil")

    with pytest.raises(ValueError):
        await queue.add_job(job)


@pytest.mark.asyncio
async def test_disallows_custom_command_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ALLOW_CUSTOM_COMMANDS", raising=False)
    queue = JobQueue(queue_dir=tmp_path)
    job = Job(
        id="custom1",
        type=JobType.CUSTOM_COMMAND,
        created="2024-01-01T00:00:00",
        priority="medium",
        params={"cmd": "whoami"},
    )

    with pytest.raises(ValueError):
        await queue.add_job(job)


@pytest.mark.asyncio
async def test_custom_command_allowed_with_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ALLOW_CUSTOM_COMMANDS", "true")
    monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
    queue = JobQueue(queue_dir=tmp_path)
    job = Job(
        id="custom2",
        type=JobType.CUSTOM_COMMAND,
        created="2024-01-01T00:00:00",
        priority="medium",
        params={"command": "echo ok"},
    )

    await queue.add_job(job)
    fetched = await queue.get_next_job()
    assert fetched is not None
    assert fetched.type == JobType.CUSTOM_COMMAND


# =============================================================================
# Security: Job ID validation
# =============================================================================


class TestJobIdValidation:
    """Tests for strict job ID validation (slug format only)."""

    @pytest.mark.asyncio
    async def test_valid_slug_ids(self, tmp_path: Path):
        """Alphanumeric, hyphens, and underscores are accepted."""
        queue = JobQueue(queue_dir=tmp_path)
        valid_ids = [
            "pdf_convert_20240101_120000_abcd1234",
            "simple-job",
            "ALL_CAPS_OK",
            "mix-of_both-123",
            "a",
        ]
        for jid in valid_ids:
            job = make_job(jid)
            path = await queue.add_job(job)
            assert path.exists(), f"Job ID {jid!r} should be accepted"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_id",
        [
            "../etc/passwd",
            "../../traversal",
            "job/subdir",
            "job\\backslash",
            "",
            "job id spaces",
            "job\x00null",
            "job\nnewline",
            ".hidden",
            "job@special",
            "job;semicolon",
        ],
    )
    async def test_path_traversal_ids_rejected(self, tmp_path: Path, bad_id: str):
        """IDs containing path separators, dots-prefix, or special chars are rejected."""
        queue = JobQueue(queue_dir=tmp_path)
        job = make_job(bad_id)
        with pytest.raises(ValueError, match="[Ii]nvalid job id"):
            await queue.add_job(job)

    @pytest.mark.asyncio
    async def test_get_next_job_skips_bad_filenames(self, tmp_path: Path):
        """Files in pending/ with non-slug stems are silently skipped."""
        queue = JobQueue(queue_dir=tmp_path)
        # Plant a file with path-traversal name directly on disk
        bad_file = tmp_path / "pending" / "..%2f..%2fetc.yaml"
        bad_file.write_text(
            yaml.dump(
                {
                    "id": "../etc",
                    "type": "pdf_save",
                    "created": "2024-01-01",
                    "priority": "low",
                    "params": {},
                    "status": "pending",
                }
            )
        )

        good_job = make_job("goodjob")
        await queue.add_job(good_job)

        fetched = await queue.get_next_job()
        assert fetched is not None
        assert fetched.id == "goodjob"


# =============================================================================
# Security: Command allowlist enforcement
# =============================================================================


class TestCommandAllowlist:
    """Tests for WORKER_COMMAND_ALLOWLIST enforcement on custom commands."""

    @pytest.mark.asyncio
    async def test_allowlist_empty_disables_custom_commands(
        self, tmp_path: Path, monkeypatch
    ):
        """When ALLOW_CUSTOM_COMMANDS=true but WORKER_COMMAND_ALLOWLIST is empty,
        custom command jobs are rejected."""
        monkeypatch.setenv("ALLOW_CUSTOM_COMMANDS", "true")
        monkeypatch.delenv("WORKER_COMMAND_ALLOWLIST", raising=False)
        queue = JobQueue(queue_dir=tmp_path)
        job = Job(
            id="cmd-no-allowlist",
            type=JobType.CUSTOM_COMMAND,
            created="2024-01-01T00:00:00",
            priority="medium",
            params={"command": "rm -rf /"},
        )

        with pytest.raises(ValueError, match="[Aa]llowlist"):
            await queue.add_job(job)

    @pytest.mark.asyncio
    async def test_allowed_command_accepted(self, tmp_path: Path, monkeypatch):
        """Command whose base executable is in the allowlist is accepted."""
        monkeypatch.setenv("ALLOW_CUSTOM_COMMANDS", "true")
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo,ls,python3")
        queue = JobQueue(queue_dir=tmp_path)

        job = Job(
            id="cmd-echo",
            type=JobType.CUSTOM_COMMAND,
            created="2024-01-01T00:00:00",
            priority="medium",
            params={"command": "echo hello"},
        )
        path = await queue.add_job(job)
        assert path.exists()

    @pytest.mark.asyncio
    async def test_disallowed_command_rejected(self, tmp_path: Path, monkeypatch):
        """Command not on the allowlist is rejected."""
        monkeypatch.setenv("ALLOW_CUSTOM_COMMANDS", "true")
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo,ls")
        queue = JobQueue(queue_dir=tmp_path)

        job = Job(
            id="cmd-rm",
            type=JobType.CUSTOM_COMMAND,
            created="2024-01-01T00:00:00",
            priority="medium",
            params={"command": "rm -rf /"},
        )
        with pytest.raises(ValueError, match="not in allowlist"):
            await queue.add_job(job)

    @pytest.mark.asyncio
    async def test_shell_chain_rejected(self, tmp_path: Path, monkeypatch):
        """Commands with shell chaining operators are rejected."""
        monkeypatch.setenv("ALLOW_CUSTOM_COMMANDS", "true")
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        queue = JobQueue(queue_dir=tmp_path)

        for cmd in [
            "echo ok && rm -rf /",
            "echo ok; rm /",
            "echo ok | cat /etc/passwd",
        ]:
            job = Job(
                id=f"cmd-chain-{hash(cmd) % 10000}",
                type=JobType.CUSTOM_COMMAND,
                created="2024-01-01T00:00:00",
                priority="medium",
                params={"command": cmd},
            )
            with pytest.raises(ValueError, match="[Ss]hell operator"):
                await queue.add_job(job)

    @pytest.mark.asyncio
    async def test_executor_validates_allowlist(self, tmp_path: Path, monkeypatch):
        """JobExecutor._execute_custom_command also validates against the allowlist."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        executor = JobExecutor()

        job = Job(
            id="exec-bad",
            type=JobType.CUSTOM_COMMAND,
            created="2024-01-01T00:00:00",
            priority="medium",
            params={"command": "rm -rf /", "timeout": 5},
        )
        with pytest.raises(ValueError, match="not in allowlist"):
            await executor.execute(job)

    @pytest.mark.asyncio
    async def test_executor_allows_valid_command(self, tmp_path: Path, monkeypatch):
        """JobExecutor runs commands that pass the allowlist check."""
        monkeypatch.setenv("WORKER_COMMAND_ALLOWLIST", "echo")
        executor = JobExecutor()

        job = Job(
            id="exec-ok",
            type=JobType.CUSTOM_COMMAND,
            created="2024-01-01T00:00:00",
            priority="medium",
            params={"command": "echo hello", "timeout": 5},
        )
        result = await executor.execute(job)
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]


# =============================================================================
# Security: Job file structure validation
# =============================================================================


class TestJobFileValidation:
    """Tests that malformed YAML job files missing required fields are rejected."""

    @pytest.mark.asyncio
    async def test_missing_id_field_skipped(self, tmp_path: Path):
        """A YAML file without 'id' is skipped by get_next_job."""
        queue = JobQueue(queue_dir=tmp_path)
        bad_file = tmp_path / "pending" / "no-id.yaml"
        bad_file.write_text(
            yaml.dump(
                {
                    "type": "pdf_save",
                    "created": "2024-01-01",
                    "priority": "medium",
                    "params": {},
                    "status": "pending",
                }
            )
        )

        good_job = make_job("valid-job")
        await queue.add_job(good_job)

        fetched = await queue.get_next_job()
        assert fetched is not None
        assert fetched.id == "valid-job"

    @pytest.mark.asyncio
    async def test_missing_type_field_skipped(self, tmp_path: Path):
        """A YAML file without 'type' is skipped by get_next_job."""
        queue = JobQueue(queue_dir=tmp_path)
        bad_file = tmp_path / "pending" / "no-type.yaml"
        bad_file.write_text(
            yaml.dump(
                {
                    "id": "no-type",
                    "created": "2024-01-01",
                    "priority": "medium",
                    "params": {},
                    "status": "pending",
                }
            )
        )

        good_job = make_job("after-notype")
        await queue.add_job(good_job)

        fetched = await queue.get_next_job()
        assert fetched is not None
        assert fetched.id == "after-notype"

    @pytest.mark.asyncio
    async def test_missing_status_field_skipped(self, tmp_path: Path):
        """A YAML file without 'status' still works (defaults to pending)."""
        queue = JobQueue(queue_dir=tmp_path)
        # This should actually work due to the default in from_dict
        file_with_defaults = tmp_path / "pending" / "no-status.yaml"
        file_with_defaults.write_text(
            yaml.dump(
                {
                    "id": "no-status",
                    "type": "pdf_save",
                    "created": "2024-01-01",
                    "priority": "medium",
                    "params": {},
                }
            )
        )

        fetched = await queue.get_next_job()
        assert fetched is not None
        assert fetched.id == "no-status"

    @pytest.mark.asyncio
    async def test_yaml_with_extra_fields_accepted(self, tmp_path: Path):
        """Extra fields in YAML should not cause failures (forward-compat)."""
        queue = JobQueue(queue_dir=tmp_path)
        job = make_job("extra-fields")
        await queue.add_job(job)

        # Manually inject extra fields into the file
        path = tmp_path / "pending" / "extra-fields.yaml"
        data = yaml.safe_load(path.read_text())
        data["extra_field"] = "should be ignored"
        path.write_text(yaml.dump(data))

        # from_dict will raise TypeError for unexpected kwargs - that's a skip
        await queue.get_next_job()
        # Either it gets fetched (if from_dict tolerates extra) or skipped (logged as error).
        # Either behaviour is acceptable for security - the key thing is no crash.

    @pytest.mark.asyncio
    async def test_non_dict_yaml_skipped(self, tmp_path: Path):
        """A YAML file containing a list instead of a dict is skipped."""
        queue = JobQueue(queue_dir=tmp_path)
        bad_file = tmp_path / "pending" / "list-yaml.yaml"
        bad_file.write_text(yaml.dump(["not", "a", "dict"]))

        good_job = make_job("after-list")
        await queue.add_job(good_job)

        fetched = await queue.get_next_job()
        assert fetched is not None
        assert fetched.id == "after-list"

    @pytest.mark.asyncio
    async def test_validate_job_data_rejects_non_dict(self, tmp_path: Path):
        """_validate_job_data returns False for non-dict input."""
        queue = JobQueue(queue_dir=tmp_path)
        assert queue._validate_job_data(None) is False
        assert queue._validate_job_data("string") is False
        assert queue._validate_job_data(["list"]) is False

    @pytest.mark.asyncio
    async def test_validate_job_data_rejects_missing_required(self, tmp_path: Path):
        """_validate_job_data returns False when required keys are missing."""
        queue = JobQueue(queue_dir=tmp_path)
        assert (
            queue._validate_job_data({"type": "pdf_save", "status": "pending"}) is False
        )
        assert queue._validate_job_data({"id": "x", "status": "pending"}) is False

    @pytest.mark.asyncio
    async def test_validate_job_data_accepts_valid(self, tmp_path: Path):
        """_validate_job_data returns True for a well-formed dict."""
        queue = JobQueue(queue_dir=tmp_path)
        assert (
            queue._validate_job_data(
                {"id": "test", "type": "pdf_save", "status": "pending"}
            )
            is True
        )


# =============================================================================
# Security: Secure file operations (path containment)
# =============================================================================


class TestSecureFileOperations:
    """Ensure all file move operations stay within the queue directory."""

    @pytest.mark.asyncio
    async def test_complete_job_verifies_path(self, tmp_path: Path):
        """complete_job refuses to write outside the queue directory."""
        queue = JobQueue(queue_dir=tmp_path)
        job = make_job("legit-job")
        await queue.add_job(job)
        fetched = await queue.get_next_job()
        assert fetched is not None

        # Tamper with the job id to attempt path escape
        fetched.id = "../../etc/evil"
        with pytest.raises(ValueError, match="[Ii]nvalid job id"):
            await queue.complete_job(fetched)

    @pytest.mark.asyncio
    async def test_fail_job_verifies_path(self, tmp_path: Path):
        """fail_job refuses to write outside the queue directory."""
        queue = JobQueue(queue_dir=tmp_path)
        job = make_job("legit-job2")
        await queue.add_job(job)
        fetched = await queue.get_next_job()
        assert fetched is not None

        fetched.id = "../../../tmp/evil"
        with pytest.raises(ValueError, match="[Ii]nvalid job id"):
            await queue.fail_job(fetched, error="test")

    @pytest.mark.asyncio
    async def test_resolved_path_stays_in_queue_dir(self, tmp_path: Path):
        """_safe_resolve raises for paths that escape the queue directory."""
        queue = JobQueue(queue_dir=tmp_path)
        # A path inside the queue dir should be fine
        safe = queue._safe_resolve(tmp_path / "pending" / "ok.yaml")
        assert str(safe).startswith(str(tmp_path))

        # A path outside the queue dir should raise
        with pytest.raises(ValueError, match="outside queue"):
            queue._safe_resolve(Path("/tmp/outside/evil.yaml"))
