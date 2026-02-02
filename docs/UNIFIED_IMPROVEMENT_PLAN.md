# Unified Improvement Plan — Telegram Agent

**Generated:** 2026-02-01
**Sources:** 14-day log/DB/architecture review + Codex security audit

---

## P0 — Fix Today (Production Broken)

### P0-1: Trail review scheduled job crashes on every run
- **File:** `src/bot/handlers/trail_handlers.py:365`
- **Bug:** Imports `get_user_settings` from `src.models.user_settings` — function does not exist in that module. Dead import that crashes the entire `send_scheduled_trail_review` function.
- **Impact:** Scheduled trail reviews at 15:13, 18:00, 22:00 all crash silently. No user notification.
- **Fix:** Remove the unused import line.
- **Acceptance criteria:** Scheduled trail review runs without ImportError; poll is sent to configured chat.
- **Testing:** Trigger `send_scheduled_trail_review` manually; verify no ImportError in `errors.log`.

### P0-2: ReactionTypeEmoji import crashes collect queue
- **File:** `src/bot/combined_processor.py:1536` (committed version)
- **Bug:** `from telegram import ReactionTypeEmoji` — class does not exist in installed python-telegram-bot version.
- **Impact:** Every message in collect mode crashes. 4 occurrences on Feb 1 alone.
- **Fix:** Already fixed on disk (replaced with `_mark_as_read_sync`), needs commit and deploy.
- **Acceptance criteria:** Collect queue processes messages without ImportError.
- **Testing:** Send voice/text while collect mode active; verify reactions appear and no errors in log.

### P0-3: ANTHROPIC_API_KEY environment variable race condition
- **File:** `src/services/claude_code_service.py:328`
- **Bug:** `os.environ.pop("ANTHROPIC_API_KEY")` in an async generator. Concurrent Claude sessions race on this process-global value.
- **Impact:** 85 "ANTHROPIC_API_KEY not set" errors in 14 days. Session names never generated.
- **Fix:** Use a threading lock around the pop/restore.
- **Acceptance criteria:** Session naming succeeds when API key is configured.
- **Testing:** Start two Claude sessions simultaneously; verify session_naming works.

### P0-4: No global error handler — messages silently disappear
- **File:** `src/bot/bot.py` — `_setup_application()`
- **Bug:** No error handlers registered. Unhandled exceptions logged but user gets zero feedback.
- **Impact:** User sends a message, it vanishes. Invisible failures.
- **Fix:** Register `application.add_error_handler()` that notifies the user.
- **Acceptance criteria:** Any unhandled exception produces a user-visible error in Telegram.
- **Testing:** Trigger an error; verify user sees an error reply.

### P0-5: Missing pip dependencies cause startup crash loops
- **Packages:** `python-telegram-bot[job-queue]`, `frontmatter`
- **Impact:** 3.5h outage Jan 27, ongoing degraded mode since Jan 28.
- **Fix:** Install missing packages. Add to requirements.txt.
- **Acceptance criteria:** Bot starts without degraded mode warning.
- **Testing:** `pip install -r requirements.txt` succeeds; bot starts cleanly.

---

## P1 — Fix This Week (Degraded Functionality)

### P1-1: Embedding service bytes/str type error
- **File:** `src/services/embedding_service.py:113`
- **Impact:** 64 errors. No image embeddings since Jan 28.
- **Testing:** Send image; verify embedding stored in DB.

### P1-2: Callback data lost on restart
- **File:** `src/bot/callback_data_manager.py`
- **Impact:** 230 errors. Buttons on older messages are dead.
- **Fix:** Persist callback data to SQLite.
- **Testing:** Restart bot; press old button; verify it works.

### P1-3: SRS buttons exceed Telegram 64-byte callback limit
- **Impact:** 10 BadRequest errors. SRS review broken.
- **Fix:** Use callback data cache for SRS buttons.

### P1-4: Unbounded _session_messages memory growth
- **File:** `src/services/reply_context.py:134`
- **Fix:** Add cleanup; cap size.

### P1-5: Zombie processes after subprocess kill
- **File:** `src/services/claude_subprocess.py:193`
- **Fix:** Add `await process.wait()` after kill.

### P1-6: Poll template counters never increment
- **Impact:** Analytics broken. All templates show times_sent=0.
- **Fix:** Update counters on send.

---

## P2 — Fix This Month (Technical Debt)

- P2-1: Messages table empty (0 rows, no persistence)
- P2-2: 8 test/artifact tables in production database
- P2-3: Temp file leaks on download failure
- P2-4: .venv/ tracked in git
- P2-5: sqlite-vss extension path references wrong username
- P2-6: Hardcoded project path map in subprocess
- P2-7: Version mismatch in FastAPI app
- P2-8: 74 active Claude sessions with no cleanup

---

## P3 — Infrastructure (From Codex Audit)

### Security
- [ ] Rate limiting, request size limits, HMAC checks
- [ ] Media validation, sandboxed processing
- [ ] Outbound file allowlist, secret redaction
- [ ] MCP/tool execution restrictions

### Configuration
- [ ] Pydantic Settings validator
- [ ] Standardized secret loading order

### Observability
- [ ] Unified JSON logging with request IDs
- [ ] Metrics endpoint
- [ ] DB backup/retention

### Testing & CI
- [ ] Coverage gates, targeted tests
- [ ] GitHub Actions pipeline
- [ ] Pre-commit hooks, dependency pinning

---

| Priority | Count | Timeline |
|----------|-------|----------|
| P0 | 5 | Today |
| P1 | 6 | This week |
| P2 | 8 | This month |
| P3 | 15+ | Ongoing |

**Review cadence:** Automated 12-hour review via Telegram.
