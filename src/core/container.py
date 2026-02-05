"""
Dependency Injection Container.

Provides centralized service registration, lifecycle management,
and dependency resolution for the application.

Usage:
    from src.core.container import get_container, service

    # Register a service
    container = get_container()
    container.register("my_service", MyService)

    # Or use decorator
    @service("my_service")
    class MyService:
        pass

    # Get a service
    svc = container.get("my_service")
"""

import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Factory type: either a class or a callable that takes the container
Factory = Union[type, Callable[["ServiceContainer"], Any]]
AsyncFactory = Callable[["ServiceContainer"], Any]


class ServiceContainer:
    """
    Dependency injection container for managing service lifecycles.

    Features:
    - Lazy initialization (services created on first access)
    - Singleton by default (or transient per-request)
    - Dependency injection via factory functions
    - Async service support
    - Easy testing via service overrides
    """

    def __init__(self):
        self._factories: Dict[str, Factory] = {}
        self._async_factories: Dict[str, AsyncFactory] = {}
        self._instances: Dict[str, Any] = {}
        self._singleton_flags: Dict[str, bool] = {}

    def register(
        self,
        name: str,
        factory: Factory,
        singleton: bool = True,
    ) -> None:
        """
        Register a service factory.

        Args:
            name: Service name/key
            factory: Class or callable that creates the service.
                     If callable, receives the container as argument.
            singleton: If True (default), cache the instance.
        """
        self._factories[name] = factory
        self._singleton_flags[name] = singleton
        # Clear any cached instance if overriding
        self._instances.pop(name, None)
        logger.debug(f"Registered service: {name} (singleton={singleton})")

    def register_async(
        self,
        name: str,
        factory: AsyncFactory,
        singleton: bool = True,
    ) -> None:
        """
        Register an async service factory.

        Args:
            name: Service name/key
            factory: Async callable that creates the service.
            singleton: If True (default), cache the instance.
        """
        self._async_factories[name] = factory
        self._singleton_flags[name] = singleton
        self._instances.pop(name, None)
        logger.debug(f"Registered async service: {name} (singleton={singleton})")

    def register_instance(self, name: str, instance: Any) -> None:
        """
        Register a pre-existing instance.

        Args:
            name: Service name/key
            instance: The instance to register
        """
        self._instances[name] = instance
        self._singleton_flags[name] = True
        logger.debug(f"Registered instance: {name}")

    def get(self, name: str) -> Any:
        """
        Get a service by name.

        Args:
            name: Service name/key

        Returns:
            The service instance

        Raises:
            KeyError: If service is not registered
        """
        # Return cached instance if exists and singleton
        if name in self._instances and self._singleton_flags.get(name, True):
            return self._instances[name]

        # Check if registered
        if name not in self._factories:
            raise KeyError(f"Service '{name}' is not registered")

        # Create instance
        factory = self._factories[name]
        if callable(factory) and not isinstance(factory, type):
            # It's a factory function, pass container
            instance = factory(self)
        else:
            # It's a class, instantiate directly
            instance = factory()

        # Cache if singleton
        if self._singleton_flags.get(name, True):
            self._instances[name] = instance
            logger.debug(f"Created singleton instance: {name}")
        else:
            logger.debug(f"Created transient instance: {name}")

        return instance

    async def get_async(self, name: str) -> Any:
        """
        Get an async service by name.

        Args:
            name: Service name/key

        Returns:
            The service instance

        Raises:
            KeyError: If service is not registered
        """
        # Return cached instance if exists and singleton
        if name in self._instances and self._singleton_flags.get(name, True):
            return self._instances[name]

        # Check if registered as async
        if name not in self._async_factories:
            # Fall back to sync get
            if name in self._factories:
                return self.get(name)
            raise KeyError(f"Async service '{name}' is not registered")

        # Create instance
        factory = self._async_factories[name]
        instance = await factory(self)

        # Cache if singleton
        if self._singleton_flags.get(name, True):
            self._instances[name] = instance
            logger.debug(f"Created async singleton instance: {name}")

        return instance

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return (
            name in self._factories
            or name in self._async_factories
            or name in self._instances
        )

    def clear(self) -> None:
        """Clear all registrations and instances."""
        self._factories.clear()
        self._async_factories.clear()
        self._instances.clear()
        self._singleton_flags.clear()
        logger.debug("Container cleared")


# Global container instance
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """Get the global service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container() -> None:
    """Reset the global container (useful for testing)."""
    global _container
    if _container is not None:
        _container.clear()
    _container = ServiceContainer()
    logger.debug("Global container reset")


def service(
    name: str,
    singleton: bool = True,
    dependencies: Optional[List[str]] = None,
) -> Callable[[type], type]:
    """
    Decorator to register a class as a service.

    Args:
        name: Service name/key
        singleton: If True (default), cache the instance
        dependencies: List of service names to inject as constructor args

    Usage:
        @service("user_service", dependencies=["database"])
        class UserService:
            def __init__(self, database):
                self.db = database
    """

    def decorator(cls: type) -> type:
        container = get_container()

        if dependencies:
            # Create factory that resolves dependencies
            def factory(c: ServiceContainer) -> Any:
                deps = [c.get(dep_name) for dep_name in dependencies]
                return cls(*deps)

            container.register(name, factory, singleton=singleton)
        else:
            container.register(name, cls, singleton=singleton)

        return cls

    return decorator
