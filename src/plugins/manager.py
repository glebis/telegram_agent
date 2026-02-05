"""
Plugin Manager for discovering, loading, and managing plugins.

The PluginManager handles the complete plugin lifecycle:
1. Discovery - Find plugins in builtin and user directories
2. Loading - Import plugin modules and register services
3. Activation - Register handlers when bot is ready
4. Message Routing - Route messages through plugin processors
5. Shutdown - Graceful cleanup in reverse order
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import yaml
from telegram.ext import Application, CallbackQueryHandler

from ..core.config import get_settings
from ..core.container import ServiceContainer, get_container
from .base import BasePlugin, PluginState

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.

    Plugin discovery order:
    1. Built-in plugins: src/plugins/builtin/
    2. User plugins: plugins/ (at project root)

    Plugins are loaded in dependency order and activated after
    the bot is initialized.
    """

    # Built-in plugins shipped with the bot
    BUILTIN_PLUGINS_PATH = Path(__file__).parent / "builtin"

    # User plugins at project root
    USER_PLUGINS_PATH = Path(__file__).parent.parent.parent / "plugins"

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._load_order: List[str] = []
        self._container: Optional[ServiceContainer] = None
        self._app: Optional[Application] = None
        # (priority, name, processor_func)
        self._message_processors: List[tuple[int, str, Callable]] = []
        self._callback_handler_registered = False

    @property
    def plugins(self) -> Dict[str, BasePlugin]:
        """Get a copy of loaded plugins."""
        return self._plugins.copy()

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get a specific plugin by name."""
        return self._plugins.get(name)

    def is_plugin_active(self, name: str) -> bool:
        """Check if a plugin is active."""
        plugin = self._plugins.get(name)
        return plugin is not None and plugin.state == PluginState.ACTIVE

    async def discover_plugins(self) -> List[str]:
        """
        Discover available plugins from plugin directories.

        Returns:
            List of plugin names found
        """
        discovered = []

        for plugins_path in [self.BUILTIN_PLUGINS_PATH, self.USER_PLUGINS_PATH]:
            if not plugins_path.exists():
                logger.debug(f"Plugin path does not exist: {plugins_path}")
                continue

            for plugin_dir in plugins_path.iterdir():
                if not plugin_dir.is_dir():
                    continue
                if plugin_dir.name.startswith("_"):
                    continue

                plugin_yaml = plugin_dir / "plugin.yaml"
                if not plugin_yaml.exists():
                    logger.debug(
                        f"Plugin dir {plugin_dir.name} missing plugin.yaml, skipping"
                    )
                    continue

                try:
                    with open(plugin_yaml) as f:
                        config = yaml.safe_load(f)

                    name = config.get("name", plugin_dir.name)
                    discovered.append(name)
                    logger.info(f"Discovered plugin: {name} at {plugin_dir}")

                except Exception as e:
                    logger.error(f"Error reading plugin.yaml in {plugin_dir}: {e}")

        return discovered

    def _resolve_dependencies(self, plugins_config: Dict[str, Dict]) -> List[str]:
        """
        Resolve plugin load order based on dependencies.

        Uses topological sort to ensure dependencies are loaded first.

        Args:
            plugins_config: Dict of plugin_name -> config dict

        Returns:
            List of plugin names in load order

        Raises:
            ValueError: If circular dependency detected
        """
        # Build dependency graph
        graph: Dict[str, List[str]] = {}
        for name, config in plugins_config.items():
            deps = config.get("dependencies", [])
            graph[name] = deps

        # Topological sort
        visited = set()
        order = []

        def visit(name: str, path: set):
            if name in path:
                raise ValueError(f"Circular dependency detected: {name}")
            if name in visited:
                return

            path.add(name)
            for dep in graph.get(name, []):
                if dep in graph:  # Only if dep is also a plugin
                    visit(dep, path)
            path.remove(name)

            visited.add(name)
            order.append(name)

        for name in graph:
            visit(name, set())

        return order

    async def load_plugins(
        self,
        container: Optional[ServiceContainer] = None,
        enabled_plugins: Optional[List[str]] = None,
        disabled_plugins: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Load all discovered plugins.

        Args:
            container: DI container for service registration (uses global if None)
            enabled_plugins: If set, only load these plugins
            disabled_plugins: Plugins to skip even if discovered

        Returns:
            Dict of plugin_name -> success
        """
        if container is None:
            container = get_container()

        self._container = container
        disabled = set(disabled_plugins or [])
        results = {}

        # Load restriction settings
        settings = get_settings()
        safe_mode = settings.plugin_safe_mode
        allowlist_raw = settings.plugin_allowlist
        allowlist: set[str] = set()
        if allowlist_raw and allowlist_raw.strip():
            allowlist = {s.strip() for s in allowlist_raw.split(",") if s.strip()}

        if safe_mode:
            logger.info("Plugin safe mode ENABLED: only builtin plugins will be loaded")
        if allowlist:
            logger.info(f"Plugin allowlist active: {sorted(allowlist)}")

        # Discover and load plugin configs
        plugins_config: Dict[str, Dict] = {}
        skipped_plugins: List[tuple[str, str]] = []  # (name, reason)

        for plugins_path in [self.BUILTIN_PLUGINS_PATH, self.USER_PLUGINS_PATH]:
            if not plugins_path.exists():
                continue

            is_builtin_path = plugins_path == self.BUILTIN_PLUGINS_PATH

            # Safe mode: skip user plugin directories entirely
            if safe_mode and not is_builtin_path:
                logger.info(f"Safe mode: skipping user plugin directory {plugins_path}")
                # Log each user plugin that would have been found
                for plugin_dir in plugins_path.iterdir():
                    if (
                        plugin_dir.is_dir()
                        and not plugin_dir.name.startswith("_")
                        and (plugin_dir / "plugin.yaml").exists()
                    ):
                        try:
                            with open(plugin_dir / "plugin.yaml") as f:
                                cfg = yaml.safe_load(f) or {}
                            pname = cfg.get("name", plugin_dir.name)
                        except Exception:
                            pname = plugin_dir.name
                        skipped_plugins.append((pname, "safe mode (user plugin)"))
                        logger.info(
                            f"Plugin {pname} skipped: safe mode blocks user plugins"
                        )
                continue

            for plugin_dir in plugins_path.iterdir():
                if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
                    continue

                plugin_yaml = plugin_dir / "plugin.yaml"
                if not plugin_yaml.exists():
                    continue

                try:
                    with open(plugin_yaml) as f:
                        config = yaml.safe_load(f) or {}

                    name = config.get("name", plugin_dir.name)

                    # Apply local overrides if present (e.g., wizard decisions)
                    local_override = plugin_dir / "plugin.local.yaml"
                    if local_override.exists():
                        try:
                            with open(local_override) as lf:
                                override_cfg = yaml.safe_load(lf) or {}
                            config.update(override_cfg)
                            logger.info(f"Applied local override for plugin {name}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to read plugin override {local_override}: {e}"
                            )

                    # Allowlist check (applied to both builtin and user plugins)
                    if allowlist and name not in allowlist:
                        reason = "not in allowlist"
                        skipped_plugins.append((name, reason))
                        logger.info(
                            f"Plugin {name} skipped: not in allowlist "
                            f"(allowed: {sorted(allowlist)})"
                        )
                        continue

                    # Check if plugin should be loaded
                    if enabled_plugins and name not in enabled_plugins:
                        logger.debug(f"Plugin {name} not in enabled list, skipping")
                        continue
                    if name in disabled:
                        logger.info(f"Plugin {name} is disabled, skipping")
                        skipped_plugins.append((name, "disabled"))
                        continue
                    if not config.get("enabled", True):
                        logger.info(f"Plugin {name} disabled in config, skipping")
                        skipped_plugins.append((name, "disabled in config"))
                        continue

                    config["_dir"] = plugin_dir
                    config["_is_builtin"] = is_builtin_path
                    plugins_config[name] = config

                except Exception as e:
                    logger.error(f"Error loading plugin config from {plugin_dir}: {e}")

        # Audit summary
        if skipped_plugins:
            logger.info(
                f"Plugin audit: {len(skipped_plugins)} plugin(s) skipped: "
                + ", ".join(f"{n} ({r})" for n, r in skipped_plugins)
            )

        if not plugins_config:
            logger.info("No plugins to load")
            return results

        # Resolve load order
        try:
            load_order = self._resolve_dependencies(plugins_config)
        except ValueError as e:
            logger.error(f"Plugin dependency error: {e}")
            return results

        # Load plugins in order
        for name in load_order:
            config = plugins_config[name]
            plugin_dir = config["_dir"]
            is_builtin = config["_is_builtin"]

            success = await self._load_plugin(name, plugin_dir, config, is_builtin)
            results[name] = success

            if success:
                self._load_order.append(name)

        loaded = sum(results.values())
        total = len(results)
        logger.info(f"Loaded {loaded}/{total} plugins")

        return results

    async def _load_plugin(
        self,
        name: str,
        plugin_dir: Path,
        config: Dict,
        is_builtin: bool,
    ) -> bool:
        """Load a single plugin."""
        try:
            # Determine module path
            if is_builtin:
                module_path = f"src.plugins.builtin.{plugin_dir.name}.plugin"
            else:
                module_path = f"plugins.{plugin_dir.name}.plugin"

            # Import plugin module
            try:
                module = importlib.import_module(module_path)
            except ModuleNotFoundError:
                # Try without src. prefix
                module_path = module_path.replace("src.", "")
                try:
                    module = importlib.import_module(module_path)
                except ModuleNotFoundError as e:
                    logger.error(f"Could not import plugin {name}: {e}")
                    return False

            # Find plugin class
            plugin_class: Optional[Type[BasePlugin]] = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                ):
                    plugin_class = attr
                    break

            if not plugin_class:
                logger.error(f"No plugin class found in {module_path}")
                return False

            # Instantiate plugin
            plugin = plugin_class(plugin_dir)
            plugin.state = PluginState.LOADING
            plugin._config = config

            # Check requirements
            ok, error = plugin.check_requirements()
            if not ok:
                logger.warning(
                    "Plugin %s skipped — prerequisites not met: %s. "
                    "Set the required environment variables and restart to enable it.",
                    name,
                    error,
                )
                plugin.state = PluginState.DISABLED
                plugin._error = error
                self._plugins[name] = plugin
                return False

            # Call on_load
            if not await plugin.on_load(self._container):
                logger.error(f"Plugin {name} on_load failed")
                plugin.state = PluginState.ERROR
                plugin._error = "on_load returned False"
                self._plugins[name] = plugin
                return False

            # Register services
            plugin.register_services(self._container)

            # Register database models
            await self._register_plugin_models(plugin)

            plugin.state = PluginState.LOADED
            self._plugins[name] = plugin
            logger.info(f"Loaded plugin: {name} v{plugin.metadata.version}")
            return True

        except Exception as e:
            logger.error(f"Error loading plugin {name}: {e}", exc_info=True)
            return False

    async def _register_plugin_models(self, plugin: BasePlugin) -> None:
        """Register plugin database models."""
        models = plugin.get_database_models()
        if not models:
            return

        from .models import register_plugin_models

        try:
            await register_plugin_models(plugin, models)
            logger.debug(
                f"Registered {len(models)} models for plugin {plugin.metadata.name}"
            )
        except Exception as e:
            logger.error(
                f"Error registering models for {plugin.metadata.name}: {e}",
                exc_info=True,
            )

    async def activate_plugins(self, app: Application) -> None:
        """
        Activate all loaded plugins (register handlers).

        Called after bot is initialized.

        Args:
            app: The Telegram Application instance
        """
        self._app = app

        for name in self._load_order:
            plugin = self._plugins.get(name)
            if not plugin or plugin.state != PluginState.LOADED:
                continue

            try:
                # Call on_activate
                if not await plugin.on_activate(app):
                    logger.error(f"Plugin {name} on_activate failed")
                    plugin.state = PluginState.ERROR
                    plugin._error = "on_activate returned False"
                    continue

                # Register command handlers
                for handler in plugin.get_command_handlers():
                    app.add_handler(handler)
                    logger.debug(f"Registered handler from {name}: {handler}")

                # Register message processor
                processor = plugin.get_message_processor()
                if processor:
                    priority = plugin.metadata.priority
                    self._message_processors.append((priority, name, processor))

                plugin.state = PluginState.ACTIVE
                logger.info(f"Activated plugin: {name}")

            except Exception as e:
                logger.error(f"Error activating plugin {name}: {e}", exc_info=True)
                plugin.state = PluginState.ERROR
                plugin._error = str(e)

        # Sort message processors by priority (lower = higher priority)
        self._message_processors.sort(key=lambda x: x[0])

        # Register unified callback handler for all plugins
        if not self._callback_handler_registered:
            self._register_callback_router(app)
            self._callback_handler_registered = True

    def _register_callback_router(self, app: Application) -> None:
        """Register a single callback handler that routes to plugins."""

        async def plugin_callback_router(update, context):
            query = update.callback_query
            if not query or not query.data:
                return

            # Parse callback data: "prefix:action:params..."
            parts = query.data.split(":")
            prefix = parts[0] if parts else None
            action = parts[1] if len(parts) > 1 else ""
            params = parts[2:] if len(parts) > 2 else []

            # Find plugin with matching prefix
            for plugin in self._plugins.values():
                if plugin.state != PluginState.ACTIVE:
                    continue
                if plugin.get_callback_prefix() == prefix:
                    try:
                        handled = await plugin.handle_callback(
                            query, action, params, context
                        )
                        if handled:
                            return
                    except Exception as e:
                        logger.error(
                            f"Plugin {plugin.metadata.name} callback error: {e}",
                            exc_info=True,
                        )

            # No plugin handled it - fall through to existing handlers

        # Add with lower group priority so plugins get first chance
        app.add_handler(CallbackQueryHandler(plugin_callback_router), group=-1)

    async def route_message(self, combined: Any) -> bool:
        """
        Route a message through plugin processors.

        Called by CombinedMessageProcessor before default routing.

        Args:
            combined: The CombinedMessage to process

        Returns:
            True if any plugin handled the message
        """
        for priority, name, processor in self._message_processors:
            try:
                if await processor(combined):
                    logger.debug(f"Message handled by plugin: {name}")
                    return True
            except Exception as e:
                logger.error(
                    f"Plugin {name} message processor error: {e}", exc_info=True
                )

        return False

    def get_api_routers(self) -> List[tuple[str, Any]]:
        """
        Get API routers from all active plugins.

        Returns:
            List of (plugin_name, router) tuples
        """
        routers = []
        for name, plugin in self._plugins.items():
            if plugin.state != PluginState.ACTIVE:
                continue
            router = plugin.get_api_router()
            if router:
                routers.append((name, router))
        return routers

    async def shutdown(self) -> None:
        """Shutdown all plugins in reverse order."""
        for name in reversed(self._load_order):
            plugin = self._plugins.get(name)
            if not plugin:
                continue

            try:
                if plugin.state == PluginState.ACTIVE:
                    await plugin.on_deactivate()
                await plugin.on_unload()
                plugin.state = PluginState.UNLOADED
                logger.info(f"Unloaded plugin: {name}")
            except Exception as e:
                logger.error(f"Error unloading plugin {name}: {e}", exc_info=True)

        self._plugins.clear()
        self._load_order.clear()
        self._message_processors.clear()

    def get_plugin_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all plugins.

        Returns:
            Dict of plugin_name -> status info
        """
        status = {}
        for name, plugin in self._plugins.items():
            status[name] = {
                "state": plugin.state.value,
                "version": plugin.metadata.version,
                "description": plugin.metadata.description,
                "error": plugin.error,
                "priority": plugin.metadata.priority,
            }
        return status


# Global instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager (for testing)."""
    global _plugin_manager
    _plugin_manager = None
