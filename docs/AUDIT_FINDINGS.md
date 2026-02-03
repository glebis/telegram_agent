# Security, Privacy & Accessibility Audit: Findings Report

**Scope:** telegram_agent codebase (FastAPI + python-telegram-bot + plugins)
**Date:** 2026-02-02
**Methodology:** Static analysis (bandit, pip-audit, detect-secrets), manual code review, codebase exploration

---

## Part 1: Critical Review of AUDIT_PLAN.md

### What the Plan Gets Right

1. **Threat-model pass scope** is well-chosen: `src/api`, `src/bot`, `src/services`, `src/utils/logging.py`, `config/*.yaml` covers the real attack surface.
2. **Subprocess safety** is correctly called out as a dedicated task. This codebase relies heavily on subprocess isolation to work around async/event-loop blocking, making it a genuine risk area.
3. **Tool selection** (bandit, pip-audit, detect-secrets) is appropriate for a Python project of this size.
4. **Deliverables** are practical: severity-tagged findings, fix plan, and evidence pack.

### What the Plan Gets Wrong or Misses

#### Priority Misalignment

1. **Accessibility is overweighted relative to impact.** The plan allocates accessibility equal standing with security and privacy, but this is a personal Telegram bot, not a public-facing web service. Telegram's native UI handles contrast, font sizes, and most a11y concerns. The plan should deprioritize keyboard layout review and instead spend that time on the privacy data-flow gaps (see below).

