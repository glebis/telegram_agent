"""Tests for individual setup wizard steps."""

from unittest.mock import MagicMock, patch

from scripts.setup_wizard.env_manager import EnvManager


class TestPreflightStep:
    """Tests for the preflight check step."""

    def test_preflight_delegates_to_run_all_checks(self, tmp_path):
        """Preflight step calls run_all_checks and returns report."""
        from scripts.setup_wizard.steps.preflight import run as run_preflight

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        mock_report = MagicMock()
        mock_report.should_block_startup = False
        mock_report.checks = []

        with patch(
            "scripts.setup_wizard.steps.preflight.run_all_checks",
            return_value=mock_report,
        ) as mock_run:
            result = run_preflight(env, console)

        mock_run.assert_called_once()
        assert result is True

    def test_preflight_returns_false_on_blocking_failure(self, tmp_path):
        """Preflight returns False when checks have blocking failures."""
        from scripts.setup_wizard.steps.preflight import run as run_preflight

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        mock_report = MagicMock()
        mock_report.should_block_startup = True
        mock_report.checks = [
            MagicMock(
                name="python_version", status=MagicMock(value="fail"), message="Too old"
            )
        ]

        with patch(
            "scripts.setup_wizard.steps.preflight.run_all_checks",
            return_value=mock_report,
        ):
            result = run_preflight(env, console)

        assert result is False


class TestCoreConfigStep:
    """Tests for core configuration step."""

    def test_collects_bot_token(self, tmp_path):
        """Core config stores the bot token in env manager."""
        from scripts.setup_wizard.steps.core_config import run as run_core

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.core_config.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.core_config.validate_bot_token",
                return_value=(True, "TestBot"),
            ),
        ):
            mock_q.password.return_value.ask.return_value = "123456:ABC-DEF"
            mock_q.confirm.return_value.ask.return_value = True  # auto-generate secret
            mock_q.select.return_value.ask.return_value = "development"

            result = run_core(env, console)

        assert result is True
        assert env.get("TELEGRAM_BOT_TOKEN") == "123456:ABC-DEF"

    def test_auto_generates_webhook_secret(self, tmp_path):
        """When user confirms, webhook secret is auto-generated."""
        from scripts.setup_wizard.steps.core_config import run as run_core

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.core_config.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.core_config.validate_bot_token",
                return_value=(True, "TestBot"),
            ),
        ):
            mock_q.password.return_value.ask.return_value = "123456:ABC-DEF"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "development"

            run_core(env, console)

        secret = env.get("TELEGRAM_WEBHOOK_SECRET")
        assert len(secret) == 64  # 32 bytes hex

    def test_manual_webhook_secret(self, tmp_path):
        """When user declines auto-generate, they enter secret manually."""
        from scripts.setup_wizard.steps.core_config import run as run_core

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.core_config.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.core_config.validate_bot_token",
                return_value=(True, "TestBot"),
            ),
        ):
            mock_q.password.return_value.ask.side_effect = [
                "123456:ABC-DEF",  # bot token
                "my-custom-secret",  # manual secret
            ]
            mock_q.confirm.return_value.ask.return_value = False  # don't auto-generate
            mock_q.select.return_value.ask.return_value = "development"

            run_core(env, console)

        assert env.get("TELEGRAM_WEBHOOK_SECRET") == "my-custom-secret"

    def test_sets_environment(self, tmp_path):
        """Environment selection is stored."""
        from scripts.setup_wizard.steps.core_config import run as run_core

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.core_config.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.core_config.validate_bot_token",
                return_value=(True, "TestBot"),
            ),
        ):
            mock_q.password.return_value.ask.return_value = "123456:ABC-DEF"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "production"

            run_core(env, console)

        assert env.get("ENVIRONMENT") == "production"

    def test_returns_false_on_cancelled_token(self, tmp_path):
        """If user cancels token prompt (None), step returns False."""
        from scripts.setup_wizard.steps.core_config import run as run_core

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.core_config.questionary") as mock_q:
            mock_q.password.return_value.ask.return_value = None

            result = run_core(env, console)

        assert result is False


