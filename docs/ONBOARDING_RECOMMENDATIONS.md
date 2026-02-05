# Onboarding & Initial Setup Recommendations

Reference: lessons from the OpenClaw onboarding flow applied to `telegram_agent`, plus gaps found in our current setup wizard and env templates.

## Objectives
- Make initial setup one command, end-to-end and idempotent.
- Surface safety defaults (webhook secrets, rate limits, sender allowlists) early.
- Verify external prerequisites (binaries, tunnels, plugins) before first run.
- Keep users healthy post-install with a doctor command and clear next steps.

## Proposed Experience
- **Single entry point**: `python scripts/setup_wizard.py` aliased to `telegram-agent onboard`. Works headless-friendly (flags) and interactive.
- **Optional service install**: flag `--install-daemon` to register a user-level service (launchd/systemd) with matching `--uninstall-daemon`.
- **Post-check tool**: `python -m src.preflight.doctor` (or `telegram-agent doctor`) combining preflight, webhook status, plugin prereqs, and tunnel status.
- **Quick actions printed at the end**: start server, send self-test message, check webhook.

## Wizard Improvements
- **Env collection**: add prompts for `WEBHOOK_BASE_URL`, `WEBHOOK_USE_HTTPS`, `WEBHOOK_MAX_BODY_BYTES`, `WEBHOOK_RATE_LIMIT`, `WEBHOOK_RATE_WINDOW_SECONDS`, `API_MAX_BODY_BYTES`.
- **Tunnel choice**: prompt for `ngrok` (token, region, port) or “skip tunnel”; print resulting public URL if configured.
- **Plugin toggles**: list discovered plugins (PDF, Claude Code) with enable/disable and prerequisite checks:
  - PDF: verify `marker_single` on PATH; set vault path folders; let user disable if missing.
  - Claude Code: check CLI/subscription presence; collect `ANTHROPIC_API_KEY` optionally; set `CLAUDE_CODE_WORK_DIR`.
- **External keys**: collect and persist all used keys: `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `FIRECRAWL_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_SEARCH_CX`, `VOICE_SERVER_URL`.
- **Database DSN**: default to async driver `sqlite+aiosqlite:///./data/telegram_agent.db` and validate connectivity during wizard.
- **Safety defaults**: prompt for Telegram allowlists/pairing mode (optional), webhook secret length check, log level per environment.
- **Summary table**: show resolved values with masking; include tunnel URL, enabled plugins, service install status, and next commands.

## Env & Config Hygiene
- **Update `.env.example`** to include every consumed variable (keys above, webhook/tunnel settings, body/rate limits, sqlite extension paths).
- **Ensure consistency**: wizard defaults match `.env.example` and `config/defaults.yaml`.
- **Ship missing stub**: add `config/settings.yaml` (empty with comment) to satisfy preflight check or drop it from required list.

## Health & Audits
- **Doctor command** (`telegram-agent doctor`):
  - Runs preflight checks (Python, deps, ports, dirs, database).
  - Verifies webhook status via Telegram API and `WEBHOOK_BASE_URL`.
  - Checks plugin binaries (marker, Claude Code CLI) and warns if enabled but missing.
  - Flags missing/weak secrets, unset required envs, tunnel reachability.
- **Scheduled self-check**: optional cron/launchd entry to run doctor daily and log to `logs/doctor.log`.

## Security Defaults
- Enforce webhook secret presence; generate 64-hex default when absent.
- Highlight recommended production limits for body size/rate limit in wizard copy.
- Optional sender gating for Telegram: pairing code or allowlist prompt for group/DM usage.

## Remote Access & Tunnels
- Offer guided tunnel setup (ngrok/cloudflared) with region selection and autostart flag.
- Print active tunnel URL in wizard summary; store in `WEBHOOK_BASE_URL`.

## Plugins & Skills Model
- Treat plugins like OpenClaw skills:
  - Discovery list in wizard with enable/disable.
  - Per-plugin `requires` env vars validated before activation.
  - Sample configs written to `plugins/<name>/plugin.local.yaml` when enabled.
- Add a simple “registry” doc section explaining how to drop new plugins into `plugins/` and rerun onboard to pick them up.

## Workspace Bootstrap
- Seed a local workspace (e.g., `data/samples/`) with:
  - Example `modes.yaml` entry.
  - Sample plugin configs.
  - A test script to send a message to the bot for verification.

## Ops & Updates
- Add `scripts/update.py` (or README guidance) mirroring OpenClaw channeling: stable/beta/dev tags or git main, followed by `doctor`.
- Document daemon management commands (`start/stop/status/uninstall`) in README and wizard summary.

## UX Copy & Docs Alignment
- Keep README “quick start” in lockstep with wizard steps; avoid divergence.
- Add a short “What was set up” section after onboarding (webhook URL, plugins, tunnel).
- Provide troubleshooting links adjacent to each wizard step (e.g., tunnel failures, Telegram token validation).

## Immediate Next Steps (prioritized)
1) Update `.env.example` and wizard prompts to cover all env keys and defaults.  
2) Add plugin prerequisite checks and toggles to the wizard (PDF, Claude Code).  
3) Add webhook/tunnel questions and summary output (including generated secret).  
4) Introduce `telegram-agent doctor` CLI wrapping preflight + webhook + plugin checks.  
5) Add daemon install/uninstall flags and document them in README/dev-setup.  
6) Ship `config/settings.yaml` stub or remove it from preflight REQUIRED_CONFIGS.  
7) Add pairing/allowlist option for Telegram safety during onboarding.  
