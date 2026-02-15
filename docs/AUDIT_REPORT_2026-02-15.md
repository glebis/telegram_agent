# Telegram Agent — Comprehensive Audit Report

**Date:** 2026-02-15 | **Codebase:** 150 source files, ~3,625 tests, 130 test files
**Sources:** 5 parallel analysis agents + Claude Code usage insights report (412 messages / 77 sessions)

---

## EXECUTIVE SUMMARY

The telegram_agent is a **well-architected personal Telegram bot** with strong foundational security, a layered architecture, and a comprehensive plugin system. However, the audit reveals **3 critical security findings, 4 high-severity architecture violations, and 25+ UX issues** that collectively explain the friction patterns visible in the usage data (32 "wrong approach" events, 17 "buggy code" events, repeated debugging sessions).

### Scorecard

| Dimension | Grade | Summary |
|-----------|-------|---------|
| **Security** | B+ | Strong auth/subprocess isolation; weakened by hardcoded crypto salt and optional webhook secret |
| **Architecture** | B- | Clean layers documented but 4 service-to-handler violations; dual DI patterns; 25+ uncontained singletons |
| **Coherence** | C+ | Config accessed 3 different ways; timeout defaults conflict between yaml and code; naming inconsistent |
| **UX & Flow** | C | Silent message drops for stickers/GIFs; buffer overflow unnotified; 2.5s delay undocumented; /todo missing from /help |
| **Test Coverage** | B | 3,625 tests exist; but 24 handler files completely untested; rate limiting middleware untested |

---

## 1. SECURITY

### Critical Findings

| # | Severity | File | Issue |
|---|----------|------|-------|
| S1 | **CRITICAL** | `src/core/vector_db.py:74,78` | SQL f-string interpolation in `load_extension()` — path values injected into raw SQL |
| S2 | **HIGH** | `src/utils/encryption.py:41` | Hardcoded salt `b"telegram_agent_field_encryption_v1"` — identical across all instances, weakens PBKDF2 |
| S3 | **HIGH** | `src/utils/encryption.py:56,73` | Encryption silently falls back to plaintext if Fernet unavailable — no production guard |

### Medium Findings (10 total)

- **Webhook secret optional in dev/test** (`src/main.py:82-85`) — forge webhook updates in non-prod
- **API_SECRET_KEY optional** (`src/core/security.py:154`) — falls back to shared webhook secret
- **Health endpoint leaks version** (`src/api/health.py:91-98`) — aids attacker fingerprinting
- **Per-IP rate limiting ineffective for webhooks** (`src/middleware/rate_limit.py:114`) — all Telegram traffic comes from same IPs
- **No distributed rate limiting** — in-memory buckets won't survive horizontal scaling
- **Error messages leak internals** in webhook admin endpoints (`src/api/webhook.py:189,229`)
- **Dev dependencies in production requirements.txt** — pytest, black, flake8 increase attack surface
- **Loose version pinning** — many packages use `>=` without upper bound
- **Log redaction incomplete** — user-provided secrets not matching regex patterns leak
- **Silent DB migration errors** (`src/core/database.py:70-154`) — `except Exception: pass` swallows all errors

### What's Done Well

- HMAC timing-safe comparisons (`hmac.compare_digest`) throughout
- Subprocess isolation pattern properly avoids command injection — data passed via stdin/JSON, not f-strings
- Secret redaction in structured logging (`src/utils/logging.py`)
- Admin API endpoints properly protected with dependency injection
- File upload validation: MIME allowlist + 10MB size limit + path traversal defense-in-depth

---

## 2. ARCHITECTURE

### Critical Layer Violations (4 found)

The documented architecture says **services must not import from bot layer**. Four services violate this:

| Service | Imports From | File |
|---------|-------------|------|
| `accountability_scheduler.py` | `..bot.handlers.accountability_commands` | `:78` |
| `claude_code_service.py` | `..bot.handlers.base._claude_mode_cache` | `:620` |
| `poll_scheduler.py` | `..bot.handlers.poll_handlers` | `:51` |
| `trail_scheduler.py` | `..bot.handlers.trail_handlers` | `:59` |

**Root cause:** Schedulers need to send messages back but reach into the handler layer instead of using an abstraction. **Fix:** Create a `MessageDispatcher` service that handlers implement.

### Dual Dependency Injection Problem

The project uses **two competing patterns** for service access:

- **Pattern A:** 25+ standalone `get_X_service()` singleton getters across `src/services/`
- **Pattern B:** `ServiceContainer` in `src/core/services.py` registering only 16 services

Result: The container is underutilized. Services are inconsistently accessed, making testing and lifecycle management harder.

### Configuration Incoherence

Configuration is accessed **three different ways**:
1. `get_settings()` (Pydantic)
2. `get_config_value("key", default)` (YAML dot notation)
3. `os.getenv("KEY", "default")` (direct env vars)

**Concrete conflict:** `claude_code_service.py:13` sets `SESSION_IDLE_TIMEOUT_MINUTES=480` from env, but `config/defaults.yaml` says `60` and `config.py` says `60`. Users see inconsistent behavior depending on which code path runs.

### Code Duplication

- Voice/video transcription logic duplicated in `combined_processor.py:2065` and `:2130`
- Voice settings UI pattern `chat_obj.X if chat_obj else default` repeated at lines 57, 180, 232, 407, 445
- `send_message_sync()` subprocess wrapper duplicated across handlers

---

## 3. UX & MESSAGE FLOW

