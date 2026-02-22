"""
Tests for Codex plugin.

Tests cover:
- Plugin metadata and capabilities
- Plugin loading and activation
- Command handler registration
- Flag parsing (--model, --effort, --sandbox, -C)
- Subprocess execution (mocked)
- Error handling (timeout, binary not found, execution failure)
- Output formatting
- Help command
- Resume command
"""

import subprocess
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.plugins.base import PluginCapabilities, PluginMetadata


class TestCodexPluginMetadata:
    """Tests for Codex plugin metadata."""

    @pytest.fixture
    def plugin(self, tmp_path):
        """Create a Codex plugin instance."""
        # Import here to avoid issues if plugin not loaded
        from plugins.codex.plugin import CodexPlugin

        return CodexPlugin(tmp_path)

    def test_metadata_properties(self, plugin):
        """Test plugin metadata has correct properties."""
        meta = plugin.metadata

        assert isinstance(meta, PluginMetadata)
        assert meta.name == "codex"
        assert meta.version == "1.0.0"
        assert "Codex" in meta.description
        assert meta.author == "Verity"
        assert meta.requires == []
        assert meta.dependencies == []
        assert meta.priority == 70
        assert meta.enabled_by_default is True

    def test_capabilities(self, plugin):
        """Test plugin capabilities."""
        caps = plugin.capabilities

        assert isinstance(caps, PluginCapabilities)
        assert "codex" in caps.services
        assert "/codex" in caps.commands
        assert "/codex:resume" in caps.commands
        assert "/codex:help" in caps.commands
        assert "codex:*" in caps.callbacks
        assert caps.api_routes is False
        assert caps.message_handler is False


class TestCodexPluginLoading:
    """Tests for plugin loading and activation."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        return CodexPlugin(tmp_path)

    @pytest.fixture
    def mock_config(self):
        """Mock plugin config."""
        return {
            "work_dir": "~/Research/vault",
            "default_model": "gpt-5-codex",
            "default_reasoning": "high",
            "default_sandbox": "read-only",
            "codex_binary": "/usr/local/bin/codex",
            "query_timeout_seconds": 600,
        }

    @pytest.mark.asyncio
    async def test_on_load_success(self, plugin, mock_config):
        """Test successful plugin loading."""
        # Mock config access via _config
        plugin._config = mock_config

        # Mock subprocess to simulate codex binary exists
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="codex version 1.0.0\n", stderr=""
            )

            result = await plugin.on_load(MagicMock())

            assert result is True
            assert plugin._work_dir == "~/Research/vault"
            assert plugin._default_model == "gpt-5-codex"
            assert plugin._default_reasoning == "high"
            assert plugin._default_sandbox == "read-only"
            assert plugin._codex_binary == "/usr/local/bin/codex"
            assert plugin._timeout == 600

            # Verify codex --version was called
            mock_run.assert_called_once()
            assert "--version" in str(mock_run.call_args)

    @pytest.mark.asyncio
    async def test_on_load_binary_not_found(self, plugin, mock_config):
        """Test loading fails when binary not found."""
        plugin._config = mock_config

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("codex not found")

            result = await plugin.on_load(MagicMock())

            assert result is False

    @pytest.mark.asyncio
    async def test_on_load_binary_check_fails(self, plugin, mock_config):
        """Test loading fails when binary check returns error."""
        plugin._config = mock_config

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error")

            result = await plugin.on_load(MagicMock())

            assert result is False

    @pytest.mark.asyncio
    async def test_on_activate(self, plugin):
        """Test plugin activation."""
        result = await plugin.on_activate(MagicMock())
        assert result is True


class TestCodexCommandHandlers:
    """Tests for command handler registration."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        return CodexPlugin(tmp_path)

    def test_get_command_handlers(self, plugin):
        """Test command handlers are registered."""
        handlers = plugin.get_command_handlers()

        assert len(handlers) == 1
        # Handler should be for "codex" command
        handler = handlers[0]
        assert hasattr(handler, "callback")