class TestApiKeysStep:
    """Tests for API keys configuration step."""

    def test_all_keys_skipped(self, tmp_path):
        """Empty strings mean no keys are stored."""
        from scripts.setup_wizard.steps.api_keys import run as run_api

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.api_keys.questionary") as mock_q:
            mock_q.password.return_value.ask.return_value = ""

            result = run_api(env, console)

        assert result is True
        assert not env.has("OPENAI_API_KEY")
        assert not env.has("GROQ_API_KEY")
        assert not env.has("ANTHROPIC_API_KEY")

    def test_partial_keys(self, tmp_path):
        """Only filled keys are stored."""
        from scripts.setup_wizard.steps.api_keys import run as run_api

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.api_keys.questionary") as mock_q:
            mock_q.password.return_value.ask.side_effect = [
                "sk-openai-key",  # OpenAI
                "",  # Groq (skip)
                "",  # Anthropic (skip)
                "",  # Google API Key (skip)
                "",  # Google Search CX (skip)
                "",  # Firecrawl (skip)
            ]

            result = run_api(env, console)

        assert result is True
        assert env.get("OPENAI_API_KEY") == "sk-openai-key"
        assert not env.has("GROQ_API_KEY")
        assert not env.has("ANTHROPIC_API_KEY")


class TestOptionalFeaturesStep:
    """Tests for optional features configuration."""

    def test_vault_path_expanded(self, tmp_path):
        """Tilde in vault path gets expanded to absolute path."""
        from scripts.setup_wizard.steps.optional_features import run as run_optional

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.optional_features.questionary"
        ) as mock_q:
            mock_q.text.return_value.ask.side_effect = [
                "~/Research/vault",  # vault path
                "",  # Claude work dir (skip)
            ]

            run_optional(env, console)

        vault_path = env.get("OBSIDIAN_VAULT_PATH")
        assert "~" not in vault_path
        assert vault_path.endswith("Research/vault")

    def test_all_skipped(self, tmp_path):
        """Empty strings mean nothing is stored."""
        from scripts.setup_wizard.steps.optional_features import run as run_optional

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.optional_features.questionary"
        ) as mock_q:
            mock_q.text.return_value.ask.return_value = ""

            run_optional(env, console)

        assert not env.has("OBSIDIAN_VAULT_PATH")
        assert not env.has("CLAUDE_CODE_WORK_DIR")


class TestDatabaseStep:
    """Tests for database initialization step."""

    def test_database_init_called(self, tmp_path):
        """Database step calls init_database."""
        from scripts.setup_wizard.steps.database import run as run_db

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        env.set("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.database.init_database_sync"
        ) as mock_init:
            mock_init.return_value = True
            result = run_db(env, console)

        assert result is True
        mock_init.assert_called_once()

    def test_database_init_failure_warns(self, tmp_path):
        """Database init failure returns True with warning (non-blocking)."""
        from scripts.setup_wizard.steps.database import run as run_db

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.database.init_database_sync"
        ) as mock_init:
            mock_init.side_effect = Exception("DB error")
            result = run_db(env, console)

        # DB init failure is a warning, not blocking
        assert result is True

    def test_database_init_returns_false_warns(self, tmp_path):
        """Database init returning False shows warning but continues."""
        from scripts.setup_wizard.steps.database import run as run_db

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.database.init_database_sync"
        ) as mock_init:
            mock_init.return_value = False
            result = run_db(env, console)

        assert result is True
        # Should have printed a WARN message
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert len(warn_calls) > 0


class TestPreflightStepEdgeCases:
    """Additional preflight edge cases (Codex review fix)."""

    def test_preflight_exception_does_not_crash(self, tmp_path):
        """If run_all_checks raises, wizard continues gracefully."""
        from scripts.setup_wizard.steps.preflight import run as run_preflight

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.preflight.run_all_checks",
            side_effect=RuntimeError("check runner crashed"),
        ):
            result = run_preflight(env, console)

        # Should continue despite exception
        assert result is True


class TestVerificationStep:
    """Tests for the verification step."""

    def test_verification_displays_summary(self, tmp_path):
        """Verification step shows config summary."""
        from scripts.setup_wizard.steps.verification import run as run_verify

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        env.set("TELEGRAM_BOT_TOKEN", "123:ABC")
        env.set("ENVIRONMENT", "development")
        console = MagicMock()

        with patch(
            "scripts.setup_wizard.steps.verification.validate_bot_token"
        ) as mock_validate:
            mock_validate.return_value = (True, "TestBot")
            result = run_verify(env, console)

        assert result is True

    def test_bot_token_validation_success(self, tmp_path):
        """Successful bot token validation shows bot name."""
        from scripts.setup_wizard.utils import validate_bot_token

        with patch("scripts.setup_wizard.utils.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "ok": True,
                "result": {"username": "my_test_bot"},
            }
            mock_httpx.get.return_value = mock_response

            success, name = validate_bot_token("123:ABC")

        assert success is True
        assert name == "my_test_bot"

    def test_bot_token_validation_failure(self, tmp_path):
        """Failed bot token validation returns False gracefully."""
        from scripts.setup_wizard.utils import validate_bot_token

        with patch("scripts.setup_wizard.utils.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Network error")

            success, name = validate_bot_token("invalid-token")

        assert success is False
        assert name == ""


