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
