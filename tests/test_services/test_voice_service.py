"""
Tests for the Voice Service.

Tests cover:
- VoiceService initialization
- Configuration loading (file and default)
- Audio transcription via Groq API (mocked)
- Intent detection from transcribed text
- Obsidian formatting (task and log entries)
- Full voice message processing workflow
- Global instance management
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest
import yaml

from src.services.voice_service import (
    VoiceService,
    get_voice_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Sample routing configuration."""
    return {
        "voice": {
            "service": "groq_whisper",
            "intents": {
                "task": {
                    "keywords": ["todo", "task", "remind me", "need to"],
                    "destination": "daily",
                    "format": "task",
                },
                "note": {
                    "keywords": ["note", "remember", "idea"],
                    "destination": "inbox",
                    "format": "note",
                },
                "quick": {
                    "keywords": [],
                    "destination": "daily",
                    "section": "log",
                },
            },
        }
    }


@pytest.fixture
def voice_service_with_key(sample_config):
    """Create VoiceService with API key and sample config."""
    with patch.dict("os.environ", {"GROQ_API_KEY": "test-api-key"}):
        with patch.object(VoiceService, "_load_config", return_value=sample_config):
            service = VoiceService()
            return service


@pytest.fixture
def voice_service_no_key(sample_config):
    """Create VoiceService without API key."""
    with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=True):
        with patch.object(VoiceService, "_load_config", return_value=sample_config):
            service = VoiceService()
            service.api_key = None  # Ensure it's None
            return service


@pytest.fixture
def temp_audio_file():
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(b"fake audio data")
        return f.name


# =============================================================================
# Initialization Tests
# =============================================================================


class TestVoiceServiceInit:
    """Tests for VoiceService initialization."""

    def test_init_with_api_key(self, sample_config):
        """Test initialization with API key set."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key-123"}):
            with patch.object(VoiceService, "_load_config", return_value=sample_config):
                service = VoiceService()

                assert service.api_key == "test-key-123"
                assert service.base_url == "https://api.groq.com/openai/v1"

    def test_init_without_api_key(self, sample_config):
        """Test initialization without API key."""
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(VoiceService, "_load_config", return_value=sample_config):
                # Remove GROQ_API_KEY if it exists
                import os
                original = os.environ.pop("GROQ_API_KEY", None)
                try:
                    service = VoiceService()
                    assert service.api_key is None
                finally:
                    if original:
                        os.environ["GROQ_API_KEY"] = original

    def test_init_loads_config(self):
        """Test that initialization loads config."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config") as mock_load:
                mock_load.return_value = {"voice": {}}
                service = VoiceService()

                mock_load.assert_called_once()
                assert service.config == {"voice": {}}


