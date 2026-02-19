# Critical: Lock down webhook admin endpoints

## Summary
Webhook management endpoints are effectively unauthenticated and take `bot_token` as a request parameter. This allows unauthorized users to update/delete webhooks or start/stop ngrok if the service is reachable.

## Affected
- `src/api/webhook.py`
- `src/main.py`

## Risk
High impact: attackers could hijack webhook routing, disable bot updates, or expose internal ngrok tunnel information. Token exposure via query params/logs is also a risk.

## Recommended Fix
- Remove `bot_token` from request params; inject it from settings or DI.
- Require auth for all `/admin/webhook/*` endpoints (reuse messaging API key or add a dedicated admin key).
- Avoid logging sensitive tokens/URLs.

## Acceptance Criteria
- All webhook admin endpoints require authentication.
- `bot_token` is never accepted via query parameters.
- Requests without auth are rejected with 401.
- Unit/integration test added or a manual test plan documented.