class TestWebhookStep:
    """Tests for the webhook/tunnel configuration step."""

    def test_webhook_sets_env_values(self, tmp_path):
        """All prompts populate env values for webhook and limits."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[2048, 10, 30, 500000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "https://example.com"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "skip"

            result = run_webhook(env, console)

        assert result is True
        assert env.get("WEBHOOK_BASE_URL") == "https://example.com"
        assert env.get("WEBHOOK_USE_HTTPS") == "true"
        assert env.get("WEBHOOK_MAX_BODY_BYTES") == "2048"
        assert env.get("WEBHOOK_RATE_LIMIT") == "10"
        assert env.get("WEBHOOK_RATE_WINDOW_SECONDS") == "30"
        assert env.get("API_MAX_BODY_BYTES") == "500000"

    def test_webhook_cancel_returns_false(self, tmp_path):
        """If user cancels at first prompt, step aborts without writes."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = None
            result = run_webhook(env, console)

        assert result is False
        assert not env.has("WEBHOOK_BASE_URL")


class TestPluginsStep:
    """Tests for plugin enablement step."""

    def test_plugins_write_overrides_and_warn_missing(self, tmp_path):
        """Prereq warnings surface and overrides are written per plugin."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()

        # pdf plugin to trigger prereq warning
        pdf_dir = plugins_root / "pdf"
        pdf_dir.mkdir()
        (pdf_dir / "plugin.yaml").write_text("name: pdf\nenabled: true\n")

        # custom plugin without prereqs
        custom_dir = plugins_root / "custom"
        custom_dir.mkdir()
        (custom_dir / "plugin.yaml").write_text("name: custom\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def fake_confirm(prompt, **_):
            answer = True if "pdf" in prompt else False
            m = MagicMock()
            m.ask.return_value = answer
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
            patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None),
        ):
            mock_q.confirm.side_effect = fake_confirm
            result = plugins_step.run(env, console)

        assert result is True

        # pdf enabled, custom disabled
        pdf_override = pdf_dir / "plugin.local.yaml"
        custom_override = custom_dir / "plugin.local.yaml"
        assert pdf_override.exists() and custom_override.exists()
        assert "enabled: true" in pdf_override.read_text()
        assert "enabled: false" in custom_override.read_text()

        # Warning printed for missing prereq
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected a warning for missing prereqs"

    def test_plugins_cancel_returns_false(self, tmp_path):
        """Canceling a confirmation aborts the step."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        plugin_dir = plugins_root / "pdf"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text("name: pdf\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def cancel_confirm(prompt, **_):
            m = MagicMock()
            m.ask.return_value = None
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
        ):
            mock_q.confirm.side_effect = cancel_confirm
            result = plugins_step.run(env, console)

        assert result is False