# =============================================================================
# Config Loading Tests
# =============================================================================


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_config_from_file(self, sample_config):
        """Test loading config from YAML file."""
        yaml_content = yaml.dump(sample_config)

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                with patch("pathlib.Path.exists", return_value=True):
                    service = VoiceService()

                    assert "voice" in service.config
                    assert "intents" in service.config.get("voice", {})

    def test_load_config_file_not_found(self):
        """Test fallback to default config when file not found."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch("builtins.open", side_effect=FileNotFoundError()):
                service = VoiceService()

                # Should use default config
                assert "voice" in service.config
                assert "intents" in service.config["voice"]

    def test_load_config_invalid_yaml(self):
        """Test fallback when YAML is invalid."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch("builtins.open", mock_open(read_data="invalid: yaml: content:")):
                with patch("yaml.safe_load", side_effect=yaml.YAMLError("Parse error")):
                    service = VoiceService()

                    # Should use default config
                    assert "voice" in service.config

    def test_default_config_structure(self, sample_config):
        """Test default config has expected structure."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config") as mock_load:
                # Make it call the real _default_config
                service = VoiceService.__new__(VoiceService)
                default = service._default_config()

                assert "voice" in default
                assert "service" in default["voice"]
                assert "intents" in default["voice"]
                assert "task" in default["voice"]["intents"]
                assert "note" in default["voice"]["intents"]
                assert "quick" in default["voice"]["intents"]

    def test_default_config_task_keywords(self):
        """Test default task intent has expected keywords."""
        service = VoiceService.__new__(VoiceService)
        default = service._default_config()

        task_keywords = default["voice"]["intents"]["task"]["keywords"]
        assert "todo" in task_keywords
        assert "task" in task_keywords
        assert "remind" in task_keywords


# =============================================================================
# Transcription Tests
# =============================================================================


class TestTranscription:
    """Tests for audio transcription."""

    @pytest.mark.asyncio
    async def test_transcribe_success(self, voice_service_with_key, temp_audio_file):
        """Test successful transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "This is the transcribed text."}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.transcribe(temp_audio_file)

            assert success is True
            assert result["text"] == "This is the transcribed text."

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self, voice_service_no_key, temp_audio_file):
        """Test transcription fails without API key."""
        success, result = await voice_service_no_key.transcribe(temp_audio_file)

        assert success is False
        assert "error" in result
        assert "API key" in result["error"]

    @pytest.mark.asyncio
    async def test_transcribe_api_error(self, voice_service_with_key, temp_audio_file):
        """Test handling of API error response."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.transcribe(temp_audio_file)

            assert success is False
            assert "error" in result
            assert "400" in result["error"]

    @pytest.mark.asyncio
    async def test_transcribe_network_error(self, voice_service_with_key, temp_audio_file):
        """Test handling of network error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = Exception("Network error")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.transcribe(temp_audio_file)

            assert success is False
            assert "error" in result
            assert "Network error" in result["error"]

    @pytest.mark.asyncio
    async def test_transcribe_empty_text(self, voice_service_with_key, temp_audio_file):
        """Test transcription with empty result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "  "}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.transcribe(temp_audio_file)

            assert success is True
            assert result["text"] == ""  # Stripped whitespace

    @pytest.mark.asyncio
    async def test_transcribe_api_500_error(self, voice_service_with_key, temp_audio_file):
        """Test handling of server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.transcribe(temp_audio_file)

            assert success is False
            assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_transcribe_sends_correct_request(self, voice_service_with_key, temp_audio_file):
        """Test that transcription sends correct API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Test"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            await voice_service_with_key.transcribe(temp_audio_file)

            # Verify the API call
            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args

            # Check URL
            assert "audio/transcriptions" in call_args[0][0]

            # Check headers
            assert "Authorization" in call_args[1]["headers"]
            assert "Bearer" in call_args[1]["headers"]["Authorization"]

            # Check data
            assert call_args[1]["data"]["model"] == "whisper-large-v3-turbo"


# =============================================================================
# Intent Detection Tests
# =============================================================================


class TestIntentDetection:
    """Tests for intent detection."""

    def test_detect_task_intent(self, voice_service_with_key):
        """Test detection of task intent."""
        result = voice_service_with_key.detect_intent("I need to buy groceries")

        assert result["intent"] == "task"
        assert result["destination"] == "daily"
        assert result["format"] == "task"
        assert result["matched_keyword"] == "need to"

    def test_detect_task_intent_todo(self, voice_service_with_key):
        """Test detection of task intent with 'todo' keyword."""
        result = voice_service_with_key.detect_intent("Add this to my todo list")

        assert result["intent"] == "task"
        assert result["matched_keyword"] == "todo"

    def test_detect_note_intent(self, voice_service_with_key):
        """Test detection of note intent."""
        result = voice_service_with_key.detect_intent("Note to self about the meeting")

        assert result["intent"] == "note"
        assert result["destination"] == "inbox"
        assert result["matched_keyword"] == "note"

    def test_detect_note_intent_idea(self, voice_service_with_key):
        """Test detection of note intent with 'idea' keyword."""
        result = voice_service_with_key.detect_intent("I have an idea for the project")

        assert result["intent"] == "note"
        assert result["matched_keyword"] == "idea"

    def test_detect_quick_intent_default(self, voice_service_with_key):
        """Test default to quick intent when no keywords match."""
        result = voice_service_with_key.detect_intent("Just a random message")

        assert result["intent"] == "quick"
        assert result["destination"] == "daily"
        assert result["section"] == "log"

    def test_detect_intent_case_insensitive(self, voice_service_with_key):
        """Test that intent detection is case insensitive."""
        result = voice_service_with_key.detect_intent("I NEED TO do this NOW")

        assert result["intent"] == "task"
        assert result["matched_keyword"] == "need to"

    def test_detect_intent_first_match_wins(self, voice_service_with_key):
        """Test that first matching keyword determines intent."""
        # "task" and "note" both in text, task keywords checked first
        result = voice_service_with_key.detect_intent("Add this task as a note")

        # Depends on order in config - task is first
        assert result["intent"] == "task"

    def test_detect_intent_empty_text(self, voice_service_with_key):
        """Test intent detection with empty text."""
        result = voice_service_with_key.detect_intent("")

        assert result["intent"] == "quick"

    def test_detect_intent_whitespace_only(self, voice_service_with_key):
        """Test intent detection with whitespace only."""
        result = voice_service_with_key.detect_intent("   ")

        assert result["intent"] == "quick"

    def test_detect_intent_with_remind_me(self, voice_service_with_key):
        """Test detection with 'remind me' keyword."""
        result = voice_service_with_key.detect_intent("Remind me to call mom")

        assert result["intent"] == "task"
        assert result["matched_keyword"] == "remind me"


# =============================================================================
# Obsidian Formatting Tests
# =============================================================================


class TestObsidianFormatting:
    """Tests for Obsidian markdown formatting."""

    def test_format_as_task(self, voice_service_with_key):
        """Test formatting text as task."""
        intent_info = {"format": "task"}
        result = voice_service_with_key.format_for_obsidian("Buy groceries", intent_info)

        assert result == "- [ ] Buy groceries"

    def test_format_as_log_entry(self, voice_service_with_key):
        """Test formatting text as log entry."""
        intent_info = {"format": None}
        timestamp = datetime(2024, 1, 15, 14, 30)

        result = voice_service_with_key.format_for_obsidian(
            "Meeting with team", intent_info, timestamp
        )

        assert result == "- 14:30 Meeting with team"

    def test_format_uses_current_time_when_none(self, voice_service_with_key):
        """Test that format uses current time when not provided."""
        intent_info = {"format": None}

        with patch("src.services.voice_service.datetime") as mock_datetime:
            mock_now = datetime(2024, 6, 20, 9, 15)
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            result = voice_service_with_key.format_for_obsidian("Test message", intent_info)

            assert "09:15" in result

    def test_format_task_with_special_characters(self, voice_service_with_key):
        """Test formatting task with special characters."""
        intent_info = {"format": "task"}
        result = voice_service_with_key.format_for_obsidian(
            "Fix bug #123 & update docs", intent_info
        )

        assert result == "- [ ] Fix bug #123 & update docs"

    def test_format_log_with_multiline_text(self, voice_service_with_key):
        """Test formatting log entry with multiline text."""
        intent_info = {"format": None}
        timestamp = datetime(2024, 1, 15, 10, 0)

        result = voice_service_with_key.format_for_obsidian(
            "Line one\nLine two", intent_info, timestamp
        )

        assert result == "- 10:00 Line one\nLine two"

    def test_format_empty_text(self, voice_service_with_key):
        """Test formatting empty text."""
        intent_info = {"format": "task"}
        result = voice_service_with_key.format_for_obsidian("", intent_info)

        assert result == "- [ ] "


# =============================================================================
# Process Voice Message Tests
# =============================================================================


class TestProcessVoiceMessage:
    """Tests for full voice message processing workflow."""

    @pytest.mark.asyncio
    async def test_process_success(self, voice_service_with_key, temp_audio_file):
        """Test successful voice message processing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "I need to call the doctor"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.process_voice_message(
                temp_audio_file
            )

            assert success is True
            assert result["text"] == "I need to call the doctor"
            assert result["intent"]["intent"] == "task"
            assert "formatted_text" in result
            assert result["formatted_text"] == "- [ ] I need to call the doctor"
            assert result["destination"] == "daily"

    @pytest.mark.asyncio
    async def test_process_transcription_failure(self, voice_service_no_key, temp_audio_file):
        """Test processing when transcription fails."""
        success, result = await voice_service_no_key.process_voice_message(temp_audio_file)

        assert success is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_note_intent(self, voice_service_with_key, temp_audio_file):
        """Test processing message with note intent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Note about the project deadline"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.process_voice_message(
                temp_audio_file
            )

            assert success is True
            assert result["intent"]["intent"] == "note"
            assert result["destination"] == "inbox"

    @pytest.mark.asyncio
    async def test_process_quick_intent(self, voice_service_with_key, temp_audio_file):
        """Test processing message with quick/default intent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Just a random thought"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.process_voice_message(
                temp_audio_file
            )

            assert success is True
            assert result["intent"]["intent"] == "quick"
            # Formatted as log entry, not task
            assert "- [ ]" not in result["formatted_text"]


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_voice_service_creates_instance(self):
        """Test that get_voice_service creates instance."""
        import src.services.voice_service as vs
        vs._voice_service = None

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config", return_value={}):
                service = get_voice_service()

                assert service is not None
                assert isinstance(service, VoiceService)

    def test_get_voice_service_returns_same_instance(self):
        """Test that get_voice_service returns same instance."""
        import src.services.voice_service as vs
        vs._voice_service = None

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config", return_value={}):
                service1 = get_voice_service()
                service2 = get_voice_service()

                assert service1 is service2


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_intent_detection_with_missing_config_section(self):
        """Test intent detection when config section is missing."""
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config", return_value={}):
                service = VoiceService()
                result = service.detect_intent("Some text")

                # Should default gracefully
                assert result["intent"] == "quick"

    def test_intent_detection_with_empty_intents(self):
        """Test intent detection with empty intents config."""
        config = {"voice": {"intents": {}}}

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch.object(VoiceService, "_load_config", return_value=config):
                service = VoiceService()
                result = service.detect_intent("Todo something")

                # Should default to quick
                assert result["intent"] == "quick"

    def test_format_with_missing_format_key(self, voice_service_with_key):
        """Test formatting when format key is missing."""
        intent_info = {}  # No format key
        timestamp = datetime(2024, 1, 1, 12, 0)

        result = voice_service_with_key.format_for_obsidian("Test", intent_info, timestamp)

        # Should default to log format
        assert "12:00" in result

    def test_intent_detection_preserves_original_text(self, voice_service_with_key):
        """Test that intent detection doesn't modify original text."""
        original = "I NEED TO do this"
        voice_service_with_key.detect_intent(original)

        # Original should be unchanged (we only use lower for matching)
        assert original == "I NEED TO do this"

    @pytest.mark.asyncio
    async def test_transcribe_with_file_read_error(self, voice_service_with_key):
        """Test transcription when file cannot be read."""
        with patch("builtins.open", side_effect=IOError("Cannot read file")):
            success, result = await voice_service_with_key.transcribe("/nonexistent/file.ogg")

            assert success is False
            assert "error" in result

    def test_default_config_intents_have_required_fields(self):
        """Test that default config intents have all required fields."""
        service = VoiceService.__new__(VoiceService)
        default = service._default_config()

        for intent_name, intent_config in default["voice"]["intents"].items():
            assert "keywords" in intent_config
            assert "destination" in intent_config
            assert isinstance(intent_config["keywords"], list)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple operations."""

    @pytest.mark.asyncio
    async def test_full_workflow_task(self, voice_service_with_key, temp_audio_file):
        """Test complete workflow for task creation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Remind me to submit the report"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.process_voice_message(
                temp_audio_file
            )

            assert success is True
            assert result["text"] == "Remind me to submit the report"
            assert result["intent"]["intent"] == "task"
            assert result["intent"]["matched_keyword"] == "remind me"
            assert result["formatted_text"] == "- [ ] Remind me to submit the report"
            assert result["destination"] == "daily"

    @pytest.mark.asyncio
    async def test_full_workflow_note(self, voice_service_with_key, temp_audio_file):
        """Test complete workflow for note creation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Remember the API key format"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            success, result = await voice_service_with_key.process_voice_message(
                temp_audio_file
            )

            assert success is True
            assert result["intent"]["intent"] == "note"
            assert result["destination"] == "inbox"

    def test_config_to_intent_to_format_chain(self, voice_service_with_key):
        """Test the chain from config to intent to formatted output."""
        # Detect intent
        intent = voice_service_with_key.detect_intent("I need to finish the presentation")

        assert intent["intent"] == "task"
        assert intent["format"] == "task"

        # Format based on intent
        formatted = voice_service_with_key.format_for_obsidian(
            "I need to finish the presentation", intent
        )

        assert formatted == "- [ ] I need to finish the presentation"
