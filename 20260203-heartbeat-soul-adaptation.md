# Heartbeat & SOUL Integration Ideas for telegram_agent

Date: 2026-02-03

## Heartbeat (scheduled check-ins)
- Add `HeartbeatScheduler` using the existing `telegram.ext.Application.job_queue` (pattern from `poll_scheduler.py` / `trail_scheduler.py`). Config keys: `HEARTBEAT_EVERY`, `HEARTBEAT_ACTIVE_HOURS`, `HEARTBEAT_TARGET_CHAT_IDS`, `HEARTBEAT_INCLUDE_REASONING`, `HEARTBEAT_ACK_MAX_CHARS`.
- Create `HeartbeatService` that composes a prompt from `HEARTBEAT.md` (workspace root or `config/HEARTBEAT.md`) with a default OpenClaw-style prompt. On response: honor `HEARTBEAT_OK`—suppress OK-only replies ≤ `ack_max_chars`; optionally emit a separate reasoning message when enabled.
- Delivery controls mirroring OpenClaw visibility: `HEARTBEAT_SHOW_OK`, `HEARTBEAT_SHOW_ALERTS`, `HEARTBEAT_USE_INDICATOR`. For Telegram, indicators can be chat actions or logs.
- Manual trigger: admin `/heartbeat` command plus CLI hook in `scripts/start_dev.py` to enqueue an immediate run; reuse the same service for consistency.
- Safety/cost: skip if `job_queue` backlog is high, outside `active_hours`, or when `HEARTBEAT.md` is empty/headers-only.

### Integration plan (detailed)
1) **Config**  
   - Add defaults to `config/defaults.yaml` under a new `heartbeat:` block.  
   - Map env vars in `src/core/config.py` (e.g., `heartbeat_every: str = "30m"`, `heartbeat_active_hours: Optional[str]`, `heartbeat_show_ok: bool`).  
   - Parse `HEARTBEAT_TARGET_CHAT_IDS` as CSV of ints; fallback to “last chat” behavior if empty.

2) **Service** (`src/services/heartbeat_service.py`)  
   - Dependencies: `llm_service` (or `claude_code_service`), `keyboard_service` (for inline buttons if desired), `JobQueueService` for backlog check, `Vault`/filesystem for `HEARTBEAT.md`.  
   - Steps: load/trim `HEARTBEAT.md`; if empty → return “skip”. Build prompt body = file content or default string. Call LLM with short token cap. Postprocess: detect `HEARTBEAT_OK` at start/end, strip and discard when remaining chars ≤ `ack_max_chars`; otherwise deliver alert. Optional: if `include_reasoning` and model supports it, send second message prefixed `Reasoning:`.  
   - Provide `run(chat_id: int | None)` that returns a `HeartbeatResult(status, delivered, skipped_reason)`.

3) **Scheduler** (`src/services/heartbeat_scheduler.py`)  
   - Wire into bot init alongside poll/trail schedulers. Use `run_repeating` with parsed duration; respect `active_hours` (local tz from settings). Check queue depth (via `JobQueueService.get_queue_status()`) before firing to avoid pileups.  
   - `target_chat_ids`: if set, iterate; if empty, resolve “last used” chat (persist last chat per user in Redis/db or reuse existing state used by Claude mode).  
   - Log heartbeat runs with outcome for observability.

4) **Command surface**  
   - Add `/heartbeat` admin command in `src/bot/handlers` that triggers `HeartbeatService.run` immediately for the current chat (or a supplied chat id). Include reply markup with “Run again” button that calls the same handler.  
   - CLI: add a subcommand to `scripts/start_dev.py` or a small `scripts/heartbeat.py` that instantiates settings + service and runs once (for cron/manual wake).

5) **Messaging/UX**  
   - Respect visibility flags:  
     - If `show_alerts` false → suppress non-OK replies.  
     - If `show_ok` false → drop OK acks silently.  
     - If `use_indicator` true → emit chat action or log event “heartbeat-ok/heartbeat-alert”.  
   - Keep messages compact to stay under Telegram chunk limits.

6) **Tests**  
   - Unit: parsing of `HEARTBEAT.md` empty/non-empty; `HEARTBEAT_OK` stripping; active-hours gate; queue-depth gate.  
   - Integration: simulate a heartbeat run via command and scheduler with a fake LLM stub.

## SOUL.md persona
- Add `SOUL.md` (or config-driven path `SOUL_PATH`, default `config/SOUL.md` or vault) and inject into system prompts used by `claude_code_service`/`llm_service`.
- Provide admin `/soul` command to view/update; mirror changes into the vault via existing vault services for persistence.
- Keep the template tight (core truths, boundaries, vibe) following OpenClaw’s `SOUL.md`; optionally support playful swap with `SOUL_EVIL.md` gated by a low-probability flag.
- Document persona usage in `docs/FEATURES.md` and ship a starter template in `config/`.

### Integration plan (detailed)
1) **Config & file location**  
   - Add `SOUL_PATH` env + default (`config/SOUL.md`). Optional `SOUL_EVIL_PATH` and `SOUL_EVIL_CHANCE` (0–1) if you want the swap hook.  
   - Ship `config/SOUL.template.md` seeded with the OpenClaw “core truths/boundaries/vibe”; copy to `SOUL.md` during setup wizard if absent.

2) **Prompt injection**  
   - In `claude_code_service` and generic `llm_service`, load the SOUL text once per process (cache + reload on mtime change). Prepend it to the system prompt after safety/system rules but before user text to keep persona consistent.  
   - If evil-swap enabled: at call time, choose SOUL vs SOUL_EVIL by chance or during a configured purge window; do not write to disk, only swap injected text.

3) **Commands**  
   - Add admin `/soul` command with submodes:  
     - `/soul show` → send current persona (paginated if long).  
     - `/soul edit <text>` or reply-to-edit → overwrite file; confirm and reload cache.  
     - `/soul reset` → restore from template.  
   - Permissions: restrict to admins already used for Claude mode.

4) **Vault sync (optional)**  
   - If `vault_path` exists, mirror updates to `<vault>/SOUL.md` for continuity; prefer symlink if acceptable, else write both locations on change.

5) **Docs & safety**  
   - Add a short section in `docs/FEATURES.md` describing persona scope, boundaries, and how to edit. Warn against secrets in SOUL.  
   - Keep persona concise to control token costs; enforce max size (e.g., 2–3 KB) when saving.
