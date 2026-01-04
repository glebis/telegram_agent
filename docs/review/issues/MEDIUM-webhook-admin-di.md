# Medium: Webhook admin endpoints use bot_token parameter

## Summary
Webhook admin endpoints expect `bot_token` as a function parameter but the router is included without DI wiring. In practice this leads to 422 errors unless callers pass a query parameter, and it couples auth to an insecure mechanism.

## Affected
- `src/api/webhook.py`
- `src/main.py`

## Recommended Fix
- Provide a dependency that injects `bot_token` from settings, not from request input.
- Ensure the router is included with the dependency at app wiring time.

## Acceptance Criteria
- Webhook admin endpoints work without requiring `bot_token` in query or body.
- `bot_token` is only read from server configuration.
- Document the admin auth mechanism in `docs/DEPLOYMENT.md` or similar.
