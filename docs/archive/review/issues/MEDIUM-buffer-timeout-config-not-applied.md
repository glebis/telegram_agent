# Medium: Buffer timeout config not applied

## Summary
`MessageBufferService` uses hardcoded defaults (2.5s, max messages, max wait), even though these values exist in settings. This makes config changes ineffective and complicates tuning.

## Affected
- `src/core/config.py`
- `src/core/services.py`
- `src/services/message_buffer.py`

## Recommended Fix
- Pass settings to `MessageBufferService` during registration in `setup_services()`.
- Ensure `buffer_timeout`, `max_buffer_messages`, and `max_buffer_wait` are used.

## Acceptance Criteria
- Buffer timeouts honor configuration values from settings.
- Changing `config/defaults.yaml` or env vars affects runtime behavior.
- Add a small unit test or manual verification note.