class TestPluginPrereqIdMatching:
    """Ensure prereq detection keys off stable identifiers (slug/id)."""

    def test_prereq_uses_slug_not_friendly_name(self, tmp_path):
        """Directory name (slug) triggers prereq check even with a different display name."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        cc_dir = plugins_root / "claude_code"
        cc_dir.mkdir()
        (cc_dir / "plugin.yaml").write_text(
            "name: Claude Code Friendly\nenabled: true\n"
        )

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def always_enable(prompt, **_):
            m = MagicMock()
            m.ask.return_value = True
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
            patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None),
        ):
            mock_q.confirm.side_effect = always_enable
            result = plugins_step.run(env, console)

        assert result is True
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected a warning for missing Claude CLI based on slug"

    def test_norm_id_is_case_insensitive(self):
        """_norm_id normalizes to lowercase and replaces hyphens."""
        from scripts.setup_wizard.steps.plugins import _norm_id

        assert _norm_id("Claude-Code") == "claude_code"
        assert _norm_id("PDF") == "pdf"
        assert _norm_id("claude_code") == "claude_code"
        assert _norm_id("CLAUDE-CODE") == "claude_code"

    def test_norm_id_handles_none_and_empty(self):
        """_norm_id gracefully handles None and empty strings."""
        from scripts.setup_wizard.steps.plugins import _norm_id

        assert _norm_id(None) == ""
        assert _norm_id("") == ""
        assert _norm_id("  ") == ""

    def test_check_prereqs_uses_normalized_slug(self):
        """_check_prereqs matches slugs after normalization."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        # "claude_code" should match the Claude prereq
        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which", return_value=None
        ):
            missing = _check_prereqs("claude_code")
        assert any("Claude Code CLI" in desc for desc, _ in missing)

        # "Claude-Code" (mixed case with hyphen) should also match
        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which", return_value=None
        ):
            missing = _check_prereqs("Claude-Code")
        assert any("Claude Code CLI" in desc for desc, _ in missing)

    def test_check_prereqs_pdf_slug(self):
        """PDF prereq is detected via slug 'pdf'."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which", return_value=None
        ):
            missing = _check_prereqs("pdf")
        assert any("marker_single" in desc for desc, _ in missing)

    def test_check_prereqs_unknown_slug_returns_empty(self):
        """Unknown slug returns no prereq warnings."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        missing = _check_prereqs("some_random_plugin")
        assert missing == []

    def test_explicit_id_field_overrides_dir_name(self, tmp_path):
        """When plugin.yaml has an explicit 'id' field, that overrides dir name."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        # Directory name is "my_fancy_pdf", but id is "pdf"
        pdf_dir = plugins_root / "my_fancy_pdf"
        pdf_dir.mkdir()
        (pdf_dir / "plugin.yaml").write_text(
            "name: My Fancy PDF Converter\nid: pdf\nenabled: true\n"
        )

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def always_enable(prompt, **_):
            m = MagicMock()
            m.ask.return_value = True
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
            patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None),
        ):
            mock_q.confirm.side_effect = always_enable
            result = plugins_step.run(env, console)

        assert result is True
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected warning via explicit id field overriding dir name"

    def test_missing_id_falls_back_to_dir_name(self, tmp_path):
        """Without an 'id' field, the directory name is used as the slug."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        pdf_dir = plugins_root / "pdf"
        pdf_dir.mkdir()
        # No 'id' field in config
        (pdf_dir / "plugin.yaml").write_text("name: PDF Converter Pro\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def always_enable(prompt, **_):
            m = MagicMock()
            m.ask.return_value = True
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
            patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None),
        ):
            mock_q.confirm.side_effect = always_enable
            result = plugins_step.run(env, console)

        assert result is True
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected warning from dir name fallback"


class TestWizardOrdering:
    """Ensure step order includes webhook and plugins."""

    def test_wizard_step_sequence(self, tmp_path):
        from scripts.setup_wizard.wizard import SetupWizard

        wiz = SetupWizard(env_path=tmp_path / ".env.local")
        names = [name for name, _ in wiz.steps]
        assert names == [
            "Pre-flight Checks",
            "Core Configuration",
            "Webhook & Tunnel",
            "API Keys",
            "Optional Features",
            "Plugins",
            "Database",
            "Verification",
        ]


# ---------------------------------------------------------------------------
# Webhook step: tunnel providers, auto-detect, prompt_int, cancel paths
# ---------------------------------------------------------------------------


