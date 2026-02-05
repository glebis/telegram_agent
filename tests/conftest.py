import asyncio
import logging
import logging.handlers
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Set test environment variables
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-secret"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _strip_file_handlers():
    """Remove file handlers from root logger so tests never write to logs/app.log."""
    root = logging.getLogger()
    saved = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    for h in saved:
        root.removeHandler(h)
    yield
    # Restore any that were removed (and strip any new ones tests may have added)
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
    for h in saved:
        root.addHandler(h)


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir) / "data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "raw").mkdir(exist_ok=True)
        (data_dir / "img").mkdir(exist_ok=True)
        yield data_dir


@pytest.fixture
def mock_bot():
    """Create a mock Telegram bot for testing"""
    from telegram import Bot

    return Mock(spec=Bot)


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service for testing"""
    from src.services.llm_service import LLMService

    mock_service = Mock(spec=LLMService)
    mock_service.analyze_image.return_value = {
        "summary": "Mock image analysis",
        "description": "Mock description",
        "confidence": 0.95,
    }
    return mock_service


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service for testing"""
    from src.services.embedding_service import EmbeddingService

    mock_service = Mock(spec=EmbeddingService)
    mock_service.generate_embedding.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
    return mock_service


@pytest.fixture
def mock_vector_db():
    """Create a mock vector database for testing"""
    from src.core.vector_db import VectorDB

    mock_db = Mock(spec=VectorDB)
    mock_db.search_similar.return_value = []
    mock_db.add_image.return_value = None
    return mock_db


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment before each test"""
    # Patch external services to prevent real API calls
    with (
        patch("src.services.llm_service.litellm") as mock_litellm,
        patch("src.services.embedding_service.SentenceTransformer") as mock_st,
        patch("src.core.vector_db.sqlite3") as mock_sqlite,
    ):

        # Configure mocks
        mock_litellm.acompletion.return_value = Mock(
            choices=[Mock(message=Mock(content='{"summary": "test"}'))]
        )

        yield {
            "litellm": mock_litellm,
            "sentence_transformer": mock_st,
            "sqlite": mock_sqlite,
        }


class AsyncMock:
    """Helper class for async mocking"""

    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.call_count = 0
        self.call_args_list = []

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.call_args_list.append((args, kwargs))

        if self.side_effect:
            if callable(self.side_effect):
                return await self.side_effect(*args, **kwargs)
            elif isinstance(self.side_effect, list):
                if self.call_count <= len(self.side_effect):
                    return self.side_effect[self.call_count - 1]
            else:
                raise self.side_effect

        return self.return_value

    def assert_called_once(self):
        assert self.call_count == 1

    def assert_called_with(self, *args, **kwargs):
        assert (args, kwargs) in self.call_args_list

    def assert_not_called(self):
        assert self.call_count == 0


# Make AsyncMock available globally for tests
pytest.AsyncMock = AsyncMock
