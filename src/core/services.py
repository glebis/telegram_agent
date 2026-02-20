"""
Service Registry - Central service configuration and registration.

This module wires up all application services with their dependencies.
Services are registered lazily and instantiated on first access.

Usage:
    from src.core.services import setup_services, get_service

    # At startup
    setup_services()

    # Get a service anywhere
    llm = get_service("llm")
"""

import logging
from typing import Any, TypeVar

from .container import get_container, reset_container

logger = logging.getLogger(__name__)

T = TypeVar("T")


def setup_services() -> None:
    """
    Register all application services in the container.

    Call this once at application startup before using any services.
    Services are registered lazily - they won't be instantiated until
    first accessed via get_service().
    """
    container = get_container()

    # ========================================================================
    # Core Services (no dependencies)
    # ========================================================================

    # Settings - configuration management
    def create_settings(c):
        from .config import get_settings

        return get_settings()

    container.register("settings", create_settings)

    # ========================================================================
    # Database Layer
    # ========================================================================

    # Note: Database is async, handled separately via init_database()
    # The session factory is accessed via get_db_session() context manager

    # ========================================================================
    # External API Services
    # ========================================================================

    # LLM Service - OpenAI/LiteLLM integration
    def create_llm_service(c):
        from ..services.llm_service import LLMService

        return LLMService()

    container.register("llm", create_llm_service)

    # Embedding Service - vector embeddings
    def create_embedding_service(c):
        from ..services.embedding_service import EmbeddingService

        return EmbeddingService()

    container.register("embedding", create_embedding_service)

    # Voice Service - audio transcription
    def create_voice_service(c):
        from ..services.voice_service import VoiceService

        return VoiceService()

    container.register("voice", create_voice_service)

    # ========================================================================
    # Business Logic Services
    # ========================================================================

    # Image Service - image processing pipeline
    def create_image_service(c):
        from ..services.image_service import ImageService

        return ImageService()

    container.register("image", create_image_service)

    # Image Classifier - image categorization
    def create_classifier(c):
        from ..services.image_classifier import ImageClassifier

        return ImageClassifier()

    container.register("classifier", create_classifier)

    # Link Service - URL processing
    def create_link_service(c):
        from ..services.link_service import LinkService

        return LinkService()

    container.register("link", create_link_service)

    # Gallery Service - image gallery generation
    def create_gallery_service(c):
        from ..services.gallery_service import GalleryService

        return GalleryService()

    container.register("gallery", create_gallery_service)

    # Similarity Service - vector similarity search
    def create_similarity_service(c):
        from ..services.similarity_service import SimilarityService

        return SimilarityService()

    container.register("similarity", create_similarity_service)

    # Cache Service - in-memory caching
    def create_cache_service(c):
        from ..services.cache_service import CacheService

        return CacheService()

    container.register("cache", create_cache_service)

    # ========================================================================
    # Telegram Bot Services
    # ========================================================================

    # Message Buffer - combines multi-part messages
    # Now properly wired to use config values
    def create_buffer_service(c):
        from ..services.message_buffer import MessageBufferService
        from .config import get_settings

        settings = get_settings()
        return MessageBufferService(
            buffer_timeout=settings.buffer_timeout,
            max_messages=settings.max_buffer_messages,
            max_wait=settings.max_buffer_wait,
            max_buffer_size=settings.max_buffer_size,
        )

    container.register("message_buffer", create_buffer_service)

    # Reply Context - tracks message context for replies
    def create_reply_context(c):
        from ..services.reply_context import ReplyContextService

        return ReplyContextService()

    container.register("reply_context", create_reply_context)

    # Routing Memory - remembers user routing preferences
    def create_routing_memory(c):
        from ..services.routing_memory import RoutingMemory

        return RoutingMemory()

    container.register("routing_memory", create_routing_memory)

    # Claude Code Service - Claude SDK integration
    def create_claude_service(c):
        from ..services.claude_code_service import ClaudeCodeService

        return ClaudeCodeService()

    container.register("claude", create_claude_service)

    # Keyboard Utils - inline keyboard builders
    def create_keyboard_utils(c):
        from ..bot.keyboard_utils import KeyboardUtils

        return KeyboardUtils()

    container.register("keyboard", create_keyboard_utils)

    # Callback Data Manager - manages callback data storage
    def create_callback_manager(c):
        from ..bot.callback_data_manager import CallbackDataManager

        return CallbackDataManager()

    container.register("callback_manager", create_callback_manager)

    # Combined Message Processor - routes buffered messages
    def create_combined_processor(c):
        from ..bot.combined_processor import CombinedMessageProcessor

        return CombinedMessageProcessor()

    container.register("combined_processor", create_combined_processor)

    # Keyboard Service - per-user reply keyboards
    def create_keyboard_service(c):
        from ..services.keyboard_service import KeyboardService

        return KeyboardService()

    container.register("keyboard_service", create_keyboard_service)

    # ========================================================================
    # Vector Database
    # ========================================================================

    def create_vector_db(c):
        from .vector_db import VectorDatabase

        return VectorDatabase(embedding_service=c.get("embedding"))

    container.register("vector_db", create_vector_db)

    # ========================================================================
    # Services migrated from global getters
    # ========================================================================

    # TTS Service - text-to-speech synthesis
    def create_tts_service(c):
        from ..services.tts_service import TTSService

        return TTSService.from_env()

    container.register("tts", create_tts_service)

    # STT Service - speech-to-text transcription
    def create_stt_service(c):
        from ..services.stt_service import STTService

        return STTService.from_env()

    container.register("stt", create_stt_service)

    # Poll Service - poll management
    def create_poll_service(c):
        from ..services.poll_service import PollService

        return PollService()

    container.register("poll", create_poll_service)

    # Polling Service - message polling
    def create_polling_service(c):
        from ..services.polling_service import PollingService

        return PollingService()

    container.register("polling", create_polling_service)

    # Heartbeat Service - system health monitoring
    def create_heartbeat_service(c):
        from ..services.heartbeat_service import HeartbeatService

        return HeartbeatService()

    container.register("heartbeat", create_heartbeat_service)

    # Todo Service - task management
    def create_todo_service(c):
        from ..services.todo_service import TodoService

        return TodoService()

    container.register("todo", create_todo_service)

    # Collect Service - message collection
    def create_collect_service(c):
        from ..services.collect_service import CollectService

        return CollectService()

    container.register("collect", create_collect_service)

    # Trail Review Service - conversation trail review
    def create_trail_review_service(c):
        from ..services.trail_review_service import TrailReviewService

        return TrailReviewService()

    container.register("trail_review", create_trail_review_service)

    # Design Skills Service - design skill prompts
    def create_design_skills_service(c):
        from ..services.design_skills_service import DesignSkillsService

        return DesignSkillsService()

    container.register("design_skills", create_design_skills_service)

    # OpenCode Service - OpenCode integration
    def create_opencode_service(c):
        from ..services.opencode_service import OpenCodeService

        return OpenCodeService()

    container.register("opencode", create_opencode_service)

    # Task Ledger Service - task tracking
    def create_task_ledger_service(c):
        from ..services.task_ledger_service import TaskLedgerService

        return TaskLedgerService()

    container.register("task_ledger", create_task_ledger_service)

    # Telethon Service - Telegram MTProto client
    def create_telethon_service(c):
        from ..services.telethon_service import TelethonService

        return TelethonService()

    container.register("telethon", create_telethon_service)

    # Voice Response Service - voice response generation
    def create_voice_response_service(c):
        from ..services.voice_response_service import VoiceResponseService

        return VoiceResponseService()

    container.register("voice_response", create_voice_response_service)

    # Job Queue Service - persistent job queue
    def create_job_queue_service(c):
        from ..services.job_queue_service import JobQueueService

        return JobQueueService()

    container.register("job_queue", create_job_queue_service)

    logger.info("All services registered in container")