class TestWebhookTunnelProviders:
    """Tests for each tunnel provider sub-flow in the webhook step."""

    def _make_env(self, tmp_path):
        env = EnvManager(tmp_path / ".env.local")
        env.load()
        return env

    def test_ngrok_tunnel_sets_all_env_vars(self, tmp_path):
        """Selecting ngrok collects authtoken, region, and port."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            # Main prompts: base_url, confirm HTTPS, tunnel select
            mock_q.text.return_value.ask.return_value = "https://my.app"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "ngrok"
            # ngrok sub-prompts: authtoken, region
            mock_q.password.return_value.ask.return_value = "tok_abc123"

            with patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000, 8080],
            ):
                result = run_webhook(env, console)

        assert result is True
        assert env.get("TUNNEL_PROVIDER") == "ngrok"
        assert env.get("NGROK_AUTHTOKEN") == "tok_abc123"
        assert env.get("TUNNEL_PORT") == "8080"
        assert env.get("NGROK_PORT") == "8080"

    def test_cloudflare_tunnel_sets_env_vars(self, tmp_path):
        """Selecting cloudflare collects tunnel name, credentials, and port."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.side_effect = [
                "https://my.app",  # base_url
                "my-tunnel",  # CF tunnel name
                "/path/to/creds.json",  # CF credentials
            ]
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = (
                "cloudflare (recommended for prod)"
            )

            with patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000, 9000],
            ):
                result = run_webhook(env, console)

        assert result is True
        assert env.get("TUNNEL_PROVIDER") == "cloudflare"
        assert env.get("CF_TUNNEL_NAME") == "my-tunnel"
        assert env.get("CF_CREDENTIALS_FILE") == "/path/to/creds.json"
        assert env.get("TUNNEL_PORT") == "9000"

    def test_tailscale_tunnel_sets_env_vars(self, tmp_path):
        """Selecting tailscale collects hostname and port."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.side_effect = [
                "https://my.app",  # base_url
                "myhost",  # tailscale hostname
            ]
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "tailscale"

            with patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000, 443],
            ):
                result = run_webhook(env, console)

        assert result is True
        assert env.get("TUNNEL_PROVIDER") == "tailscale"
        assert env.get("TAILSCALE_HOSTNAME") == "myhost"
        assert env.get("TUNNEL_PORT") == "443"

    def test_skip_tunnel_sets_provider_none(self, tmp_path):
        """Selecting 'skip' sets TUNNEL_PROVIDER to 'none'."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "https://example.com"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "skip"

            result = run_webhook(env, console)

        assert result is True
        assert env.get("TUNNEL_PROVIDER") == "none"

    def test_https_false_stored(self, tmp_path):
        """When user declines HTTPS, 'false' is stored."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "http://localhost:8000"
            mock_q.confirm.return_value.ask.return_value = False
            mock_q.select.return_value.ask.return_value = "skip"

            result = run_webhook(env, console)

        assert result is True
        assert env.get("WEBHOOK_USE_HTTPS") == "false"

    def test_base_url_whitespace_stripped(self, tmp_path):
        """Leading/trailing whitespace in base URL is stripped."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "  https://example.com  "
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "skip"

            result = run_webhook(env, console)

        assert result is True
        assert env.get("WEBHOOK_BASE_URL") == "https://example.com"

    def test_empty_base_url_not_stored(self, tmp_path):
        """Empty base URL string does not get stored."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = ""
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "skip"

            result = run_webhook(env, console)

        assert result is True
        assert not env.has("WEBHOOK_BASE_URL")


class TestWebhookCancelPaths:
    """Tests for cancel (None) at various prompts in the webhook step."""

    def _make_env(self, tmp_path):
        env = EnvManager(tmp_path / ".env.local")
        env.load()
        return env

    def test_cancel_at_https_confirm(self, tmp_path):
        """Canceling at the HTTPS confirmation aborts the step."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = "https://example.com"
            mock_q.confirm.return_value.ask.return_value = None

            result = run_webhook(env, console)

        assert result is False

    def test_cancel_at_tunnel_select(self, tmp_path):
        """Canceling at tunnel selection aborts the step."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "https://example.com"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = None

            result = run_webhook(env, console)

        assert result is False

    def test_cancel_at_ngrok_authtoken(self, tmp_path):
        """Canceling during ngrok authtoken prompt aborts the step."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.return_value = "https://example.com"
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "ngrok"
            mock_q.password.return_value.ask.return_value = None

            result = run_webhook(env, console)

        assert result is False

    def test_cancel_at_cloudflare_tunnel_name(self, tmp_path):
        """Canceling during cloudflare tunnel name prompt aborts."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.side_effect = [
                "https://example.com",  # base_url
                None,  # CF tunnel name -> cancel
            ]
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = (
                "cloudflare (recommended for prod)"
            )

            result = run_webhook(env, console)

        assert result is False

    def test_cancel_at_tailscale_hostname(self, tmp_path):
        """Canceling during tailscale hostname prompt aborts."""
        from scripts.setup_wizard.steps.webhook import run as run_webhook

        env = self._make_env(tmp_path)
        console = MagicMock()

        with (
            patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q,
            patch(
                "scripts.setup_wizard.steps.webhook._prompt_int",
                side_effect=[1048576, 120, 60, 1000000],
            ),
        ):
            mock_q.text.return_value.ask.side_effect = [
                "https://example.com",  # base_url
                None,  # tailscale hostname -> cancel
            ]
            mock_q.confirm.return_value.ask.return_value = True
            mock_q.select.return_value.ask.return_value = "tailscale"

            result = run_webhook(env, console)

        assert result is False


class TestAutoDetectDefault:
    """Tests for _auto_detect_default() tunnel auto-selection logic."""

    def _make_env(self, tmp_path, **kv):
        env = EnvManager(tmp_path / ".env.local")
        env.load()
        for k, v in kv.items():
            env.set(k, v)
        return env

    def test_explicit_tunnel_provider_wins(self, tmp_path):
        """If TUNNEL_PROVIDER is set, that value is returned directly."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path, TUNNEL_PROVIDER="ngrok")
        assert _auto_detect_default(env) == "ngrok"

    def test_cf_tunnel_name_implies_cloudflare(self, tmp_path):
        """CF_TUNNEL_NAME in env implies cloudflare."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path, CF_TUNNEL_NAME="my-tunnel")
        assert _auto_detect_default(env) == "cloudflare (recommended for prod)"

    def test_cf_credentials_implies_cloudflare(self, tmp_path):
        """CF_CREDENTIALS_FILE in env implies cloudflare."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path, CF_CREDENTIALS_FILE="/tmp/creds.json")
        assert _auto_detect_default(env) == "cloudflare (recommended for prod)"

    def test_tailscale_hostname_implies_tailscale(self, tmp_path):
        """TAILSCALE_HOSTNAME in env implies tailscale."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path, TAILSCALE_HOSTNAME="myhost")
        assert _auto_detect_default(env) == "tailscale"

    def test_ngrok_authtoken_implies_ngrok(self, tmp_path):
        """NGROK_AUTHTOKEN in env implies ngrok."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path, NGROK_AUTHTOKEN="tok123")
        assert _auto_detect_default(env) == "ngrok"

    def test_no_env_vars_returns_skip(self, tmp_path):
        """With no tunnel env vars at all, 'skip' is the default."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(tmp_path)
        assert _auto_detect_default(env) == "skip"

    def test_priority_order(self, tmp_path):
        """TUNNEL_PROVIDER takes precedence over all other indicators."""
        from scripts.setup_wizard.steps.webhook import _auto_detect_default

        env = self._make_env(
            tmp_path,
            TUNNEL_PROVIDER="tailscale",
            CF_TUNNEL_NAME="present",
            NGROK_AUTHTOKEN="present",
        )
        assert _auto_detect_default(env) == "tailscale"


class TestPromptInt:
    """Tests for the _prompt_int helper in the webhook step."""

    def test_valid_integer(self):
        """Normal integer input returns that integer."""
        from scripts.setup_wizard.steps.webhook import _prompt_int

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = "42"
            result = _prompt_int("Test", None, 10)

        assert result == 42

    def test_invalid_input_returns_default(self):
        """Non-numeric input returns the default value."""
        from scripts.setup_wizard.steps.webhook import _prompt_int

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = "not_a_number"
            result = _prompt_int("Test", None, 99)

        assert result == 99

    def test_none_returns_none(self):
        """When user cancels (None), None is returned."""
        from scripts.setup_wizard.steps.webhook import _prompt_int

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = None
            result = _prompt_int("Test", None, 10)

        assert result is None

    def test_current_value_used_as_default(self):
        """When current value exists, it's passed as the text default."""
        from scripts.setup_wizard.steps.webhook import _prompt_int

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = "8080"
            result = _prompt_int("Port", "8080", 8000)
            mock_q.text.assert_called_once_with("Port", default="8080")

        assert result == 8080

    def test_empty_string_returns_default(self):
        """Empty string (user presses enter with no current) returns default."""
        from scripts.setup_wizard.steps.webhook import _prompt_int

        with patch("scripts.setup_wizard.steps.webhook.questionary") as mock_q:
            mock_q.text.return_value.ask.return_value = ""
            result = _prompt_int("Port", None, 8000)

        assert result == 8000


