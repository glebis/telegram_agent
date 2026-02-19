"""
Tests that callback_handlers.py uses sanitize_error() instead of str(e).

Verifies the callback_handlers module no longer exposes raw exception
text in user-facing messages.
"""

pass


class TestCallbackHandlersNoStrE:
    """Verify callback_handlers.py does not pass str(e) to user messages."""

    def _read_source(self) -> str:
        """Read the callback_handlers.py source."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "bot"
            / "callback_handlers.py"
        )
        return src.read_text()

    def test_no_str_e_in_user_facing_calls(self):
        """User-facing calls must not contain str(e) anywhere nearby.

        Checks both same-line and multi-line call patterns where str(e)
        appears as an argument to reply_text / send_message / edit_text.
        """
        source = self._read_source()

        # Single-line check
        user_facing_str_e = []
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("logger.") or stripped.startswith("#"):
                continue
            if "str(e)" in line and any(
                kw in line for kw in ("reply_text", "send_message", "edit_text")
            ):
                user_facing_str_e.append((i, stripped))

        # Multi-line check: find str(e) used as argument within 5 lines
        # of a user-facing call (covers split-line function calls)
        lines = source.splitlines()
        call_keywords = ("reply_text", "send_message_sync", "edit_text", "send_message")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("logger.") or stripped.startswith("#"):
                continue
            if "str(e)" not in stripped:
                continue
            # Look back up to 5 lines for a user-facing call opener
            for back in range(1, 6):
                if i - back < 0:
                    break
                prev = lines[i - back].strip()
                if prev.startswith("logger.") or prev.startswith("#"):
                    continue
                if any(kw in prev for kw in call_keywords):
                    entry = (i + 1, stripped)
                    if entry not in user_facing_str_e:
                        user_facing_str_e.append(entry)
                    break

        assert user_facing_str_e == [], (
            f"callback_handlers.py still has str(e) in user-facing messages "
            f"at lines: {[ln for ln, _ in user_facing_str_e]}"
        )

    def test_no_raw_error_msg_in_user_messages(self):
        """User messages must not contain {error_msg} pattern (from str(e))."""
        source = self._read_source()
        user_facing_error_msg = []
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("logger."):
                continue
            if stripped.startswith("#"):
                continue
            # Check for f-string patterns with error_msg in user-facing calls
            if ("reply_text" in line or "edit_text" in line) and "error_msg" in line:
                # Allow if it's just the DEBUG_MODE block
                pass  # We check below more specifically
            if (
                "reply_text" in line or "send_message_sync" in line
            ) and "{error_msg}" in line:
                user_facing_error_msg.append((i, stripped))

        assert user_facing_error_msg == [], (
            f"callback_handlers.py has {{error_msg}} in user messages "
            f"at lines: {[ln for ln, _ in user_facing_error_msg]}"
        )

    def test_imports_sanitize_error(self):
        """callback_handlers.py should import sanitize_error."""
        source = self._read_source()
        assert (
            "sanitize_error" in source
        ), "callback_handlers.py does not import sanitize_error"

    def test_debug_mode_still_allowed(self):
        """DEBUG_MODE blocks may show details -- that is intentional."""
        source = self._read_source()
        # The DEBUG_MODE block in handle_reanalyze_callback is OK
        # Just verify it exists and is guarded
        assert "DEBUG_MODE" in source, "DEBUG_MODE guard should still exist"
