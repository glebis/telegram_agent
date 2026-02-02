"""EnvManager - Idempotent .env file parsing, upsert, and writing.

Preserves comments, blank lines, and key ordering. Supports the upsert
pattern: update existing keys in-place, append new keys at the end.
Values containing special characters (#, spaces, quotes) are automatically
quoted when written.
"""

from pathlib import Path
from typing import Optional


# Characters that require quoting when writing
_NEEDS_QUOTING = set('#"\' ')


class EnvManager:
    """Manages a .env file with idempotent read/write operations."""

    def __init__(self, env_path: Path):
        self.path = Path(env_path)
        self.lines: list[str] = []
        self.values: dict[str, str] = {}
        self._key_line_map: dict[str, int] = {}

    def load(self) -> dict[str, str]:
        """Load and parse the .env file. Safe to call on nonexistent files."""
        self.lines = []
        self.values = {}
        self._key_line_map = {}

        if not self.path.exists():
            return self.values

        raw = self.path.read_text()
        if not raw.strip():
            return self.values

        for i, line in enumerate(raw.splitlines()):
            self.lines.append(line)
            key, value = self._parse_line(line)
            if key is not None:
                self.values[key] = value
                self._key_line_map[key] = i

        return self.values

    def get(self, key: str, default: str = "") -> str:
        """Get a value by key, with optional default."""
        return self.values.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self.values

    def set(self, key: str, value: str) -> None:
        """Set a key-value pair. Updates in-place if exists, appends if new.

        Values containing #, spaces, or quotes are automatically double-quoted.
        """
        self.values[key] = value
        serialized = self._serialize(key, value)
        if key in self._key_line_map:
            line_idx = self._key_line_map[key]
            self.lines[line_idx] = serialized
        else:
            self.lines.append(serialized)
            self._key_line_map[key] = len(self.lines) - 1

    def save(self) -> None:
        """Write the current state to the .env file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(self.lines)
        if not content.endswith("\n"):
            content += "\n"
        self.path.write_text(content)

    @staticmethod
    def _serialize(key: str, value: str) -> str:
        """Serialize a key-value pair, quoting the value if necessary."""
        if any(c in value for c in _NEEDS_QUOTING):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'{key}="{escaped}"'
        return f"{key}={value}"

    @staticmethod
    def _parse_line(line: str) -> tuple[Optional[str], str]:
        """Parse a single .env line into (key, value) or (None, '') for non-KV lines."""
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None, ""

        if "=" not in stripped:
            return None, ""

        key, _, raw_value = stripped.partition("=")
        key = key.strip()
        if not key:
            return None, ""

        value = raw_value.strip()

        # Strip surrounding quotes (and unescape)
        if len(value) >= 2:
            if (value[0] == '"' and value[-1] == '"') or (
                value[0] == "'" and value[-1] == "'"
            ):
                inner = value[1:-1]
                # Unescape only for double-quoted values
                if value[0] == '"':
                    inner = inner.replace('\\"', '"').replace("\\\\", "\\")
                return key, inner

        # Strip inline comments (only for unquoted values)
        # Per dotenv spec, # must be preceded by whitespace to be a comment
        if " #" in value:
            value = value[: value.index(" #")].rstrip()

        return key, value
