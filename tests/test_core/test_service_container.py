"""
Tests for the dependency injection container.
"""

import pytest


class TestServiceContainer:
    """Test the ServiceContainer class."""

    def test_container_can_be_created(self):
        """Container can be instantiated."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()
        assert container is not None

    def test_register_and_get_service(self):
        """Can register a service factory and retrieve it."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class MyService:
            def __init__(self):
                self.name = "test"

        container.register("my_service", MyService)
        service = container.get("my_service")

        assert isinstance(service, MyService)
        assert service.name == "test"

    def test_singleton_by_default(self):
        """Services are singletons by default - same instance returned."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        call_count = 0

        class CountingService:
            def __init__(self):
                nonlocal call_count
                call_count += 1

        container.register("counter", CountingService)

        s1 = container.get("counter")
        s2 = container.get("counter")

        assert s1 is s2
        assert call_count == 1

    def test_transient_services(self):
        """Transient services create new instances each time."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class TransientService:
            pass

        container.register("transient", TransientService, singleton=False)

        s1 = container.get("transient")
        s2 = container.get("transient")

        assert s1 is not s2

    def test_dependency_injection(self):
        """Services can depend on other services."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class DatabaseService:
            def query(self):
                return "data"

        class UserService:
            def __init__(self, db: DatabaseService):
                self.db = db

            def get_users(self):
                return self.db.query()

        container.register("database", DatabaseService)
        container.register("user_service", lambda c: UserService(c.get("database")))

        user_service = container.get("user_service")
        assert user_service.get_users() == "data"

    def test_register_instance(self):
        """Can register a pre-existing instance."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class ConfigService:
            def __init__(self, env: str):
                self.env = env

        config = ConfigService("production")
        container.register_instance("config", config)

        retrieved = container.get("config")
        assert retrieved is config
        assert retrieved.env == "production"

    def test_override_service(self):
        """Can override a registered service."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class RealService:
            name = "real"

        class MockService:
            name = "mock"

        container.register("service", RealService)
        container.register("service", MockService)  # Override

        service = container.get("service")
        assert service.name == "mock"

    def test_get_unregistered_raises(self):
        """Getting an unregistered service raises KeyError."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        with pytest.raises(KeyError):
            container.get("nonexistent")

    def test_has_service(self):
        """Can check if a service is registered."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()
        container.register("exists", lambda c: "value")

        assert container.has("exists")
        assert not container.has("not_exists")

    def test_clear_resets_container(self):
        """Clear removes all services and instances."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()
        container.register("service", lambda c: object())
        _ = container.get("service")  # Create instance

        container.clear()

        assert not container.has("service")

    def test_lazy_initialization(self):
        """Services are only instantiated when first accessed."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()
        initialized = False

        class LazyService:
            def __init__(self):
                nonlocal initialized
                initialized = True

        container.register("lazy", LazyService)
        assert not initialized

        container.get("lazy")
        assert initialized


class TestAsyncServiceContainer:
    """Test async service support."""

    @pytest.mark.asyncio
    async def test_async_factory(self):
        """Can register and get async factories."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        async def async_factory(c):
            return {"initialized": True}

        container.register_async("async_service", async_factory)
        service = await container.get_async("async_service")

        assert service["initialized"] is True

    @pytest.mark.asyncio
    async def test_async_with_dependencies(self):
        """Async services can depend on sync services."""
        from src.core.container import ServiceContainer

        container = ServiceContainer()

        class Config:
            db_url = "sqlite:///:memory:"

        async def create_db(c):
            config = c.get("config")
            return {"url": config.db_url, "connected": True}

        container.register("config", Config)
        container.register_async("database", create_db)

        db = await container.get_async("database")
        assert db["url"] == "sqlite:///:memory:"
        assert db["connected"] is True


class TestGlobalContainer:
    """Test global container access."""

    def test_get_container_returns_same_instance(self):
        """get_container returns the same container instance."""
        from src.core.container import get_container, reset_container

        reset_container()  # Start fresh

        c1 = get_container()
        c2 = get_container()

        assert c1 is c2

    def test_reset_container_creates_new(self):
        """reset_container creates a new container."""
        from src.core.container import get_container, reset_container

        c1 = get_container()
        reset_container()
        c2 = get_container()

        assert c1 is not c2


class TestServiceDecorator:
    """Test the @service decorator for registering services."""

    def test_service_decorator_registers(self):
        """@service decorator registers the class."""
        from src.core.container import get_container, reset_container, service

        reset_container()

        @service("decorated_service")
        class DecoratedService:
            value = 42

        container = get_container()
        assert container.has("decorated_service")

        svc = container.get("decorated_service")
        assert svc.value == 42

    def test_service_decorator_with_dependencies(self):
        """@service decorator can specify dependencies."""
        from src.core.container import get_container, reset_container, service

        reset_container()
        container = get_container()

        class DepService:
            data = "dependency"

        container.register("dep", DepService)

        @service("main", dependencies=["dep"])
        class MainService:
            def __init__(self, dep: DepService):
                self.dep = dep

        svc = container.get("main")
        assert svc.dep.data == "dependency"