class TestCodexFlagParsing:
    """Tests for inline flag parsing."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        plugin = CodexPlugin(tmp_path)
        # Set defaults
        plugin._default_model = "gpt-5-codex"
        plugin._default_reasoning = "high"
        plugin._default_sandbox = "read-only"
        plugin._work_dir = "~/Research/vault"
        return plugin

    def test_parse_flags_defaults(self, plugin):
        """Test parsing with no flags uses defaults."""
        result = plugin._parse_flags("Analyze the auth module")

        assert result["model"] == "gpt-5-codex"
        assert result["effort"] == "high"
        assert result["sandbox"] == "read-only"
        assert "vault" in result["cwd"]
        assert result["prompt"] == "Analyze the auth module"

    def test_parse_flags_model(self, plugin):
        """Test parsing --model flag."""
        result = plugin._parse_flags("--model gpt-5 Analyze code")

        assert result["model"] == "gpt-5"
        assert result["prompt"] == "Analyze code"

    def test_parse_flags_effort(self, plugin):
        """Test parsing --effort flag."""
        result = plugin._parse_flags("--effort medium Refactor")

        assert result["effort"] == "medium"
        assert result["prompt"] == "Refactor"

    def test_parse_flags_sandbox(self, plugin):
        """Test parsing --sandbox flag."""
        result = plugin._parse_flags("--sandbox workspace-write Fix bugs")

        assert result["sandbox"] == "workspace-write"
        assert result["prompt"] == "Fix bugs"

    def test_parse_flags_cwd(self, plugin):
        """Test parsing -C flag."""
        result = plugin._parse_flags("-C /tmp/project Check tests")

        assert result["cwd"] == "/tmp/project"
        assert result["prompt"] == "Check tests"

    def test_parse_flags_multiple(self, plugin):
        """Test parsing multiple flags."""
        result = plugin._parse_flags(
            "--model gpt-5 --effort low --sandbox read-only -C /home/user Do analysis"
        )

        assert result["model"] == "gpt-5"
        assert result["effort"] == "low"
        assert result["sandbox"] == "read-only"
        assert result["cwd"] == "/home/user"
        assert result["prompt"] == "Do analysis"

    def test_parse_flags_order_independent(self, plugin):
        """Test flags can be in any order."""
        result = plugin._parse_flags(
            "-C /tmp --effort high --model gpt-5-codex Analyze this"
        )

        assert result["model"] == "gpt-5-codex"
        assert result["effort"] == "high"
        assert result["cwd"] == "/tmp"
        assert result["prompt"] == "Analyze this"


class TestCodexSubprocessExecution:
    """Tests for subprocess execution."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        plugin = CodexPlugin(tmp_path)
        plugin._codex_binary = "/usr/local/bin/codex"
        plugin._timeout = 600
        return plugin

    def test_run_subprocess_success(self, plugin):
        """Test successful subprocess execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Analysis complete", stderr=""
            )

            output = plugin._run_subprocess("codex exec test", cwd="/tmp", timeout=10)

            assert output == "Analysis complete"
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert kwargs["shell"] is True
            assert kwargs["cwd"] == "/tmp"
            assert kwargs["timeout"] == 10

    def test_run_subprocess_failure(self, plugin):
        """Test subprocess execution failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Codex error")

            with pytest.raises(RuntimeError) as exc_info:
                plugin._run_subprocess("codex exec test", cwd="/tmp", timeout=10)

            assert "Codex failed" in str(exc_info.value)
            assert "Codex error" in str(exc_info.value)

    def test_run_subprocess_timeout(self, plugin):
        """Test subprocess timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

            with pytest.raises(subprocess.TimeoutExpired):
                plugin._run_subprocess("codex exec test", cwd="/tmp", timeout=10)


class TestCodexOutputFormatting:
    """Tests for output formatting."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        return CodexPlugin(tmp_path)

    def test_format_output_empty(self, plugin):
        """Test formatting empty output."""
        result = plugin._format_output("")

        assert result == "<i>No output</i>"

    def test_format_output_text(self, plugin):
        """Test formatting plain text output."""
        result = plugin._format_output("Analysis complete: no issues found")

        assert "Analysis complete" in result
        assert "no issues found" in result

    def test_format_output_code(self, plugin):
        """Test formatting code output."""
        code_output = "```python\ndef hello():\n    pass\n```"
        result = plugin._format_output(code_output)

        assert "<pre>" in result
        assert "</pre>" in result

    def test_escape_html(self, plugin):
        """Test HTML escaping."""
        text = "<script>alert('xss')</script> & test"
        result = plugin._escape_html(text)

        assert "&lt;script&gt;" in result
        assert "&amp;" in result
        assert "<script>" not in result


