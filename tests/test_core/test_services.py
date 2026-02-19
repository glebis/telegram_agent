"""
Tests for the service registry.
"""

import pytest


class TestServiceRegistry:
    """Test the service registry module."""

    def test_setup_services_registers_all(self):
        """setup_services registers all expected services."""
        from src.core.container import get_container, reset_container
        from src.core.services import Services, setup_services

        reset_container()
        setup_services()
        container = get_container()

        # Check all service constants are registered
        expected_services = [
            Services.SETTINGS,
            Services.LLM,
            Services.EMBEDDING,
            Services.VOICE,
            Services.IMAGE,
            Services.CLASSIFIER,
            Services.LINK,
            Services.GALLERY,
            Services.SIMILARITY,
            Services.CACHE,
            Services.MESSAGE_BUFFER,
            Services.REPLY_CONTEXT,
            Services.ROUTING_MEMORY,
            Services.CLAUDE,
            Services.KEYBOARD,
            Services.CALLBACK_MANAGER,
            Services.COMBINED_PROCESSOR,
            Services.KEYBOARD_SERVICE,
            Services.VECTOR_DB,
            # New services migrated from global getters
            Services.TTS,
            Services.STT,
            Services.POLL,
            Services.POLLING,
            Services.HEARTBEAT,
            Services.TODO,
            Services.COLLECT,
            Services.TRAIL_REVIEW,
            Services.DESIGN_SKILLS,
            Services.OPENCODE,
            Services.TASK_LEDGER,
            Services.TELETHON,
            Services.VOICE_RESPONSE,
            Services.JOB_QUEUE,
        ]

        for service_name in expected_services:
            assert container.has(
                service_name
            ), f"Service '{service_name}' not registered"

    def test_get_service_returns_instance(self):
        """get_service returns a service instance."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        settings = get_service(Services.SETTINGS)
        assert settings is not None

    def test_services_are_singletons(self):
        """Services are singletons - same instance returned."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        s1 = get_service(Services.CACHE)
        s2 = get_service(Services.CACHE)

        assert s1 is s2

    def test_reset_services_creates_new_instances(self):
        """reset_services creates fresh instances."""
        from src.core.container import reset_container
        from src.core.services import (
            Services,
            get_service,
            reset_services,
            setup_services,
        )

        reset_container()
        setup_services()

        s1 = get_service(Services.CACHE)

        reset_services()

        s2 = get_service(Services.CACHE)

        assert s1 is not s2

    def test_get_service_unknown_raises(self):
        """get_service raises KeyError for unknown service."""
        from src.core.container import reset_container
        from src.core.services import get_service, setup_services

        reset_container()
        setup_services()

        with pytest.raises(KeyError):
            get_service("nonexistent_service")