# ---------------------------------------------------------------------------
# Plugins step: edge cases for discovery, filesystem, and runtime warnings
# ---------------------------------------------------------------------------


class TestPluginsNoDirectory:
    """Tests for plugins step when the plugins directory is missing or empty."""

    def test_no_plugins_directory(self, tmp_path):
        """Step returns True with a warning when PLUGINS_ROOT does not exist."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        nonexistent = tmp_path / "no_such_dir"
        with patch.object(plugins_step, "PLUGINS_ROOT", nonexistent):
            result = plugins_step.run(env, console)

        assert result is True
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected a warning about missing plugins directory"

    def test_empty_plugins_directory(self, tmp_path):
        """Step returns True with a warning when no plugins are found."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch.object(plugins_step, "PLUGINS_ROOT", plugins_root):
            result = plugins_step.run(env, console)

        assert result is True
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected a warning about no plugins discovered"

    def test_underscore_dirs_are_skipped(self, tmp_path):
        """Directories starting with _ are ignored during discovery."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        internal = plugins_root / "_internal"
        internal.mkdir()
        (internal / "plugin.yaml").write_text("name: internal\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch.object(plugins_step, "PLUGINS_ROOT", plugins_root):
            result = plugins_step.run(env, console)

        assert result is True
        # No confirm prompt should have been called since the only
        # plugin dir starts with _
        warn_calls = [c for c in console.print.call_args_list if "WARN" in str(c)]
        assert warn_calls, "Expected 'no plugins discovered' warning"

    def test_dir_without_plugin_yaml_skipped(self, tmp_path):
        """Directories without plugin.yaml are not treated as plugins."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        stray = plugins_root / "not_a_plugin"
        stray.mkdir()
        # No plugin.yaml inside

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch.object(plugins_step, "PLUGINS_ROOT", plugins_root):
            result = plugins_step.run(env, console)

        assert result is True