### Critical UX Issues

| # | Issue | Impact |
|---|-------|--------|
| U1 | **Stickers, GIFs, dice silently dropped** — no handler, no error message | Users get zero feedback |
| U2 | **Buffer overflow drops messages silently** — 20+ msgs in 2.5s window -> data loss with only debug log | Users lose messages with no notification |
| U3 | **`/todo` missing from /help** — command exists but is undocumented in help categories | Feature undiscoverable |
| U4 | **No auto-splitting for >4096 char responses** — long image analyses may fail silently | Truncated/failed messages |
| U5 | **Mixed parse_mode** — most handlers use HTML but `todo_commands.py:212` uses Markdown | Format breakage |

### Callback Dead-Ends

- Callbacks with no timeout protection — user sees "Loading" state, operation fails silently, message stays in loading state
- Inconsistent `query.answer()` handling — some callbacks pre-answer, others don't
- Voice settings changes save without confirmation — user doesn't know if tap succeeded

### The 2.5s Buffer Problem

Every message waits 2.5s before processing (to combine multi-part inputs). This:
- Makes single messages feel sluggish
- Is never explained to users
- Combined with buffer overflow behavior, can silently lose rapid-fire messages

### Usage Report Correlation

The usage report's top friction (32 "wrong approach" events, 17 "buggy code") maps directly to:
- **Fix-deploy-pray cycle:** No verification step after code changes — the audit confirms no auto-split, no length validation, silent failures
- **Debugging persistence:** 12+ debugging sessions traced to async deadlocks, aiosqlite timeouts, and webhook issues — all paths with thin error UX

---

## 4. TEST COVERAGE

### By the Numbers

| Category | Coverage |
|----------|----------|
| Source files | 150 |
| Test files | 130 (87% file coverage) |
| Test functions | ~3,625 |
| **Untested handler files** | **24 (0% behavior coverage)** |
| **Untested middleware** | **rate_limit.py, user_rate_limit.py** |
| **Untested services** | **stt_service, polling_service, SRS (5 files), message_persistence** |

### Critical Gaps

1. **Rate limiting middleware untested** — security-critical token bucket logic has zero tests
2. **24 bot handler files** — only import-level tests exist; no behavior tests for /help, /settings, /mode, /claude, etc.
3. **Combined processor tests** use mock objects that don't match real `CombinedMessage` — tests don't verify actual behavior
4. **SRS algorithm (5 files)** — spaced repetition correctness unverified
5. **STT service** — voice transcription fallback logic (Groq -> OpenAI) untested

### What's Well-Tested

- Subprocess isolation: 100 tests in `test_claude_subprocess.py`
- Security: timing-safe comparison, admin auth, headers, error leakage, GDPR
- Plugin system: 32+32+90 tests across base, manager, models
- Message buffer: 78 tests covering timeout, flush, link-comment pairing

---

## 5. INSIGHTS FROM USAGE DATA

The report (412 messages, 77 sessions, Feb 5-14) reveals patterns that validate the audit findings:

### Friction -> Root Cause Mapping

| Usage Friction | Audit Finding |
|----------------|---------------|
| 32 "wrong approach" events | No verification hooks post-edit; silent error swallowing in handlers |
| 17 "buggy code" events | 24 handler files with 0 behavior tests; combined processor tests use mocks that don't match real objects |
| "Claude ignores existing restart scripts" | Configuration accessed 3 ways; no single source of truth for operational procedures |
| "Deploy fixes that don't work" | Health endpoint doesn't validate message processing flow; only checks DB connectivity |
| "Stale task monitoring alerts" | `_claude_mode_cache` private state shared across layers creates invisible dependencies |

### Session Pattern Insights

- **150 command failures** and **127 "other" errors** — correlates with silent error handling in handlers
- **81% satisfaction despite friction** — the architecture is fundamentally sound; issues are in the polish layer
- **51.5 msgs/day** across 77 sessions — this is a heavily-used personal tool; reliability matters more than features

---

## 6. PRIORITY ACTION PLAN

### P0 — Fix Now (Security)

1. `src/core/vector_db.py:74,78` — Replace f-string SQL with parameterized queries
2. `src/utils/encryption.py:41` — Use per-instance random salt from environment
3. `src/utils/encryption.py:56,73` — Fail hard in production if Fernet unavailable

### P1 — Fix This Sprint (Architecture + UX)

4. Add handler for unsupported message types (stickers, GIFs) — return friendly "unsupported" message
5. Add user notification for buffer overflow — don't silently drop messages
6. Eliminate 4 service-to-handler imports — create `MessageDispatcher` abstraction
7. Add `/todo` to help categories
8. Add rate limiting middleware tests

### P2 — Fix Next Sprint (Coherence + Testing)

9. Standardize config access to single pattern (`get_settings()`)
10. Resolve timeout default conflicts (yaml vs code)
11. Migrate all 25+ standalone service getters into `ServiceContainer`
12. Add handler behavior tests (24 files, ~200 tests needed)
13. Add auto-splitting for responses >4096 chars

### P3 — Backlog (Polish)

14. Standardize naming: `*_commands.py` vs `*_handlers.py`
15. Add settings change confirmation messages
16. Move dev dependencies to `requirements-dev.txt`
17. Document 2.5s buffer delay in help text
18. Add callback operation timeout with user feedback

---

*Report generated from 5 parallel analysis agents examining 150 source files, 130 test files, and 412 usage messages across 77 sessions.*