class TestServiceIntegration:
    """Integration tests for specific services."""

    def test_llm_service_instantiates(self):
        """LLM service can be instantiated."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        llm = get_service(Services.LLM)
        assert llm is not None
        assert hasattr(llm, "analyze_image")

    def test_cache_service_instantiates(self):
        """Cache service can be instantiated."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        cache = get_service(Services.CACHE)
        assert cache is not None
        # CacheService uses async methods for analysis caching
        assert hasattr(cache, "get_cached_analysis")
        assert hasattr(cache, "store_analysis")

    def test_keyboard_utils_instantiates(self):
        """Keyboard utils can be instantiated."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        keyboard = get_service(Services.KEYBOARD)
        assert keyboard is not None
        assert hasattr(keyboard, "create_reanalysis_keyboard")


class TestNewServiceRegistrations:
    """Tests for services migrated from global getters to the container."""

    def test_todo_service_via_container(self):
        """TodoService resolves from container."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services
        from src.services.todo_service import TodoService

        reset_container()
        setup_services()

        svc = get_service(Services.TODO)
        assert isinstance(svc, TodoService)

    def test_poll_service_via_container(self):
        """PollService resolves from container."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services
        from src.services.poll_service import PollService

        reset_container()
        setup_services()

        svc = get_service(Services.POLL)
        assert isinstance(svc, PollService)

    def test_heartbeat_service_via_container(self):
        """HeartbeatService resolves from container."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services
        from src.services.heartbeat_service import HeartbeatService

        reset_container()
        setup_services()

        svc = get_service(Services.HEARTBEAT)
        assert isinstance(svc, HeartbeatService)

    def test_collect_service_via_container(self):
        """CollectService resolves from container."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services
        from src.services.collect_service import CollectService

        reset_container()
        setup_services()

        svc = get_service(Services.COLLECT)
        assert isinstance(svc, CollectService)

    def test_design_skills_service_via_container(self):
        """DesignSkillsService resolves from container."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services
        from src.services.design_skills_service import DesignSkillsService

        reset_container()
        setup_services()

        svc = get_service(Services.DESIGN_SKILLS)
        assert isinstance(svc, DesignSkillsService)

    def test_container_singleton_matches_global_getter(self):
        """Container returns same type as the old global getter would."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        # Container singletons: two calls return same object
        svc1 = get_service(Services.TODO)
        svc2 = get_service(Services.TODO)
        assert svc1 is svc2

    def test_all_new_services_are_singletons(self):
        """All newly registered services behave as singletons."""
        from src.core.container import reset_container
        from src.core.services import Services, get_service, setup_services

        reset_container()
        setup_services()

        new_services = [
            Services.POLL,
            Services.TODO,
            Services.HEARTBEAT,
            Services.COLLECT,
            Services.DESIGN_SKILLS,
            Services.OPENCODE,
            Services.TASK_LEDGER,
        ]

        for name in new_services:
            s1 = get_service(name)
            s2 = get_service(name)
            assert s1 is s2, f"Service '{name}' is not a singleton"


class TestGettersDelegateToContainer:
    """Global get_*_service() getters must delegate to the DI container."""

    def _setup(self):
        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

    def test_get_llm_service_delegates(self):
        """get_llm_service() returns the container's LLM instance."""
        self._setup()
        from src.core.services import Services, get_service
        from src.services.llm_service import get_llm_service

        assert get_llm_service() is get_service(Services.LLM)

    def test_get_claude_code_service_delegates(self):
        """get_claude_code_service() returns the container's Claude instance."""
        self._setup()
        from src.core.services import Services, get_service
        from src.services.claude_code_service import get_claude_code_service

        assert get_claude_code_service() is get_service(Services.CLAUDE)

    def test_get_reply_context_service_delegates(self):
        """get_reply_context_service() returns the container's instance."""
        self._setup()
        from src.core.services import Services, get_service
        from src.services.reply_context import get_reply_context_service

        assert get_reply_context_service() is get_service(Services.REPLY_CONTEXT)

    def test_get_keyboard_service_delegates(self):
        """get_keyboard_service() returns the container's instance."""
        self._setup()
        from src.core.services import Services, get_service
        from src.services.keyboard_service import get_keyboard_service

        assert get_keyboard_service() is get_service(Services.KEYBOARD_SERVICE)

    def test_get_collect_service_delegates(self):
        """get_collect_service() returns the container's instance."""
        self._setup()
        from src.core.services import Services, get_service
        from src.services.collect_service import get_collect_service

        assert get_collect_service() is get_service(Services.COLLECT)

    def test_get_embedding_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.embedding_service import get_embedding_service

        assert get_embedding_service() is get_service(Services.EMBEDDING)

    def test_get_voice_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.voice_service import get_voice_service

        assert get_voice_service() is get_service(Services.VOICE)

    def test_get_image_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.image_service import get_image_service

        assert get_image_service() is get_service(Services.IMAGE)

    def test_get_cache_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.cache_service import get_cache_service

        assert get_cache_service() is get_service(Services.CACHE)

    def test_get_similarity_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.similarity_service import get_similarity_service

        assert get_similarity_service() is get_service(Services.SIMILARITY)

    def test_get_gallery_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.gallery_service import get_gallery_service

        assert get_gallery_service() is get_service(Services.GALLERY)

    def test_get_link_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.link_service import get_link_service

        assert get_link_service() is get_service(Services.LINK)

    def test_get_tts_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.tts_service import get_tts_service

        assert get_tts_service() is get_service(Services.TTS)

    def test_get_stt_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.stt_service import get_stt_service

        assert get_stt_service() is get_service(Services.STT)

    def test_get_poll_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.poll_service import get_poll_service

        assert get_poll_service() is get_service(Services.POLL)

    def test_get_polling_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.polling_service import get_polling_service

        assert get_polling_service() is get_service(Services.POLLING)

    def test_get_heartbeat_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.heartbeat_service import get_heartbeat_service

        assert get_heartbeat_service() is get_service(Services.HEARTBEAT)

    def test_get_todo_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.todo_service import get_todo_service

        assert get_todo_service() is get_service(Services.TODO)

    def test_get_trail_review_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.trail_review_service import get_trail_review_service

        assert get_trail_review_service() is get_service(Services.TRAIL_REVIEW)

    def test_get_design_skills_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.design_skills_service import get_design_skills_service

        assert get_design_skills_service() is get_service(Services.DESIGN_SKILLS)

    def test_get_opencode_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.opencode_service import get_opencode_service

        assert get_opencode_service() is get_service(Services.OPENCODE)

    def test_get_task_ledger_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.task_ledger_service import get_task_ledger_service

        assert get_task_ledger_service() is get_service(Services.TASK_LEDGER)

    def test_get_telethon_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.telethon_service import get_telethon_service

        assert get_telethon_service() is get_service(Services.TELETHON)

    def test_get_voice_response_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.voice_response_service import get_voice_response_service

        assert get_voice_response_service() is get_service(Services.VOICE_RESPONSE)

    def test_get_job_queue_service_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.job_queue_service import get_job_queue_service

        assert get_job_queue_service() is get_service(Services.JOB_QUEUE)

    def test_get_message_buffer_delegates(self):
        self._setup()
        from src.core.services import Services, get_service
        from src.services.message_buffer import get_message_buffer

        assert get_message_buffer() is get_service(Services.MESSAGE_BUFFER)


