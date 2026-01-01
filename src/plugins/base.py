"""
Base classes and protocols for the plugin system.

Plugins extend BasePlugin and implement the required lifecycle methods
to integrate with the bot's service container, command handlers, and
message routing.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import Application, BaseHandler, ContextTypes
    from fastapi import APIRouter
    from ..core.container import ServiceContainer


class PluginState(Enum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginMetadata:
    """
    Plugin metadata loaded from plugin.yaml.

    Attributes:
        name: Unique plugin identifier (e.g., "claude-code")
        version: Semantic version string (e.g., "1.0.0")
        description: Human-readable description
        author: Plugin author name
        requires: List of required environment variables
        dependencies: List of other plugin names this depends on
        priority: Message routing priority (lower = higher priority)
        enabled_by_default: Whether plugin is enabled when first discovered
    """

    name: str
    version: str
    description: str
    author: str = ""
    requires: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    priority: int = 100
    enabled_by_default: bool = True


@dataclass
class PluginCapabilities:
    """
    Declares what a plugin provides.

    Used for documentation and validation.
    """

    services: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    callbacks: List[str] = field(default_factory=list)
    api_routes: bool = False
    message_handler: bool = False


class BasePlugin(ABC):
    """
    Base class for all plugins.

    Plugins are self-contained modules that can register:
    - Services (via the DI container)
    - Command handlers (/command)
    - Callback handlers (inline keyboard callbacks)
    - API routes (FastAPI router)
    - Message routing hooks

    Lifecycle:
        1. __init__() - Plugin instantiated with its directory path
        2. check_requirements() - Verify env vars and dependencies
        3. on_load() - Register services, load config
        4. on_activate() - Register handlers (bot is ready)
        5. on_deactivate() - Cleanup before disable
        6. on_unload() - Final cleanup

    Example:
        class MyPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="my-plugin",
                    version="1.0.0",
                    description="Does something cool",
                )

            async def on_load(self, container) -> bool:
                container.register("my_service", MyService)
                return True
    """

    def __init__(self, plugin_dir: Path):
        """
        Initialize plugin with its directory path.

        Args:
            plugin_dir: Path to the plugin's directory
        """
        self.plugin_dir = plugin_dir
        self.state = PluginState.UNLOADED
        self._config: Dict[str, Any] = {}
        self._error: Optional[str] = None

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata. Must be implemented by subclasses."""
        pass

    @property
    def capabilities(self) -> PluginCapabilities:
        """
        Return plugin capabilities.

        Override to declare what your plugin provides.
        """
        return PluginCapabilities()

    @property
    def config(self) -> Dict[str, Any]:
        """Get the loaded configuration from plugin.yaml."""
        return self._config

    @property
    def error(self) -> Optional[str]:
        """Get error message if plugin is in error state."""
        return self._error

    def check_requirements(self) -> tuple[bool, str]:
        """
        Check if all requirements are met.

        Verifies that all required environment variables are set.

        Returns:
            Tuple of (success, error_message)
        """
        missing = []
        for req in self.metadata.requires:
            if not os.getenv(req):
                missing.append(req)

        if missing:
            return False, f"Missing environment variables: {', '.join(missing)}"
        return True, ""

    # === Lifecycle Hooks ===

    async def on_load(self, container: "ServiceContainer") -> bool:
        """
        Called when plugin is being loaded.

        This is the place to:
        - Register services with the DI container
        - Load configuration files
        - Initialize any required state

        Args:
            container: The service container for dependency injection

        Returns:
            True if loading succeeded, False otherwise
        """
        return True

    async def on_activate(self, app: "Application") -> bool:
        """
        Called when the bot is ready and plugin should activate.

        This is the place to:
        - Initialize caches that require database access
        - Start background tasks
        - Do any async initialization

        Args:
            app: The Telegram Application instance

        Returns:
            True if activation succeeded, False otherwise
        """
        return True

    async def on_deactivate(self) -> None:
        """
        Called when plugin is being deactivated.

        Clean up any resources that were allocated in on_activate.
        """
        pass

    async def on_unload(self) -> None:
        """
        Called when plugin is being unloaded.

        Final cleanup - close connections, save state, etc.
        """
        pass

    # === Registration Methods ===

    def register_services(self, container: "ServiceContainer") -> None:
        """
        Register plugin services in the DI container.

        Override to register your plugin's services.

        Example:
            def register_services(self, container):
                container.register("my_service", MyService)
        """
        pass

    def get_command_handlers(self) -> List["BaseHandler"]:
        """
        Return Telegram command handlers to register.

        Override to provide command handlers.

        Example:
            def get_command_handlers(self):
                from telegram.ext import CommandHandler
                return [
                    CommandHandler("mycommand", self.handle_mycommand),
                ]
        """
        return []

    def get_callback_prefix(self) -> Optional[str]:
        """
        Return the callback data prefix for this plugin.

        Callbacks with data starting with this prefix will be routed
        to this plugin's handle_callback method.

        Example:
            def get_callback_prefix(self):
                return "myplugin"  # Handles "myplugin:action:params..."
        """
        return None

    async def handle_callback(
        self,
        query: Any,
        action: str,
        params: List[str],
        context: "ContextTypes.DEFAULT_TYPE",
    ) -> bool:
        """
        Handle callback queries for this plugin.

        Called when a callback with matching prefix is received.

        Args:
            query: The CallbackQuery object
            action: The action part of the callback data
            params: Additional parameters from callback data
            context: The bot context

        Returns:
            True if the callback was handled, False to pass to others
        """
        return False

    def get_api_router(self) -> Optional["APIRouter"]:
        """
        Return a FastAPI router for plugin-specific API endpoints.

        Override to provide API routes.

        Example:
            def get_api_router(self):
                from fastapi import APIRouter
                router = APIRouter()

                @router.get("/status")
                async def get_status():
                    return {"status": "ok"}

                return router
        """
        return None

    def get_message_processor(self) -> Optional[Callable]:
        """
        Return a message processor function for routing integration.

        The processor will be called for each message in priority order.
        Return True to indicate the message was handled.

        Signature:
            async def process(combined: CombinedMessage) -> bool

        Example:
            def get_message_processor(self):
                async def process(combined):
                    if combined.has_my_trigger():
                        await self.handle_message(combined)
                        return True
                    return False
                return process
        """
        return None

    def get_database_models(self) -> List[Type]:
        """
        Return SQLAlchemy model classes for this plugin.

        Models will be registered with the database and tables created
        if they don't exist.

        Example:
            def get_database_models(self):
                from .models import MyModel, AnotherModel
                return [MyModel, AnotherModel]
        """
        return []

    # === Utility Methods ===

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value from the plugin config.

        Args:
            key: Dot-separated key path (e.g., "settings.timeout")
            default: Default value if key not found

        Returns:
            The configuration value or default
        """
        keys = key.split(".")
        value = self._config.get("config", {})

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.metadata.name!r} "
            f"state={self.state.value}>"
        )
