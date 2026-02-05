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
            Services.VECTOR_DB,
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
