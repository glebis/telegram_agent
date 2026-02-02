"""
Tests for the file-based worker queue.

Focus on the existing behaviors (no new features):
- add_job writes pending YAML
- get_next_job moves to in_progress and marks status/started_at
- complete_job moves to completed and removes in_progress file
- fail_job moves to failed and removes in_progress file
- malformed job files are skipped without breaking processing
"""

import asyncio
import yaml
from pathlib import Path

import pytest

from scripts.worker_queue import Job, JobQueue, JobStatus, JobType


def make_job(job_id: str, priority: str = "medium") -> Job:
    return Job(
        id=job_id,
        type=JobType.PDF_SAVE,
        created="2024-01-01T00:00:00",
        priority=priority,
        params={"path": "/tmp/example.pdf"},
    )


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
    queue = JobQueue(queue_dir=tmp_path)
    job = Job(
        id="custom2",
        type=JobType.CUSTOM_COMMAND,
        created="2024-01-01T00:00:00",
        priority="medium",
        params={"cmd": "echo ok"},
    )

    await queue.add_job(job)
    fetched = await queue.get_next_job()
    assert fetched is not None
    assert fetched.type == JobType.CUSTOM_COMMAND
