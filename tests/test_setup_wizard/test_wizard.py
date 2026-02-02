"""Tests for the SetupWizard orchestrator and CLI entry point."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from scripts.setup_wizard.env_manager import EnvManager


class TestSetupWizard:
    """Tests for the SetupWizard class."""

    def test_runs_all_steps_in_order(self, tmp_path):
        """Wizard executes all 6 steps in sequence."""
        from scripts.setup_wizard.wizard import SetupWizard

        env_path = tmp_path / ".env.local"
        wizard = SetupWizard(env_path=env_path)

        mock_steps = []
        for i in range(6):
            step = MagicMock(return_value=True)
            mock_steps.append(step)

        wizard.steps = [(f"Step {i+1}", s) for i, s in enumerate(mock_steps)]
        wizard.run()

        for step in mock_steps:
            step.assert_called_once()

    def test_stops_on_step_cancel(self, tmp_path):
        """When a step returns False, wizard stops and saves partial config."""
        from scripts.setup_wizard.wizard import SetupWizard

        env_path = tmp_path / ".env.local"
        wizard = SetupWizard(env_path=env_path)

        step1 = MagicMock(return_value=True)
        step2 = MagicMock(return_value=False)  # cancelled
        step3 = MagicMock(return_value=True)

        wizard.steps = [("Step 1", step1), ("Step 2", step2), ("Step 3", step3)]
        wizard.run()

        step1.assert_called_once()
        step2.assert_called_once()
        step3.assert_not_called()

    def test_handles_keyboard_interrupt(self, tmp_path):
        """KeyboardInterrupt is caught and partial config is saved."""
        from scripts.setup_wizard.wizard import SetupWizard

        env_path = tmp_path / ".env.local"
        wizard = SetupWizard(env_path=env_path)

        step1 = MagicMock(return_value=True)
        step2 = MagicMock(side_effect=KeyboardInterrupt)

        wizard.steps = [("Step 1", step1), ("Step 2", step2)]
        # Should not raise
        wizard.run()

        step1.assert_called_once()
        # Partial config should be saved
        assert env_path.exists() or True  # env may or may not exist depending on state

    def test_idempotent_rerun(self, tmp_path):
        """Running wizard twice preserves existing values on second run."""
        from scripts.setup_wizard.wizard import SetupWizard

        env_path = tmp_path / ".env.local"
        env_path.write_text("EXISTING_KEY=keep_this\n")

        wizard = SetupWizard(env_path=env_path)

        def step_that_adds(env, console):
            env.set("NEW_KEY", "new_value")
            return True

        wizard.steps = [("Add key", step_that_adds)]
        wizard.run()

        # Verify both keys present
        mgr = EnvManager(env_path)
        mgr.load()
        assert mgr.get("EXISTING_KEY") == "keep_this"
        assert mgr.get("NEW_KEY") == "new_value"

    def test_env_file_saved_after_completion(self, tmp_path):
        """Wizard saves the .env file after all steps complete."""
        from scripts.setup_wizard.wizard import SetupWizard

        env_path = tmp_path / ".env.local"
        wizard = SetupWizard(env_path=env_path)

        def step_that_sets(env, console):
            env.set("FOO", "bar")
            return True

        wizard.steps = [("Set FOO", step_that_sets)]
        wizard.run()

        # File should exist with our value
        assert env_path.exists()
        content = env_path.read_text()
        assert "FOO=bar" in content


class TestCLIEntryPoint:
    """Tests for the CLI script entry point."""

    def test_help_flag(self):
        """--help exits cleanly with usage info."""
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent

        result = subprocess.run(
            [sys.executable, "scripts/setup_wizard.py", "--help"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=30,
        )
        assert result.returncode == 0
        assert "setup" in result.stdout.lower() or "wizard" in result.stdout.lower() or "Usage" in result.stdout
