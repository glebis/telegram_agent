# One-Time Codebase Review Report

## Scope
- Repository: telegram_agent
- Areas: API, bot layer, services, core config, plugins, deployment/docs
- Exclusions: runtime behavior, external services, and production infrastructure were not exercised

## Method
- Static review of core execution paths
- Focus on security, correctness, reliability, configurability, portability
- No tests or live runs executed

## Architecture Summary
- FastAPI app receives Telegram webhooks and routes into bot handlers
- Message buffering combines rapid inputs before routing
- Services are registered via a DI container and invoked lazily
- Plugins are discovered from built-in and user plugin folders

## Findings

### Critical
1) Webhook admin endpoints are unauthenticated and accept `bot_token` as request input.
   - Impact: remote users can reconfigure webhooks or ngrok if endpoint is exposed.
   - References: `src/api/webhook.py`, `src/main.py`

### High
1) `/cleanup` endpoint is unauthenticated and can delete files on demand.
   - Impact: arbitrary cleanup can remove files in temp directories if exposed.
   - References: `src/main.py`

### Medium
1) Buffer timeout configuration is not applied.
   - Impact: config values for buffer timeout and limits are ignored; tuning is ineffective.
   - References: `src/core/config.py`, `src/core/services.py`, `src/services/message_buffer.py`

2) Webhook admin endpoints depend on a `bot_token` parameter but router is wired without DI.
   - Impact: endpoints return 422 unless callers pass a query param; also encourages token exposure.
   - References: `src/api/webhook.py`, `src/main.py`

### Low
1) Platform-specific binaries are committed without portability notes.
   - Impact: confusion or broken installs on non-macOS systems.
   - References: `extensions/vss0.dylib`, `extensions/vector0.dylib`

2) `.DS_Store` is committed.
   - Impact: repo hygiene only.
   - References: `scripts/.DS_Store`

## Existing Backlog (Provided)
- Rate limiting plugin for per-user quotas
- Configurable buffer timeout (currently hardcoded 2.5s)
- Bot init flow separating webhook setup from bot startup
- Scheduler/summarize/export plugins
- Alembic migrations
- Translate plugin, metrics dashboard, plugin hot-reload, PostgreSQL support

## Recommendations
- Lock down admin endpoints with a dedicated admin API key or reuse the messaging API key.
- Inject sensitive tokens from configuration only (no query params).
- Wire message buffer settings from config to runtime.
- Document portability constraints for native extensions.

## Quick Wins
- Protect `/cleanup` behind the same auth as admin endpoints.
- Remove `bot_token` from request surface and log output.
- Apply buffer config values in service registration.

## Testing Gaps
- No automated tests were reviewed or run for webhook admin endpoints.
- No runtime validation for configuration overrides.