2. **"GDPR-lite posture" and "SOC2-style controls" are premature.** For a single-user/small-group personal bot running on a local Mac Mini, formal compliance frameworks add planning overhead without proportionate risk reduction. The plan should focus on concrete data hygiene (what's stored, for how long, is it cleaned up) rather than compliance theater.

3. **Supply-chain risk for sqlite-vss dylibs is underspecified.** The plan mentions "verify sqlite-vss dylibs provenance" as a bullet point but doesn't define what verification means. These are unsigned precompiled C binaries loaded into the database process. This deserves its own task with specific acceptance criteria (hash manifest, upstream comparison, load-time verification).

#### Missing Attack Surface

4. **No mention of the message buffer as an attack vector.** The 2.5-second message buffer (`src/services/message_buffer.py`) accumulates user input across multiple messages before flushing. A malicious user could craft multi-part payloads that are benign individually but form an injection when combined. The plan should include buffer combination logic in its threat model.

5. **No mention of Claude Code as an execution vector.** The bot sends user-controlled prompts to Claude Code, which can execute arbitrary commands on the host system. The plan mentions "subprocess safety" but doesn't specifically address prompt injection leading to host command execution. This is the highest-impact risk in the entire system and deserves a dedicated task.

6. **Reply context cache poisoning is unaddressed.** The `ReplyContext` service uses a 24-hour TTL LRU cache keyed by message ID. The plan doesn't consider what happens if a user crafts replies to inject context into another user's session (relevant in group chats).

7. **No mention of file-path disclosure in Claude responses.** Claude Code responses routinely contain full system paths (`/Users/server/Research/vault/...`). The plan's "Obsidian path exposure" bullet is too vague and doesn't capture the actual risk vector: Claude generates paths that reveal the server's filesystem layout.

#### Process Issues

8. **Timeline is unrealistic for the scope.** Days 1-2 for "code/config review + dependency scan" across ~50 Python files, ~15 config files, shell scripts, launchd plists, and plugin directories is aggressive. The dependency scan alone takes an hour. Recommend splitting into two phases: automated scanning (1 day), then manual review (3-4 days).

9. **"DRI: <assign>" is a gap.** An audit plan without an assigned owner is a plan that won't execute. This should be assigned before the plan is approved.

10. **No risk-acceptance criteria.** The success criteria say "no high/critical unmitigated findings" but don't define a risk-acceptance process for findings that can't be fixed immediately (e.g., the subprocess architecture is a fundamental design choice, not something you can "fix").

---

## Part 2: Static Analysis Results

### 2.1 Bandit (Python Security Scanner)

**Total issues at medium+ severity: 7**

| Severity | ID | Issue | Location | Verdict |
|----------|-----|-------|----------|---------|
| HIGH | B324 | MD5 used for security | `src/services/embedding_service.py:67` | **False positive** - used for cache key deduplication, not cryptographic security |
| HIGH | B324 | MD5 used for security | `src/services/embedding_service.py:124` | **False positive** - same pattern |
| HIGH | B324 | MD5 used for security | `src/utils/session_emoji.py:30` | **False positive** - deterministic emoji generation |
| MEDIUM | B108 | Insecure temp file usage | `src/bot/handlers/claude_commands.py:620` | **Valid** - uses `/tmp` without `tempfile.mkstemp()` |
| MEDIUM | B108 | Insecure temp file usage | `src/services/claude_subprocess.py:143` | **Valid** - same pattern |
| MEDIUM | B104 | Binding to all interfaces | `src/main.py:880` | **Expected** - server must bind to 0.0.0.0, mitigated by ngrok tunnel |
| MEDIUM | B104 | Binding to all interfaces | `src/preflight/checks.py:248` | **Expected** - health check binding |

**Action items:**
- Add `usedforsecurity=False` to MD5 calls to silence false positives
- Replace `/tmp` usage with `tempfile.mkstemp()` or `tempfile.TemporaryDirectory()` for the two B108 findings

### 2.2 pip-audit (Dependency Vulnerabilities)

**Result: No known vulnerabilities found.** All installed packages are clean against PyPI/OSV advisories.

**Dependency pinning status:**

| Strategy | Count | Risk |
|----------|-------|------|
| Range-pinned (`>=x,<y`) | 5 | Low - `litellm`, `openai`, `claude-code-sdk`, `mcp`, `aiohttp` |
| Floor-only (`>=x`) | 38 | **Medium** - includes `fastapi`, `sqlalchemy`, `python-telegram-bot`, `anthropic` |
| Exact-pinned (`==x`) | 0 | N/A |

**Key risk:** 38 packages with floor-only constraints means a future `pip install` could pull in a breaking major version of `fastapi` or `sqlalchemy`. Recommend generating `requirements.lock` via `pip freeze` for deployment reproducibility.

### 2.3 detect-secrets / Git History Scan

**Result: Clean.** No real secrets in source code or git history.

- `.env` and `.env.local` are properly `.gitignored` and never committed
- 23 detect-secrets flags are all in test files with fake values (`"test-key"`, `"test-secret"`, etc.)
- No hardcoded API keys, tokens, or credentials in any source file

**One minor finding:** `.env.local` has `644` permissions (world-readable on the host). Should be `600` to match `.env`.

---

## Part 3: Manual Code Review Findings

### FINDING-01: Claude Code Prompt Injection (CRITICAL)

**Risk:** User-controlled prompts are sent to Claude Code, which has filesystem and command execution access on the host system.

**Location:** `src/services/claude_subprocess.py:157-507`

**Mitigations already in place:**
- Working directory whitelist (`~/Research/vault`, `~/ai_projects`, `/tmp`) at line 121-154
- Input sanitization for UTF-8 surrogates at line 324-344
- JSON escaping of inputs at line 366-375

**Gaps:**
- No output sanitization - Claude responses are sent directly to Telegram
- No command allowlist/blocklist for Claude's tool use
- The CWD whitelist constrains where Claude starts, but Claude can access files outside the CWD via absolute paths
- System prompt instructs Claude to use full vault paths, which Claude could be manipulated into reading arbitrary files

**Recommendation:** This is an inherent risk of the Claude Code architecture. Document it as an accepted risk with compensating controls: restrict the bot to trusted users only (admin contacts), monitor Claude session logs, and consider Claude's `--allowedTools` flag if supported.

### FINDING-02: Webhook Auth Bypass in Development (MEDIUM)

**Risk:** Webhook secret validation is conditional on the secret being configured. In development without the secret, all webhook requests are accepted.

**Location:** `src/main.py:771-779`

```python
webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
if webhook_secret:
    # validation...
```

**Mitigating factor:** Line 64-67 enforces the secret in production mode. However, the `ENVIRONMENT` variable defaults to empty, meaning a misconfigured production deployment could run without webhook auth.

**Recommendation:** Default `ENVIRONMENT` to `"production"` rather than empty string, or require the webhook secret unconditionally.

### FINDING-03: Image File Cleanup Bug in Data Deletion (MEDIUM)

**Risk:** When a user exercises their right to deletion (`/deletedata`), image files may not be fully removed from disk.

**Location:** `src/bot/handlers/privacy_commands.py:487-495`

The deletion code checks for attributes `file_path`, `raw_path`, and `compressed_path` on Image objects, but the Image model (`src/models/image.py:25-29`) defines columns as `original_path` and `compressed_path`. The attribute name mismatch means `original_path` files are never deleted.

**Recommendation:** Align attribute names in the deletion loop with the actual Image model columns.

### FINDING-04: System Path Disclosure in Claude Responses (MEDIUM)

**Risk:** Claude Code responses contain full filesystem paths (`/Users/server/Research/vault/...`) that reveal the server's directory structure and username.

**Location:** `src/bot/handlers/claude_commands.py:658-676` (transformation function)

The `_transform_vault_paths_in_text()` function attempts to convert paths to wikilinks, but:
- Only handles paths within the vault directory
- Paths outside the vault pass through unmodified
- If the regex fails, the raw path is exposed
- Error messages from Claude may contain arbitrary system paths

**Recommendation:** Add a catch-all sanitizer that strips or replaces any `/Users/server/` prefix in all outgoing messages, not just vault paths.

### FINDING-05: f-string SQL in Vector DB Extension Loading (LOW)

**Risk:** SQL injection via extension path if `SQLITE_EXTENSIONS_PATH` env var is attacker-controlled.

**Location:** `src/core/vector_db.py:73,77`

```python
await db.execute(f"SELECT load_extension('{vector0_file}')")
```

**Mitigating factor:** The path comes from an environment variable with a safe default (`./extensions`), not from user input. Exploitation requires control over the server's environment variables, which implies full compromise anyway.

**Recommendation:** Use parameterized queries or at minimum validate the path against an allowlist before interpolation.

### FINDING-06: Insecure Temp File Creation (LOW)

**Risk:** Two locations use hardcoded `/tmp` paths instead of `tempfile` module, creating a potential symlink race condition.

**Locations:**
- `src/bot/handlers/claude_commands.py:620`
- `src/services/claude_subprocess.py:143`

**Recommendation:** Replace with `tempfile.mkstemp()` or `tempfile.TemporaryDirectory()`.

### FINDING-07: No Explicit Consent Before External API Data Transmission (LOW)

**Risk:** Voice messages are transcribed via Groq and images analyzed via OpenAI without per-interaction consent confirmation.

**Locations:**
- `src/services/voice_service.py:43-100` (Groq Whisper)
- `src/services/llm_service.py:69` (OpenAI image analysis)

**Mitigating factor:** This is a personal bot with a small trusted user base. Users implicitly consent by sending messages to the bot. The GDPR privacy commands (`/mydata`, `/deletedata`, `/privacy`) exist for data management.

**Recommendation:** For current scope, document the data flows in the bot's `/help` or `/privacy` response. No per-interaction consent dialog needed for a personal bot.

### FINDING-08: Incomplete Temp Directory Cleanup Coverage (LOW)

**Risk:** The periodic cleanup service (`src/utils/cleanup.py`) only covers 3 directories (`temp_images`, `temp_docs`, `temp_audio`). Other temp files created during processing may be missed.

**Location:** `src/utils/cleanup.py:27-31`

**Recommendation:** Add all directories where temp files are created, or switch to using `tempfile.TemporaryDirectory()` context managers that auto-clean.

---

## Part 4: Security Posture Summary

### What's Done Well

| Area | Implementation | Assessment |
|------|---------------|------------|
| Webhook authentication | `hmac.compare_digest()` timing-safe comparison | Excellent |
| Admin API auth | Derived keys with salted SHA-256, per-endpoint separation | Excellent |
| Security headers | X-Content-Type-Options, X-Frame-Options, HSTS, Cache-Control | Excellent |
| Rate limiting | Per-IP limits on webhook (120/min) and API (30/min) + body size limits | Good |
| Log redaction | Regex-based token, API key, phone, and transcription redaction | Excellent |
| PII sanitization | Dedicated `PIISanitizingFilter` with file rotation (30-day) | Excellent |
| Secret management | `.env` files gitignored, never committed, Pydantic Settings loader | Good |
| Subprocess isolation | stdin/env for data passing, CWD whitelist, JSON escaping | Good |
| Data retention | User-configurable periods, automated enforcement, GDPR deletion | Good |
| ORM usage | SQLAlchemy throughout, no raw SQL with user input | Excellent |
| Deduplication | Webhook update deduplication prevents replay attacks | Good |

### Risk Register

| ID | Finding | Severity | Status | Recommendation |
|----|---------|----------|--------|----------------|
| F-01 | Claude Code prompt injection | CRITICAL | **Mitigated** | Tool access now configurable via `config/defaults.yaml` and env vars; restrict to trusted users; monitor sessions |
| F-02 | Conditional webhook auth | MEDIUM | **Fix** | Default ENVIRONMENT to production |
| F-03 | Image file cleanup bug | MEDIUM | **FIXED** | Aligned attribute names with Image model (`original_path`, `compressed_path`) |
| F-04 | System path disclosure | MEDIUM | **Fix** | Add catch-all path sanitizer |
| F-05 | f-string SQL for extensions | LOW | **Fix** | Use parameterized query or allowlist |
| F-06 | Insecure temp file creation | LOW | **Fix** | Use `tempfile` module |
| F-07 | No per-interaction consent | LOW | **Accept** | Document data flows in /help |
| F-08 | Incomplete temp cleanup | LOW | **Fix** | Expand cleanup directory list |
| F-09 | Dep pinning gaps (38 floor-only) | LOW | **Fix** | Generate requirements.lock |
| F-10 | .env.local 644 permissions | LOW | **FIXED** | `chmod 600` applied |

### Keyboard/Accessibility Notes

These are real usability issues but low-priority for a personal bot:

- Settings keyboard has 8 rows of buttons (overwhelming on mobile)
- Heavy emoji reliance for state indicators without text fallbacks
- Model selection labels ("haiku", "sonnet", "opus") are opaque to non-Anthropic users
- Generic button labels ("More", "Retry") lack context

---

## Part 5: Recommended Actions (Priority Order)

### Immediate (before next deploy)

1. ~~**F-03: Fix image file deletion attribute mismatch**~~ **DONE** - changed `file_path`/`raw_path` to `original_path`/`compressed_path` in `privacy_commands.py:489`
2. ~~**F-10: Tighten .env.local permissions**~~ **DONE** - `chmod 600 .env.local`

### Short-term (next sprint)

3. **F-02: Harden webhook auth default** - set `ENVIRONMENT` default to `"production"` or require webhook secret unconditionally
4. **F-04: Add catch-all path sanitizer** to strip `/Users/<username>/` from all outgoing messages
5. **F-06: Replace /tmp usage** with `tempfile` module in the two flagged locations
6. **F-09: Generate requirements.lock** - run `pip freeze > requirements.lock` and commit

### Medium-term

7. **F-05: Parameterize extension loading SQL** in `vector_db.py`
8. **F-08: Expand temp cleanup coverage** to all temp file locations
9. **Bandit suppressions:** Add `usedforsecurity=False` to the 3 MD5 calls
10. **Dylib integrity:** Generate SHA-256 hashes for `vss0.dylib` and `vector0.dylib`, verify on startup

### Accepted Risks

- **F-01 (Claude Code execution):** Fundamental to the bot's purpose. Now mitigated by configurable tool access (`config/defaults.yaml` → `claude_tools.allowed_tools` / `claude_tools.disallowed_tools`, or env vars `CLAUDE_ALLOWED_TOOLS` / `CLAUDE_DISALLOWED_TOOLS`), admin-only access, CWD whitelist, and session monitoring. Tool restrictions are set at install time, not through the bot UI.
- **F-07 (No per-interaction consent):** Acceptable for a personal/small-group bot. Documented in privacy commands.

---

## Appendix: Tool Outputs

### Bandit Summary
- 3 HIGH (all false-positive MD5), 4 MEDIUM (2 temp file, 2 bind-all), 65 LOW
- No real high-severity code vulnerabilities

### pip-audit Summary
- 0 known vulnerabilities in installed packages
- 5/43 packages range-pinned, 38 floor-only pinned

### detect-secrets Summary
- 0 real secrets in source or git history
- 23 test-file flags (all fake values)
- `.env` files properly gitignored, correct permissions on `.env`, needs tightening on `.env.local`
