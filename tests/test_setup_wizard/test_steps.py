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
        (cc_dir / "plugin.yaml").write_text("name: Claude Code Friendly\nenabled: true\n")

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
        with patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None):
            missing = _check_prereqs("claude_code")
        assert any("Claude Code CLI" in desc for desc, _ in missing)

        # "Claude-Code" (mixed case with hyphen) should also match
        with patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None):
            missing = _check_prereqs("Claude-Code")
        assert any("Claude Code CLI" in desc for desc, _ in missing)

    def test_check_prereqs_pdf_slug(self):
        """PDF prereq is detected via slug 'pdf'."""
        from scripts.setup_wizard.steps.plugins import _check_prereqs

        with patch("scripts.setup_wizard.steps.plugins.shutil.which", return_value=None):
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
        (pdf_dir / "plugin.yaml").write_text(
            "name: PDF Converter Pro\nenabled: true\n"
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