class TestCodexCommandHandling:
    """Tests for command handling logic."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        plugin = CodexPlugin(tmp_path)
        plugin._work_dir = "~/Research/vault"
        plugin._default_model = "gpt-5-codex"
        plugin._default_reasoning = "high"
        plugin._default_sandbox = "read-only"
        plugin._codex_binary = "/usr/local/bin/codex"
        plugin._timeout = 600
        return plugin

    @pytest.fixture
    def mock_update(self):
        """Create mock Update object."""
        update = MagicMock()
        update.effective_user = MagicMock(
            id=123, username="testuser", first_name="Test", last_name="User"
        )
        update.effective_chat = MagicMock(id=456)
        update.message = MagicMock(
            chat_id=456,
            message_id=789,
            text="/codex Test prompt",
        )
        # Make reply_text async
        update.message.reply_text = AsyncMock()
        return update

    @pytest.fixture
    def mock_context(self):
        """Create mock Context object."""
        context = MagicMock()
        context.args = ["Test", "prompt"]
        return context

    @pytest.mark.asyncio
    async def test_handle_codex_no_permission(self, plugin, mock_update, mock_context):
        """Test command handling without permission."""
        with patch(
            "src.services.claude_code_service.is_claude_code_admin",
            return_value=False,
        ):
            await plugin._handle_codex(mock_update, mock_context)

            # Should reply with permission error
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            assert "permission" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_codex_help_subcommand(
        self, plugin, mock_update, mock_context
    ):
        """Test /codex:help subcommand."""
        mock_update.message.text = "/codex:help"

        with (
            patch(
                "src.services.claude_code_service.is_claude_code_admin",
                return_value=True,
            ),
            patch("src.bot.handlers.initialize_user_chat", new_callable=AsyncMock),
        ):
            await plugin._handle_codex(mock_update, mock_context)

            # Should show help
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            assert "Codex" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_codex_help(self, plugin, mock_update):
        """Test help text content."""
        await plugin._codex_help(mock_update)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        help_text = call_args[0][0]

        # Check key sections exist
        assert "Codex" in help_text
        assert "/codex" in help_text
        assert "/codex:resume" in help_text
        assert "--model" in help_text
        assert "--effort" in help_text
        assert "--sandbox" in help_text
        assert "-C" in help_text
        assert "gpt-5-codex" in help_text

    @pytest.mark.asyncio
    async def test_codex_resume_no_prompt(self, plugin, mock_update, mock_context):
        """Test resume without prompt shows error."""
        await plugin._codex_resume(mock_update, mock_context, "")

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "provide a prompt" in call_args[0][0].lower()


class TestCodexPluginLifecycle:
    """Tests for plugin lifecycle methods."""

    @pytest.fixture
    def plugin(self, tmp_path):
        from plugins.codex.plugin import CodexPlugin

        return CodexPlugin(tmp_path)

    @pytest.mark.asyncio
    async def test_on_deactivate(self, plugin):
        """Test plugin deactivation."""
        await plugin.on_deactivate()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_on_unload(self, plugin):
        """Test plugin unloading."""
        await plugin.on_unload()
        # Should complete without error
