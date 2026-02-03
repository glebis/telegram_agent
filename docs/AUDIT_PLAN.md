# Security, Privacy & Accessibility Audit Plan

Scope: telegram_agent codebase (FastAPI + python-telegram-bot + plugins), infra scripts, configs, and tests.

## Objectives
- Security: identify auth/transport/storage weaknesses; key/secret handling; supply-chain risks; subprocess safety; Claude Code tool access control.
- Privacy: validate data minimization, retention, redaction, and user-consent flows (Telegram/Obsidian/Groq/OpenAI).
- Accessibility: ensure user-facing text/buttons comply with basic a11y heuristics (label clarity, button count/spacing for custom keyboards).

## Deliverables
1) Findings report (severity-tagged) with code refs and repro steps.
2) Fix plan with owners.
3) Evidence pack: config snapshots, test logs, SBOM, dependency risk summary.

## Methodology & Tasks

### Security
- Code review: threat-model pass over `src/api`, `src/bot`, `src/services`, `src/utils/logging.py`, `src/main.py`, `config/*.yaml`.
- Config/secret handling: check `.env*`, `config/`, launchd scripts; verify secrets never logged; env validation.
- AuthZ/AuthN: admin/webhook endpoints (`src/api/webhook.py`, `src/api/messaging.py`), bot command guards, rate limits, webhook secret enforcement.
- Transport: webhook TLS assumptions (ngrok), HSTS middleware, secret token validation.
- Claude Code execution safety: tool access restrictions (`config/defaults.yaml` → `claude_allowed_tools`), CWD whitelist enforcement, prompt injection surface, output sanitization.
- Subprocess/async safety: `src/services/claude_subprocess.py`, `src/utils/subprocess_helper.py`, message handlers' subprocess calls, message buffer combination attack surface.
- Dependency & supply chain: lock/pin review (`requirements*.txt`), transitive CVE scan, sqlite-vss dylib integrity (SHA-256 hash manifest, upstream provenance verification, load-time check).

### Data Hygiene
- Data flow & storage: SQLite schemas (`src/models/*`), what's stored, for how long, is it cleaned up.
- Retention enforcement: verify `data_retention_service.py` covers all tables and file types; check image deletion attribute alignment with model columns.
- Temp file lifecycle: catalog all temp file creation points, verify cleanup coverage, confirm `tempfile` module usage.
- Logging/observability: ensure redaction (`src/utils/logging.py`), PII scrubbing, log rotation, no path/secret leakage.
- Privacy controls: data minimization in transcripts/images, deletion paths (`/deletedata`), Obsidian path exposure in Claude responses.

### Accessibility
- Keyboard layouts/text (`src/services/keyboard_service.py`, handlers): label clarity, state feedback, button count/spacing.

### Testing
- Targeted pytest for webhook/messaging hardening; add regression tests where missing.
- Reply context cache behavior in group chat scenarios.

## Tools & Evidence
- Static: `bandit`, `pip-audit`, `safety`, SBOM via `pip-audit -f cyclonedx`.
- Dynamic: `pytest` suites (security-focused cases in `tests/test_api`), manual webhook secret validation, rate-limit probes.
- Secrets: `detect-secrets` or `git secrets` scan.
- Logs: review `logs/` rotation configs; ensure redaction processor exercised.

## Success Criteria
- No high/critical unmitigated findings (accepted risks documented with compensating controls).
- Secrets never logged; webhook/admin endpoints gated; body/rate limits enforced.
- Claude Code tool access configurable at install time; default toolset is least-privilege for the use case.
- Documented retention/deletion path covering all data types and file locations.
- Accessible keyboards: clear labels, minimal rows, consistent affordances.
- Reproducible test commands in report; SBOM and scan outputs archived.
