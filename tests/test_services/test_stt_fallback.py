"""
Tests for STT (Speech-to-Text) fallback service.

Verifies that the STT service:
- Tries providers in configured order
- Falls back to next provider on failure
- Supports configurable provider chain via STT_PROVIDERS env var
- Returns clear error when all providers fail
- Does not trigger fallback when primary succeeds
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.stt_service import (
    STTResult,
    STTService,
    get_stt_service,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stt_service():
    """Create a fresh STTService instance with default provider order."""
    return STTService(providers=["groq", "local_whisper"])


@pytest.fixture
def groq_only_service():
    """Create an STTService that only uses Groq."""
    return STTService(providers=["groq"])


@pytest.fixture
def local_only_service():
    """Create an STTService that only uses local whisper."""
    return STTService(providers=["local_whisper"])


@pytest.fixture
def audio_path(tmp_path):
    """Create a dummy audio file for testing."""
    p = tmp_path / "test_audio.ogg"
    p.write_bytes(b"fake audio data")
    return p


# ---------------------------------------------------------------------------
# STTResult dataclass tests
# ---------------------------------------------------------------------------


class TestSTTResult:
    def test_successful_result(self):
        result = STTResult(
            success=True,
            text="Hello world",
            provider="groq",
        )
        assert result.success is True
        assert result.text == "Hello world"
        assert result.provider == "groq"
        assert result.error is None

    def test_failed_result(self):
        result = STTResult(
            success=False,
            text="",
            provider="groq",
            error="API key missing",
        )
        assert result.success is False
        assert result.text == ""
        assert result.error == "API key missing"


# ---------------------------------------------------------------------------
# Provider ordering tests
# ---------------------------------------------------------------------------


class TestProviderOrdering:
    def test_default_providers(self, stt_service):
        """Default provider list should be groq first, local_whisper second."""
        assert stt_service.providers == ["groq", "local_whisper"]

    def test_custom_provider_order(self):
        """Provider order should be configurable."""
        service = STTService(providers=["local_whisper", "groq"])
        assert service.providers == ["local_whisper", "groq"]

    def test_single_provider(self, groq_only_service):
        """Should work with a single provider."""
        assert groq_only_service.providers == ["groq"]

    def test_unknown_provider_ignored(self):
        """Unknown providers should be filtered out."""
        service = STTService(providers=["groq", "nonexistent", "local_whisper"])
        assert service.providers == ["groq", "local_whisper"]

    def test_empty_providers_uses_defaults(self):
        """Empty provider list should fall back to defaults."""
        service = STTService(providers=[])
        assert len(service.providers) > 0

    def test_from_env_var(self):
        """Provider list should be parseable from STT_PROVIDERS env var."""
        with patch.dict(os.environ, {"STT_PROVIDERS": "local_whisper,groq"}):
            service = STTService.from_env()
            assert service.providers == ["local_whisper", "groq"]

    def test_from_env_var_missing_uses_default(self):
        """Missing STT_PROVIDERS env var should use default order."""
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("STT_PROVIDERS", None)
            with patch.dict(os.environ, env, clear=True):
                service = STTService.from_env()
                assert "groq" in service.providers


# ---------------------------------------------------------------------------
# Primary provider success (no fallback triggered)
# ---------------------------------------------------------------------------


class TestPrimaryProviderSuccess:
    def test_groq_success_no_fallback(self, stt_service, audio_path):
        """When Groq succeeds, local_whisper should NOT be called."""
        groq_result = STTResult(success=True, text="Hello from Groq", provider="groq")

        with (
            patch.object(
                stt_service, "_transcribe_groq", return_value=groq_result
            ) as mock_groq,
            patch.object(stt_service, "_transcribe_local_whisper") as mock_local,
        ):
            result = stt_service.transcribe(audio_path)

            assert result.success is True
            assert result.text == "Hello from Groq"
            assert result.provider == "groq"
            mock_groq.assert_called_once()
            mock_local.assert_not_called()

    def test_local_whisper_success_when_primary(self, local_only_service, audio_path):
        """When local_whisper is the only/primary provider, it should be called."""
        local_result = STTResult(
            success=True, text="Hello from local", provider="local_whisper"
        )

        with patch.object(
            local_only_service, "_transcribe_local_whisper", return_value=local_result
        ) as mock_local:
            result = local_only_service.transcribe(audio_path)

            assert result.success is True
            assert result.text == "Hello from local"
            assert result.provider == "local_whisper"
            mock_local.assert_called_once()


# ---------------------------------------------------------------------------
# Fallback on failure
# ---------------------------------------------------------------------------


class TestFallbackOnFailure:
    def test_groq_fails_falls_back_to_local(self, stt_service, audio_path):
        """When Groq fails, should fall back to local_whisper."""
        groq_fail = STTResult(
            success=False, text="", provider="groq", error="API timeout"
        )
        local_ok = STTResult(
            success=True, text="Fallback transcription", provider="local_whisper"
        )

        with (
            patch.object(
                stt_service, "_transcribe_groq", return_value=groq_fail
            ) as mock_groq,
            patch.object(
                stt_service, "_transcribe_local_whisper", return_value=local_ok
            ) as mock_local,
        ):
            result = stt_service.transcribe(audio_path)

            assert result.success is True
            assert result.text == "Fallback transcription"
            assert result.provider == "local_whisper"
            mock_groq.assert_called_once()
            mock_local.assert_called_once()

    def test_groq_exception_falls_back(self, stt_service, audio_path):
        """When Groq raises an exception, should catch and fall back."""
        local_ok = STTResult(success=True, text="Recovered", provider="local_whisper")

        with (
            patch.object(
                stt_service,
                "_transcribe_groq",
                side_effect=Exception("Connection refused"),
            ),
            patch.object(
                stt_service, "_transcribe_local_whisper", return_value=local_ok
            ),
        ):
            result = stt_service.transcribe(audio_path)

            assert result.success is True
            assert result.text == "Recovered"
            assert result.provider == "local_whisper"


# ---------------------------------------------------------------------------
# All providers fail
# ---------------------------------------------------------------------------


class TestAllProvidersFail:
    def test_all_fail_returns_error(self, stt_service, audio_path):
        """When all providers fail, should return a clear error result."""
        groq_fail = STTResult(
            success=False, text="", provider="groq", error="API error"
        )
        local_fail = STTResult(
            success=False, text="", provider="local_whisper", error="whisper not found"
        )

        with (
            patch.object(stt_service, "_transcribe_groq", return_value=groq_fail),
            patch.object(
                stt_service, "_transcribe_local_whisper", return_value=local_fail
            ),
        ):
            result = stt_service.transcribe(audio_path)

            assert result.success is False
            assert result.text == ""
            assert "all" in result.error.lower() or "failed" in result.error.lower()

    def test_single_provider_fail_returns_error(self, groq_only_service, audio_path):
        """When the only provider fails, should return clear error."""
        groq_fail = STTResult(
            success=False, text="", provider="groq", error="No API key"
        )

        with patch.object(
            groq_only_service, "_transcribe_groq", return_value=groq_fail
        ):
            result = groq_only_service.transcribe(audio_path)

            assert result.success is False
            assert "No API key" in result.error or "failed" in result.error.lower()


# ---------------------------------------------------------------------------
# Groq provider unit tests
# ---------------------------------------------------------------------------


class TestGroqProvider:
    def test_groq_success(self, stt_service, audio_path):
        """Groq provider should call run_python_script and parse JSON response."""
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.success = True
        mock_subprocess_result.stdout = json.dumps(
            {"success": True, "text": "Transcribed text"}
        )

        with (
            patch(
                "src.services.stt_service.run_python_script",
                return_value=mock_subprocess_result,
            ),
            patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}),
        ):
            result = stt_service._transcribe_groq(audio_path)

            assert result.success is True
            assert result.text == "Transcribed text"
            assert result.provider == "groq"

    def test_groq_missing_api_key(self, stt_service, audio_path):
        """Groq provider should fail gracefully when API key is missing."""
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("GROQ_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                result = stt_service._transcribe_groq(audio_path)

                assert result.success is False
                assert (
                    "api key" in result.error.lower() or "key" in result.error.lower()
                )

    def test_groq_api_error(self, stt_service, audio_path):
        """Groq provider should raise RetryableError on API errors."""
        from src.utils.retry import RetryableError

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.success = False
        mock_subprocess_result.stderr = "Rate limit exceeded"
        mock_subprocess_result.error = "Exit code: 1"

        with (
            patch(
                "src.services.stt_service.run_python_script",
                return_value=mock_subprocess_result,
            ),
            patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}),
        ):
            with pytest.raises(RetryableError):
                stt_service._transcribe_groq(audio_path)


# ---------------------------------------------------------------------------
# Local whisper provider unit tests
# ---------------------------------------------------------------------------


class TestLocalWhisperProvider:
    def test_local_whisper_success(self, stt_service, audio_path):
        """Local whisper should call whisper CLI via subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Transcribed by local whisper"

        with (
            patch("shutil.which", return_value="/usr/local/bin/whisper"),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = stt_service._transcribe_local_whisper(audio_path)

            assert result.success is True
            assert result.text == "Transcribed by local whisper"
            assert result.provider == "local_whisper"

    def test_local_whisper_not_installed(self, stt_service, audio_path):
        """Should fail gracefully if whisper CLI is not installed."""
        with patch("shutil.which", return_value=None):
            result = stt_service._transcribe_local_whisper(audio_path)

            assert result.success is False
            assert (
                "not found" in result.error.lower()
                or "not installed" in result.error.lower()
            )

    def test_local_whisper_timeout(self, stt_service, audio_path):
        """Should handle subprocess timeout gracefully."""
        with (
            patch("shutil.which", return_value="/usr/local/bin/whisper"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="whisper", timeout=120),
            ),
        ):
            result = stt_service._transcribe_local_whisper(audio_path)

            assert result.success is False
            assert "timeout" in result.error.lower()

    def test_local_whisper_prefers_mlx(self, stt_service, audio_path):
        """Should prefer mlx-whisper if available, then fall back to whisper CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "MLX transcription"

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: (
                "/opt/homebrew/bin/mlx_whisper" if cmd == "mlx_whisper" else None
            )
            with patch("subprocess.run", return_value=mock_result):
                result = stt_service._transcribe_local_whisper(audio_path)

                assert result.success is True


# ---------------------------------------------------------------------------
# Integration-style tests (with subprocess mocking)
# ---------------------------------------------------------------------------


class TestTranscribeEndToEnd:
    def test_full_fallback_chain(self, audio_path):
        """End-to-end: Groq fails, local_whisper succeeds."""
        service = STTService(providers=["groq", "local_whisper"])

        groq_fail = STTResult(
            success=False, text="", provider="groq", error="503 Service Unavailable"
        )
        local_ok = STTResult(
            success=True, text="Local transcription", provider="local_whisper"
        )

        with (
            patch.object(service, "_transcribe_groq", return_value=groq_fail),
            patch.object(service, "_transcribe_local_whisper", return_value=local_ok),
        ):
            result = service.transcribe(audio_path)

            assert result.success is True
            assert result.text == "Local transcription"

    def test_file_not_found(self, stt_service):
        """Should return error if audio file does not exist."""
        result = stt_service.transcribe(Path("/nonexistent/audio.ogg"))

        assert result.success is False
        assert "not found" in result.error.lower() or "exist" in result.error.lower()

    def test_language_passed_through(self, stt_service, audio_path):
        """Language parameter should be passed to providers."""
        groq_result = STTResult(success=True, text="Bonjour", provider="groq")

        with patch.object(
            stt_service, "_transcribe_groq", return_value=groq_result
        ) as mock_groq:
            stt_service.transcribe(audio_path, language="fr")

            mock_groq.assert_called_once_with(
                audio_path, "whisper-large-v3-turbo", "fr"
            )


# ---------------------------------------------------------------------------
# get_stt_service singleton
# ---------------------------------------------------------------------------


class TestGetSTTService:
    def _setup_container(self):
        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

    def test_returns_stt_service_instance(self):
        """get_stt_service() should return an STTService instance."""
        self._setup_container()
        with patch.dict(os.environ, {}, clear=False):
            service = get_stt_service()
            assert isinstance(service, STTService)

    def test_singleton_returns_same_instance(self):
        """get_stt_service() should return the same instance on subsequent calls."""
        self._setup_container()
        s1 = get_stt_service()
        s2 = get_stt_service()
        assert s1 is s2