class TestPluginsEnableDisable:
    """Tests for plugin enable/disable toggle behavior."""

    def test_all_plugins_disabled(self, tmp_path):
        """When user disables all plugins, overrides reflect that."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        for name in ("alpha", "beta"):
            d = plugins_root / name
            d.mkdir()
            (d / "plugin.yaml").write_text(f"name: {name}\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def always_disable(prompt, **_):
            m = MagicMock()
            m.ask.return_value = False
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
        ):
            mock_q.confirm.side_effect = always_disable
            result = plugins_step.run(env, console)

        assert result is True
        for name in ("alpha", "beta"):
            override = plugins_root / name / "plugin.local.yaml"
            assert override.exists()
            assert "enabled: false" in override.read_text()

    def test_all_plugins_enabled(self, tmp_path):
        """When user enables all plugins, overrides reflect that."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        for name in ("alpha", "beta"):
            d = plugins_root / name
            d.mkdir()
            (d / "plugin.yaml").write_text(f"name: {name}\nenabled: false\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def always_enable(prompt, **_):
            m = MagicMock()
            m.ask.return_value = True
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
        ):
            mock_q.confirm.side_effect = always_enable
            result = plugins_step.run(env, console)

        assert result is True
        for name in ("alpha", "beta"):
            override = plugins_root / name / "plugin.local.yaml"
            assert override.exists()
            assert "enabled: true" in override.read_text()

    def test_enabled_default_false_sets_confirm_default_false(self, tmp_path):
        """Plugin with enabled: false in config defaults the confirm to False."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        d = plugins_root / "myplug"
        d.mkdir()
        (d / "plugin.yaml").write_text("name: myplug\nenabled: false\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
        ):
            mock_q.confirm.return_value.ask.return_value = False
            plugins_step.run(env, console)

            # The confirm call should have default=False because plugin config
            # has enabled: false
            call_kwargs = mock_q.confirm.call_args
            assert call_kwargs[1].get("default") is False or (
                len(call_kwargs[0]) > 1 and call_kwargs[0][1] is False
            )

    def test_enabling_with_missing_prereqs_prints_warning(self, tmp_path):
        """Enabling a plugin despite missing prereqs emits an extra warning."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        d = plugins_root / "pdf"
        d.mkdir()
        (d / "plugin.yaml").write_text("name: pdf\nenabled: true\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        def enable_it(prompt, **_):
            m = MagicMock()
            m.ask.return_value = True
            return m

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
            patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None),
        ):
            mock_q.confirm.side_effect = enable_it
            result = plugins_step.run(env, console)

        assert result is True
        # Should have both the prereq warning AND the "enabling without
        # prerequisites" warning
        all_prints = [str(c) for c in console.print.call_args_list]
        prereq_warns = [p for p in all_prints if "prerequisites" in p.lower()]
        assert (
            len(prereq_warns) >= 1
        ), "Expected 'enabling without prerequisites' warning"

    def test_plugin_with_description_shown_in_prompt(self, tmp_path):
        """Plugin description from YAML is included in the confirm prompt."""
        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        d = plugins_root / "myplug"
        d.mkdir()
        (d / "plugin.yaml").write_text(
            "name: My Plugin\ndescription: Does cool things\nenabled: true\n"
        )

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with (
            patch.object(plugins_step, "PLUGINS_ROOT", plugins_root),
            patch("scripts.setup_wizard.steps.plugins.questionary") as mock_q,
        ):
            mock_q.confirm.return_value.ask.return_value = True
            plugins_step.run(env, console)

            prompt_text = mock_q.confirm.call_args[0][0]
            assert "Does cool things" in prompt_text

    def test_malformed_yaml_raises(self, tmp_path):
        """Malformed plugin.yaml causes an error (not silently swallowed)."""
        import pytest

        from scripts.setup_wizard.steps import plugins as plugins_step

        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        d = plugins_root / "bad"
        d.mkdir()
        (d / "plugin.yaml").write_text("name: [invalid yaml\n  broken: {{\n")

        env = EnvManager(tmp_path / ".env.local")
        env.load()
        console = MagicMock()

        with patch.object(plugins_step, "PLUGINS_ROOT", plugins_root):
            with pytest.raises(Exception):
                plugins_step.run(env, console)