class TestNoStaleGlobalState:
    """Verify no service module retains its own singleton global."""

    def test_no_global_service_variables_in_service_modules(self):
        """Service modules should not have module-level _*_service globals."""
        import importlib
        import inspect

        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

        modules_to_check = [
            "src.services.llm_service",
            "src.services.cache_service",
            "src.services.embedding_service",
            "src.services.voice_service",
            "src.services.image_service",
            "src.services.similarity_service",
            "src.services.gallery_service",
            "src.services.link_service",
            "src.services.poll_service",
            "src.services.todo_service",
            "src.services.heartbeat_service",
            "src.services.collect_service",
            "src.services.keyboard_service",
            "src.services.claude_code_service",
            "src.services.reply_context",
            "src.services.tts_service",
            "src.services.stt_service",
            "src.services.polling_service",
            "src.services.trail_review_service",
            "src.services.design_skills_service",
            "src.services.opencode_service",
            "src.services.task_ledger_service",
            "src.services.telethon_service",
            "src.services.voice_response_service",
            "src.services.job_queue_service",
            "src.services.message_buffer",
        ]

        for mod_name in modules_to_check:
            mod = importlib.import_module(mod_name)
            members = inspect.getmembers(mod)
            for name, value in members:
                if (
                    name.startswith("_")
                    and name.endswith("_service")
                    and value is None
                ):
                    pytest.fail(
                        f"Stale global '{name}' found in {mod_name}"
                    )
