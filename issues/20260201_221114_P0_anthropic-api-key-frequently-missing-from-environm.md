# ANTHROPIC_API_KEY frequently missing from environment

**Priority:** P0
**Created:** 2026-02-01T22:11:14.243252
**Source:** Automated architecture review

## Description
API key reported missing 12 times in 12h. Likely caused by env var race condition in concurrent Claude sessions.

## Acceptance Criteria
Session naming succeeds consistently when API key is configured

## Definition of Done
Zero 'API key not set' errors over 24h with normal usage.

## Testing Approach
Run concurrent Claude sessions; check session_naming logs.
