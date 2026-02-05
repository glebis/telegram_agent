"""Tests for EnvManager - .env file parsing, upsert, and writing."""


class TestEnvManagerParse:
    """Tests for parsing .env files."""

    def test_parse_empty_file(self, tmp_path):
        """Empty file returns empty dict."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values == {}

    def test_parse_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict without error."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values == {}
        assert mgr.lines == []

    def test_parse_with_values(self, tmp_path):
        """Parses KEY=value pairs correctly."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\nBAZ=qux\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values == {"FOO": "bar", "BAZ": "qux"}

    def test_parse_preserves_comments(self, tmp_path):
        """Comments and blank lines are preserved in raw lines."""
        content = "# This is a comment\nFOO=bar\n\n# Another comment\nBAZ=qux\n"
        env_file = tmp_path / ".env.local"
        env_file.write_text(content)

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values == {"FOO": "bar", "BAZ": "qux"}
        assert len(mgr.lines) == 5

    def test_parse_quoted_values(self, tmp_path):
        """Handles double-quoted and single-quoted values."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=\"hello world\"\nBAR='single quoted'\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values["FOO"] == "hello world"
        assert mgr.values["BAR"] == "single quoted"

    def test_parse_empty_value(self, tmp_path):
        """KEY= with no value parses as empty string."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=\nBAR=value\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values["FOO"] == ""
        assert mgr.values["BAR"] == "value"

    def test_parse_value_with_equals(self, tmp_path):
        """Values containing = are parsed correctly (split on first = only)."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("DATABASE_URL=sqlite:///data/test.db\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values["DATABASE_URL"] == "sqlite:///data/test.db"

    def test_parse_inline_comment(self, tmp_path):
        """Inline comments after values are stripped."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar # this is a comment\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.values["FOO"] == "bar"


class TestEnvManagerUpsert:
    """Tests for upserting values."""

    def test_upsert_new_key(self, tmp_path):
        """Adding a new key appends it."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("NEW_KEY", "new_value")
        assert mgr.values["NEW_KEY"] == "new_value"
        assert mgr.values["FOO"] == "bar"

    def test_upsert_existing_key(self, tmp_path):
        """Updating existing key changes value in-place."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=old\nBAR=keep\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("FOO", "new")
        assert mgr.values["FOO"] == "new"
        assert mgr.values["BAR"] == "keep"

    def test_upsert_preserves_order(self, tmp_path):
        """Existing keys stay in their original position after update."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FIRST=1\nSECOND=2\nTHIRD=3\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("SECOND", "updated")
        mgr.save()

        saved = env_file.read_text().splitlines()
        assert saved[0] == "FIRST=1"
        assert saved[1] == "SECOND=updated"
        assert saved[2] == "THIRD=3"

    def test_upsert_preserves_comments(self, tmp_path):
        """Comments are not destroyed by upsert."""
        content = "# Core config\nFOO=bar\n\n# Optional\nBAZ=qux\n"
        env_file = tmp_path / ".env.local"
        env_file.write_text(content)

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("FOO", "updated")
        mgr.save()

        saved = env_file.read_text()
        assert "# Core config" in saved
        assert "# Optional" in saved
        assert "FOO=updated" in saved

    def test_set_empty_value(self, tmp_path):
        """Setting empty string value is supported."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("FOO", "")
        assert mgr.values["FOO"] == ""


class TestEnvManagerSave:
    """Tests for writing .env files."""

    def test_write_creates_file(self, tmp_path):
        """Save creates file if it doesn't exist."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("FOO", "bar")
        mgr.save()

        assert env_file.exists()
        assert "FOO=bar" in env_file.read_text()

    def test_write_roundtrip(self, tmp_path):
        """parse -> upsert -> write -> parse yields consistent result."""
        env_file = tmp_path / ".env.local"
        original = "# Header\nFOO=bar\nBAZ=qux\n"
        env_file.write_text(original)

        from scripts.setup_wizard.env_manager import EnvManager

        mgr1 = EnvManager(env_file)
        mgr1.load()
        mgr1.set("FOO", "updated")
        mgr1.set("NEW", "added")
        mgr1.save()

        mgr2 = EnvManager(env_file)
        mgr2.load()
        assert mgr2.values["FOO"] == "updated"
        assert mgr2.values["BAZ"] == "qux"
        assert mgr2.values["NEW"] == "added"

    def test_save_trailing_newline(self, tmp_path):
        """Saved file ends with a newline."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("FOO", "bar")
        mgr.save()

        assert env_file.read_text().endswith("\n")


class TestEnvManagerSpecialValues:
    """Tests for values with special characters (Codex review fix)."""

    def test_roundtrip_value_with_hash(self, tmp_path):
        """Values containing # survive set -> save -> load roundtrip."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("PASSWORD", "abc #123")
        mgr.save()

        mgr2 = EnvManager(env_file)
        mgr2.load()
        assert mgr2.values["PASSWORD"] == "abc #123"

    def test_roundtrip_value_with_spaces(self, tmp_path):
        """Values with leading/trailing spaces are preserved via quoting."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("MSG", "hello world")
        mgr.save()

        mgr2 = EnvManager(env_file)
        mgr2.load()
        assert mgr2.values["MSG"] == "hello world"

    def test_roundtrip_value_with_quotes(self, tmp_path):
        """Values with embedded quotes are properly escaped."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("JSON", '{"key": "value"}')
        mgr.save()

        mgr2 = EnvManager(env_file)
        mgr2.load()
        assert mgr2.values["JSON"] == '{"key": "value"}'

    def test_roundtrip_simple_value_unquoted(self, tmp_path):
        """Simple values without special chars are stored without quotes."""
        env_file = tmp_path / ".env.local"

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        mgr.set("TOKEN", "sk-abc123def456")
        mgr.save()

        raw = env_file.read_text()
        assert "TOKEN=sk-abc123def456" in raw  # no quotes needed


class TestEnvManagerHelpers:
    """Tests for helper methods."""

    def test_has_key(self, tmp_path):
        """has() returns True for existing keys, False otherwise."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.has("FOO") is True
        assert mgr.has("MISSING") is False

    def test_get_with_default(self, tmp_path):
        """get() returns value or default."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\n")

        from scripts.setup_wizard.env_manager import EnvManager

        mgr = EnvManager(env_file)
        mgr.load()
        assert mgr.get("FOO") == "bar"
        assert mgr.get("MISSING", "fallback") == "fallback"
        assert mgr.get("MISSING") == ""