def get_service(name: str) -> Any:
    """
    Get a service by name from the container.

    Args:
        name: Service name (e.g., "llm", "image", "claude")

    Returns:
        The service instance

    Raises:
        KeyError: If service is not registered
    """
    return get_container().get(name)


def reset_services() -> None:
    """
    Reset all services (useful for testing).

    This clears the container and re-registers all services.
    """
    reset_container()
    setup_services()
    logger.info("Services reset")


# Service name constants for type safety
class Services:
    """Constants for service names."""

    SETTINGS = "settings"
    LLM = "llm"
    EMBEDDING = "embedding"
    VOICE = "voice"
    IMAGE = "image"
    CLASSIFIER = "classifier"
    LINK = "link"
    GALLERY = "gallery"
    SIMILARITY = "similarity"
    CACHE = "cache"
    MESSAGE_BUFFER = "message_buffer"
    REPLY_CONTEXT = "reply_context"
    ROUTING_MEMORY = "routing_memory"
    CLAUDE = "claude"
    KEYBOARD = "keyboard"
    CALLBACK_MANAGER = "callback_manager"
    COMBINED_PROCESSOR = "combined_processor"
    KEYBOARD_SERVICE = "keyboard_service"
    VECTOR_DB = "vector_db"
    TTS = "tts"
    STT = "stt"
    POLL = "poll"
    POLLING = "polling"
    HEARTBEAT = "heartbeat"
    TODO = "todo"
    COLLECT = "collect"
    TRAIL_REVIEW = "trail_review"
    DESIGN_SKILLS = "design_skills"
    OPENCODE = "opencode"
    TASK_LEDGER = "task_ledger"
    TELETHON = "telethon"
    VOICE_RESPONSE = "voice_response"
    JOB_QUEUE = "job_queue"
