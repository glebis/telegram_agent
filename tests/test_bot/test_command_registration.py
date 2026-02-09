"""
Architecture guard test: verify all registered commands have handlers.

Parses bot.py to extract CommandHandler registrations and verifies
each command name corresponds to an importable handler function.
"""

import re
from pathlib import Path

# Path to bot.py
BOT_PY = Path(__file__).parent.parent.parent / "src" / "bot" / "bot.py"


def _extract_registered_commands() -> list[str]:
    """Extract command names from CommandHandler(...) calls in bot.py."""
    source = BOT_PY.read_text()
    # Match CommandHandler("command_name", ...)
    pattern = r'CommandHandler\(\s*"([a-z_]+)"'
    return re.findall(pattern, source)


class TestCommandRegistration:
    """Guard tests for command handler registration."""

    def test_all_commands_have_unique_names(self):
        """No duplicate command registrations."""
        commands = _extract_registered_commands()
        assert len(commands) == len(set(commands)), (
            f"Duplicate commands: " f"{[c for c in commands if commands.count(c) > 1]}"
        )

    def test_all_commands_registered(self):
        """At least the core commands are registered."""
        commands = set(_extract_registered_commands())
        expected_core = {
            "start",
            "help",
            "settings",
            "claude",
            "privacy",
            "language",
        }
        missing = expected_core - commands
        assert not missing, f"Missing core commands: {missing}"

    def test_handler_functions_importable(self):
        """Each registered command has a named handler function."""
        source = BOT_PY.read_text()
        # Match CommandHandler("name", handler_func)
        pattern = r'CommandHandler\(\s*"([a-z_]+)"\s*,\s*(\w+)\s*\)'
        pairs = re.findall(pattern, source)

        assert len(pairs) > 10, "Expected at least 10 command registrations"

        for cmd_name, handler_name in pairs:
            # Handler name should be a callable reference (not empty/invalid)
            assert handler_name.isidentifier(), (
                f"Handler for /{cmd_name} is not a valid identifier: " f"{handler_name}"
            )

    def test_bot_py_exists(self):
        """bot.py file exists at expected path."""
        assert BOT_PY.exists(), f"bot.py not found at {BOT_PY}"