class TestPluginsWriteOverride:
    """Tests for _write_local_override helper."""

    def test_write_enabled_true(self, tmp_path):
        """_write_local_override writes enabled: true."""
        from scripts.setup_wizard.steps.plugins import _write_local_override

        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        _write_local_override(plugin_dir, True)

        override = plugin_dir / "plugin.local.yaml"
        assert override.exists()
        content = override.read_text()
        assert "enabled: true" in content

    def test_write_enabled_false(self, tmp_path):
        """_write_local_override writes enabled: false."""
        from scripts.setup_wizard.steps.plugins import _write_local_override

        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        _write_local_override(plugin_dir, False)

        override = plugin_dir / "plugin.local.yaml"
        assert override.exists()
        content = override.read_text()
        assert "enabled: false" in content

    def test_write_override_overwrites_existing(self, tmp_path):
        """Calling _write_local_override twice replaces the file."""
        from scripts.setup_wizard.steps.plugins import _write_local_override

        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        _write_local_override(plugin_dir, True)
        _write_local_override(plugin_dir, False)

        content = (plugin_dir / "plugin.local.yaml").read_text()
        assert "enabled: false" in content
        assert "enabled: true" not in content


class TestPluginsLoadConfig:
    """Tests for _load_plugin_config helper."""

    def test_load_valid_config(self, tmp_path):
        """Valid YAML loads into a dict."""
        from scripts.setup_wizard.steps.plugins import _load_plugin_config

        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.yaml").write_text("name: test\nenabled: true\ndescription: hi\n")

        config = _load_plugin_config(d)
        assert config["name"] == "test"
        assert config["enabled"] is True
        assert config["description"] == "hi"

    def test_load_empty_yaml_returns_empty_dict(self, tmp_path):
        """Empty YAML file returns empty dict (not None)."""
        from scripts.setup_wizard.steps.plugins import _load_plugin_config

        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.yaml").write_text("")

        config = _load_plugin_config(d)
        assert config == {}

    def test_load_missing_file_raises(self, tmp_path):
        """Missing plugin.yaml raises FileNotFoundError."""
        import pytest

        from scripts.setup_wizard.steps.plugins import _load_plugin_config

        d = tmp_path / "myplugin"
        d.mkdir()

        with pytest.raises(FileNotFoundError):
            _load_plugin_config(d)


class TestCheckPrereqsWithBinaries:
    """Tests for _check_prereqs with both present and absent binaries."""

    def test_pdf_prereqs_satisfied(self):
        """When marker_single is on PATH, no prereqs are missing."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which",
            return_value="/usr/local/bin/marker_single",
        ):
            missing = _check_prereqs("pdf")
        assert missing == []

    def test_claude_prereqs_satisfied_by_claude_binary(self):
        """When 'claude' binary exists, claude_code prereq is satisfied."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        def which_side_effect(name):
            if name == "claude":
                return "/usr/local/bin/claude"
            return None

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which",
            side_effect=which_side_effect,
        ):
            missing = _check_prereqs("claude_code")
        assert missing == []

    def test_claude_prereqs_satisfied_by_claude_code_binary(self):
        """When 'claude-code' binary exists, claude_code prereq is satisfied."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        def which_side_effect(name):
            if name == "claude-code":
                return "/usr/local/bin/claude-code"
            return None

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which",
            side_effect=which_side_effect,
        ):
            missing = _check_prereqs("claude_code")
        assert missing == []

    def test_claude_prereqs_missing_both_binaries(self):
        """When neither 'claude' nor 'claude-code' exist, prereq is missing."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which", return_value=None
        ):
            missing = _check_prereqs("claude_code")
        assert len(missing) == 1
        assert "Claude Code CLI" in missing[0][0]

    def test_prereq_hint_included(self):
        """Missing prereq entries include install hints."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        with patch(
            "scripts.setup_wizard.steps.plugins.shutil.which", return_value=None
        ):
            missing = _check_prereqs("pdf")
        assert len(missing) == 1
        _, hint = missing[0]
        assert "pip install" in hint
