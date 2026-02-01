# Improvement Plan (Telegram Agent)

Updated: Feb 1, 2026

## Remaining Work

### 1. Media Pipeline Hardening

What's done: extension allowlist, size cap, centralized validation in `image_service.py`.

Still needed:
- MIME sniffing (validate actual file content, not just extension)
- Sandbox ffmpeg/imagemagick calls with CPU/time limits (ulimit/timeout wrapper)
- EXIF/metadata stripping before storing or sending images back
- Outbound file allowlist — restrict auto-sent file paths to media/output directories

### 2. Observability

What's done: PII log filter, 30-day TimedRotatingFileHandler, audit log for security events.

Still needed:
- JSON structured logging with request/task IDs across FastAPI + bot handlers + background tasks
- `/metrics` endpoint (latency, queue depth, active tasks, Claude call counts, external API errors)
- DB and media backup/retention strategy with documented restore steps

### 3. CI & Supply Chain

What's done: pre-commit (bandit/black/isort/detect-private-key), dep upper-bound pinning, `scripts/security_scan.sh` (bandit + pip-audit + safety + security tests).

Still needed:
- GitHub Actions pipeline: lint, mypy, pytest with coverage, docker build
- Coverage gate (fail CI below threshold)
- `requirements.lock` with hashes (pip-tools or uv)
- `Makefile` or `justfile` for common dev commands (lint/test/format/run)
