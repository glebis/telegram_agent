"""
Tests for secure subprocess helper.

The subprocess helper should:
1. Pass data via stdin (not f-string interpolation)
2. Use environment variables for secrets
3. Handle timeouts gracefully
4. Return structured results
"""

import json


class TestSecureSubprocess:
    """Test secure subprocess execution."""

    def test_subprocess_helper_exists(self):
        """The subprocess helper module should exist."""
        from src.utils.subprocess_helper import run_python_script

        assert callable(run_python_script)

    def test_passes_data_via_stdin(self):
        """Data should be passed via stdin, not interpolated."""
        from src.utils.subprocess_helper import run_python_script

        # Script that reads from stdin
        script = """
import sys, json
data = json.load(sys.stdin)
print(json.dumps({"received": data}))
"""
        result = run_python_script(
            script=script,
            input_data={"test_key": "test_value", "special": "chars\"with'quotes"},
            timeout=10,
        )

        assert result.success
        output = json.loads(result.stdout)
        assert output["received"]["test_key"] == "test_value"
        assert output["received"]["special"] == "chars\"with'quotes"

    def test_passes_secrets_via_env(self):
        """Secrets should be passed via environment variables."""
        from src.utils.subprocess_helper import run_python_script

        script = """
import os, json
print(json.dumps({"token": os.environ.get("BOT_TOKEN", "missing")}))
"""
        result = run_python_script(
            script=script,
            env_vars={"BOT_TOKEN": "secret123"},
            timeout=10,
        )

        assert result.success
        output = json.loads(result.stdout)
        assert output["token"] == "secret123"

    def test_handles_timeout(self):
        """Should handle timeout gracefully."""
        from src.utils.subprocess_helper import run_python_script

        script = """
import time
time.sleep(10)
print("done")
"""
        result = run_python_script(script=script, timeout=1)

        assert not result.success
        assert "timeout" in result.error.lower()

    def test_handles_script_error(self):
        """Should capture script errors."""
        from src.utils.subprocess_helper import run_python_script

        script = """
raise ValueError("intentional error")
"""
        result = run_python_script(script=script, timeout=10)

        assert not result.success
        assert "ValueError" in result.stderr or "intentional error" in result.stderr

    def test_returns_structured_result(self):
        """Should return a structured result object."""
        from src.utils.subprocess_helper import SubprocessResult, run_python_script

        script = 'print("hello")'
        result = run_python_script(script=script, timeout=10)

        assert isinstance(result, SubprocessResult)
        assert hasattr(result, "success")
        assert hasattr(result, "stdout")
        assert hasattr(result, "stderr")
        assert hasattr(result, "return_code")
        assert hasattr(result, "error")

    def test_combined_stdin_and_env(self):
        """Should support both stdin data and env vars."""
        from src.utils.subprocess_helper import run_python_script

        script = """
import sys, os, json
data = json.load(sys.stdin)
result = {
    "data": data,
    "api_key": os.environ.get("API_KEY"),
}
print(json.dumps(result))
"""
        result = run_python_script(
            script=script,
            input_data={"query": "test"},
            env_vars={"API_KEY": "key123"},
            timeout=10,
        )

        assert result.success
        output = json.loads(result.stdout)
        assert output["data"]["query"] == "test"
        assert output["api_key"] == "key123"


class TestTelegramDownloadHelper:
    """Test Telegram file download helper."""

    def test_download_helper_exists(self):
        """Download helper function should exist."""
        from src.utils.subprocess_helper import download_telegram_file

        assert callable(download_telegram_file)

    def test_download_returns_path_on_success(self):
        """Should return file path on successful download."""
        # This is more of an integration test - we'll mock it
        pass  # Placeholder - actual test requires mocking


class TestTranscriptionHelper:
    """Test audio transcription helper."""

    def test_transcription_helper_exists(self):
        """Transcription helper function should exist."""
        from src.utils.subprocess_helper import transcribe_audio

        assert callable(transcribe_audio)
