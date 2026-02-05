"""
Tests for the plugin base classes.

Tests cover:
- PluginState enum values
- PluginMetadata dataclass
- PluginCapabilities dataclass
- BasePlugin abstract class
- Plugin lifecycle (on_load, on_activate, on_deactivate, on_unload)
- Abstract method requirements
- Plugin metadata properties
- Command handler registration
- Callback handling
- Config value retrieval
- Error handling in lifecycle hooks
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.plugins.base import (
    BasePlugin,
    PluginCapabilities,
    PluginMetadata,
    PluginState,
)


class TestPluginState:
    """Tests for PluginState enum."""

    def test_all_states_exist(self):
        """Test all expected plugin states are defined."""
        assert hasattr(PluginState, "UNLOADED")
        assert hasattr(PluginState, "LOADING")
        assert hasattr(PluginState, "LOADED")
        assert hasattr(PluginState, "ACTIVE")
        assert hasattr(PluginState, "DISABLED")
        assert hasattr(PluginState, "ERROR")

    def test_state_values(self):
        """Test state enum values are strings."""
        assert PluginState.UNLOADED.value == "unloaded"
        assert PluginState.LOADING.value == "loading"
        assert PluginState.LOADED.value == "loaded"
        assert PluginState.ACTIVE.value == "active"
        assert PluginState.DISABLED.value == "disabled"
        assert PluginState.ERROR.value == "error"

    def test_state_comparison(self):
        """Test states can be compared."""
        state1 = PluginState.LOADED
        state2 = PluginState.LOADED
        state3 = PluginState.ACTIVE

        assert state1 == state2
        assert state1 != state3

    def test_state_count(self):
        """Test we have exactly 6 states."""
        assert len(PluginState) == 6


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_required_fields_only(self):
        """Test creating metadata with only required fields."""
        meta = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )

        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.description == "A test plugin"

    def test_default_author(self):
        """Test author defaults to empty string."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        assert meta.author == ""

    def test_default_requires(self):
        """Test requires defaults to empty list."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        assert meta.requires == []
        assert isinstance(meta.requires, list)

    def test_default_dependencies(self):
        """Test dependencies defaults to empty list."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        assert meta.dependencies == []
        assert isinstance(meta.dependencies, list)

    def test_default_priority(self):
        """Test priority defaults to 100."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        assert meta.priority == 100

    def test_default_enabled_by_default(self):
        """Test enabled_by_default defaults to True."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        assert meta.enabled_by_default is True

    def test_all_fields_set(self):
        """Test setting all fields."""
        meta = PluginMetadata(
            name="full-plugin",
            version="2.0.0",
            description="Full description",
            author="Test Author",
            requires=["API_KEY", "OTHER_KEY"],
            dependencies=["dep-plugin-1", "dep-plugin-2"],
            priority=50,
            enabled_by_default=False,
        )

        assert meta.name == "full-plugin"
        assert meta.version == "2.0.0"
        assert meta.description == "Full description"
        assert meta.author == "Test Author"
        assert meta.requires == ["API_KEY", "OTHER_KEY"]
        assert meta.dependencies == ["dep-plugin-1", "dep-plugin-2"]
        assert meta.priority == 50
        assert meta.enabled_by_default is False

    def test_requires_list_is_mutable(self):
        """Test requires list can be modified."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        meta.requires.append("NEW_VAR")
        assert "NEW_VAR" in meta.requires

    def test_dependencies_list_is_mutable(self):
        """Test dependencies list can be modified."""
        meta = PluginMetadata(name="test", version="1.0.0", description="test")
        meta.dependencies.append("new-dep")
        assert "new-dep" in meta.dependencies

    def test_priority_can_be_zero(self):
        """Test priority can be set to 0 (highest priority)."""
        meta = PluginMetadata(
            name="test", version="1.0.0", description="test", priority=0
        )
        assert meta.priority == 0

    def test_priority_can_be_negative(self):
        """Test priority can be negative."""
        meta = PluginMetadata(
            name="test", version="1.0.0", description="test", priority=-10
        )
        assert meta.priority == -10


class TestPluginCapabilities:
    """Tests for PluginCapabilities dataclass."""

    def test_default_values(self):
        """Test all fields have correct defaults."""
        caps = PluginCapabilities()

        assert caps.services == []
        assert caps.commands == []
        assert caps.callbacks == []
        assert caps.api_routes is False
        assert caps.message_handler is False

    def test_services_list(self):
        """Test setting services list."""
        caps = PluginCapabilities(services=["service1", "service2"])
        assert caps.services == ["service1", "service2"]

    def test_commands_list(self):
        """Test setting commands list."""
        caps = PluginCapabilities(commands=["/cmd1", "/cmd2"])
        assert caps.commands == ["/cmd1", "/cmd2"]

    def test_callbacks_list(self):
        """Test setting callbacks list."""
        caps = PluginCapabilities(callbacks=["cb:action1", "cb:action2"])
        assert caps.callbacks == ["cb:action1", "cb:action2"]

    def test_api_routes_true(self):
        """Test setting api_routes to True."""
        caps = PluginCapabilities(api_routes=True)
        assert caps.api_routes is True

    def test_message_handler_true(self):
        """Test setting message_handler to True."""
        caps = PluginCapabilities(message_handler=True)
        assert caps.message_handler is True

    def test_all_capabilities_set(self):
        """Test setting all capabilities."""
        caps = PluginCapabilities(
            services=["svc1"],
            commands=["/cmd1"],
            callbacks=["cb1"],
            api_routes=True,
            message_handler=True,
        )

        assert caps.services == ["svc1"]
        assert caps.commands == ["/cmd1"]
        assert caps.callbacks == ["cb1"]
        assert caps.api_routes is True
        assert caps.message_handler is True


# Helper class for testing - a minimal concrete implementation
class MinimalPlugin(BasePlugin):
    """Minimal plugin implementation for testing."""

    def __init__(self, plugin_dir: Path, name: str = "minimal"):
        super().__init__(plugin_dir)
        self._name = name

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version="1.0.0",
            description="Minimal test plugin",
        )


class TestBasePluginInitialization:
    """Tests for BasePlugin initialization."""

    def test_init_sets_plugin_dir(self, tmp_path):
        """Test plugin_dir is set correctly."""
        plugin = MinimalPlugin(tmp_path)
        assert plugin.plugin_dir == tmp_path

    def test_init_sets_unloaded_state(self, tmp_path):
        """Test initial state is UNLOADED."""
        plugin = MinimalPlugin(tmp_path)
        assert plugin.state == PluginState.UNLOADED

    def test_init_empty_config(self, tmp_path):
        """Test initial config is empty dict."""
        plugin = MinimalPlugin(tmp_path)
        assert plugin._config == {}
        assert plugin.config == {}

    def test_init_no_error(self, tmp_path):
        """Test initial error is None."""
        plugin = MinimalPlugin(tmp_path)
        assert plugin._error is None
        assert plugin.error is None


class TestBasePluginAbstractMethods:
    """Tests for abstract method requirements."""

    def test_cannot_instantiate_base_plugin(self, tmp_path):
        """Test BasePlugin cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BasePlugin(tmp_path)

        assert "abstract" in str(exc_info.value).lower()

    def test_must_implement_metadata(self, tmp_path):
        """Test subclass must implement metadata property."""

        class IncompletePlugin(BasePlugin):
            pass  # Missing metadata property

        with pytest.raises(TypeError) as exc_info:
            IncompletePlugin(tmp_path)

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_implementation_works(self, tmp_path):
        """Test concrete implementation can be instantiated."""
        plugin = MinimalPlugin(tmp_path)
        assert plugin is not None
        assert isinstance(plugin, BasePlugin)


class TestBasePluginProperties:
    """Tests for BasePlugin properties."""

    def test_metadata_property(self, tmp_path):
        """Test metadata property returns PluginMetadata."""
        plugin = MinimalPlugin(tmp_path, name="test-plugin")
        meta = plugin.metadata

        assert isinstance(meta, PluginMetadata)
        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"

    def test_capabilities_default(self, tmp_path):
        """Test default capabilities returns empty PluginCapabilities."""
        plugin = MinimalPlugin(tmp_path)
        caps = plugin.capabilities

        assert isinstance(caps, PluginCapabilities)
        assert caps.services == []
        assert caps.commands == []
        assert caps.api_routes is False

    def test_capabilities_can_be_overridden(self, tmp_path):
        """Test capabilities can be overridden in subclass."""

        class CapablePlugin(MinimalPlugin):
            @property
            def capabilities(self) -> PluginCapabilities:
                return PluginCapabilities(
                    services=["my_service"],
                    commands=["/mycommand"],
                    api_routes=True,
                )

        plugin = CapablePlugin(tmp_path)
        caps = plugin.capabilities

        assert caps.services == ["my_service"]
        assert caps.commands == ["/mycommand"]
        assert caps.api_routes is True

    def test_config_property(self, tmp_path):
        """Test config property returns internal config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"test": "value"}

        assert plugin.config == {"test": "value"}

    def test_error_property(self, tmp_path):
        """Test error property returns internal error."""
        plugin = MinimalPlugin(tmp_path)
        plugin._error = "Something went wrong"

        assert plugin.error == "Something went wrong"


class TestBasePluginCheckRequirements:
    """Tests for check_requirements method."""

    def test_no_requirements_passes(self, tmp_path):
        """Test plugin with no requirements passes check."""
        plugin = MinimalPlugin(tmp_path)
        ok, error = plugin.check_requirements()

        assert ok is True
        assert error == ""

    def test_present_env_var_passes(self, tmp_path):
        """Test plugin with present env var passes."""

        class RequiresEnvPlugin(MinimalPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="requires-env",
                    version="1.0.0",
                    description="Test",
                    requires=["TEST_PLUGIN_VAR"],
                )

        os.environ["TEST_PLUGIN_VAR"] = "present"
        try:
            plugin = RequiresEnvPlugin(tmp_path)
            ok, error = plugin.check_requirements()

            assert ok is True
            assert error == ""
        finally:
            del os.environ["TEST_PLUGIN_VAR"]

    def test_missing_env_var_fails(self, tmp_path):
        """Test plugin with missing env var fails."""

        class RequiresMissingPlugin(MinimalPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="requires-missing",
                    version="1.0.0",
                    description="Test",
                    requires=["NONEXISTENT_VAR_12345"],
                )

        # Make sure it's not set
        os.environ.pop("NONEXISTENT_VAR_12345", None)

        plugin = RequiresMissingPlugin(tmp_path)
        ok, error = plugin.check_requirements()

        assert ok is False
        assert "NONEXISTENT_VAR_12345" in error
        assert "Missing environment variables" in error

    def test_multiple_missing_vars(self, tmp_path):
        """Test error message lists all missing vars."""

        class RequiresMultiplePlugin(MinimalPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="requires-multiple",
                    version="1.0.0",
                    description="Test",
                    requires=["MISSING_VAR_A", "MISSING_VAR_B"],
                )

        os.environ.pop("MISSING_VAR_A", None)
        os.environ.pop("MISSING_VAR_B", None)

        plugin = RequiresMultiplePlugin(tmp_path)
        ok, error = plugin.check_requirements()

        assert ok is False
        assert "MISSING_VAR_A" in error
        assert "MISSING_VAR_B" in error

    def test_partial_requirements_met(self, tmp_path):
        """Test partial requirements met still fails."""

        class PartialPlugin(MinimalPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="partial",
                    version="1.0.0",
                    description="Test",
                    requires=["PRESENT_VAR", "MISSING_VAR_X"],
                )

        os.environ["PRESENT_VAR"] = "present"
        os.environ.pop("MISSING_VAR_X", None)

        try:
            plugin = PartialPlugin(tmp_path)
            ok, error = plugin.check_requirements()

            assert ok is False
            assert "MISSING_VAR_X" in error
            assert "PRESENT_VAR" not in error  # Should only list missing
        finally:
            del os.environ["PRESENT_VAR"]


class TestBasePluginLifecycleHooks:
    """Tests for lifecycle hook methods."""

    @pytest.mark.asyncio
    async def test_on_load_default_returns_true(self, tmp_path):
        """Test default on_load returns True."""
        plugin = MinimalPlugin(tmp_path)
        container = MagicMock()

        result = await plugin.on_load(container)

        assert result is True

    @pytest.mark.asyncio
    async def test_on_activate_default_returns_true(self, tmp_path):
        """Test default on_activate returns True."""
        plugin = MinimalPlugin(tmp_path)
        app = MagicMock()

        result = await plugin.on_activate(app)

        assert result is True

    @pytest.mark.asyncio
    async def test_on_deactivate_default_returns_none(self, tmp_path):
        """Test default on_deactivate returns None."""
        plugin = MinimalPlugin(tmp_path)

        result = await plugin.on_deactivate()

        assert result is None

    @pytest.mark.asyncio
    async def test_on_unload_default_returns_none(self, tmp_path):
        """Test default on_unload returns None."""
        plugin = MinimalPlugin(tmp_path)

        result = await plugin.on_unload()

        assert result is None

    @pytest.mark.asyncio
    async def test_on_load_can_be_overridden(self, tmp_path):
        """Test on_load can be overridden to do work."""

        class CustomLoadPlugin(MinimalPlugin):
            load_called = False
            received_container = None

            async def on_load(self, container):
                CustomLoadPlugin.load_called = True
                CustomLoadPlugin.received_container = container
                return True

        plugin = CustomLoadPlugin(tmp_path)
        container = MagicMock()

        await plugin.on_load(container)

        assert CustomLoadPlugin.load_called
        assert CustomLoadPlugin.received_container is container

    @pytest.mark.asyncio
    async def test_on_load_can_return_false(self, tmp_path):
        """Test on_load can return False to indicate failure."""

        class FailingLoadPlugin(MinimalPlugin):
            async def on_load(self, container):
                return False

        plugin = FailingLoadPlugin(tmp_path)
        container = MagicMock()

        result = await plugin.on_load(container)

        assert result is False

    @pytest.mark.asyncio
    async def test_on_activate_can_be_overridden(self, tmp_path):
        """Test on_activate can be overridden."""

        class CustomActivatePlugin(MinimalPlugin):
            activate_called = False
            received_app = None

            async def on_activate(self, app):
                CustomActivatePlugin.activate_called = True
                CustomActivatePlugin.received_app = app
                return True

        plugin = CustomActivatePlugin(tmp_path)
        app = MagicMock()

        await plugin.on_activate(app)

        assert CustomActivatePlugin.activate_called
        assert CustomActivatePlugin.received_app is app

    @pytest.mark.asyncio
    async def test_on_activate_can_return_false(self, tmp_path):
        """Test on_activate can return False to indicate failure."""

        class FailingActivatePlugin(MinimalPlugin):
            async def on_activate(self, app):
                return False

        plugin = FailingActivatePlugin(tmp_path)
        app = MagicMock()

        result = await plugin.on_activate(app)

        assert result is False

    @pytest.mark.asyncio
    async def test_on_deactivate_can_do_cleanup(self, tmp_path):
        """Test on_deactivate can perform cleanup."""

        class CleanupPlugin(MinimalPlugin):
            deactivate_called = False

            async def on_deactivate(self):
                CleanupPlugin.deactivate_called = True

        plugin = CleanupPlugin(tmp_path)

        await plugin.on_deactivate()

        assert CleanupPlugin.deactivate_called

    @pytest.mark.asyncio
    async def test_on_unload_can_do_final_cleanup(self, tmp_path):
        """Test on_unload can perform final cleanup."""

        class FinalCleanupPlugin(MinimalPlugin):
            unload_called = False

            async def on_unload(self):
                FinalCleanupPlugin.unload_called = True

        plugin = FinalCleanupPlugin(tmp_path)

        await plugin.on_unload()

        assert FinalCleanupPlugin.unload_called

    @pytest.mark.asyncio
    async def test_full_lifecycle_order(self, tmp_path):
        """Test lifecycle hooks can be called in correct order."""

        class LifecyclePlugin(MinimalPlugin):
            order = []

            async def on_load(self, container):
                LifecyclePlugin.order.append("load")
                return True

            async def on_activate(self, app):
                LifecyclePlugin.order.append("activate")
                return True

            async def on_deactivate(self):
                LifecyclePlugin.order.append("deactivate")

            async def on_unload(self):
                LifecyclePlugin.order.append("unload")

        LifecyclePlugin.order = []  # Reset
        plugin = LifecyclePlugin(tmp_path)
        container = MagicMock()
        app = MagicMock()

        await plugin.on_load(container)
        await plugin.on_activate(app)
        await plugin.on_deactivate()
        await plugin.on_unload()

        assert LifecyclePlugin.order == ["load", "activate", "deactivate", "unload"]


class TestBasePluginLifecycleErrorHandling:
    """Tests for error handling in lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_on_load_exception_propagates(self, tmp_path):
        """Test exception in on_load propagates."""

        class ExceptionLoadPlugin(MinimalPlugin):
            async def on_load(self, container):
                raise ValueError("Load failed!")

        plugin = ExceptionLoadPlugin(tmp_path)
        container = MagicMock()

        with pytest.raises(ValueError, match="Load failed!"):
            await plugin.on_load(container)

    @pytest.mark.asyncio
    async def test_on_activate_exception_propagates(self, tmp_path):
        """Test exception in on_activate propagates."""

        class ExceptionActivatePlugin(MinimalPlugin):
            async def on_activate(self, app):
                raise RuntimeError("Activate failed!")

        plugin = ExceptionActivatePlugin(tmp_path)
        app = MagicMock()

        with pytest.raises(RuntimeError, match="Activate failed!"):
            await plugin.on_activate(app)

    @pytest.mark.asyncio
    async def test_on_deactivate_exception_propagates(self, tmp_path):
        """Test exception in on_deactivate propagates."""

        class ExceptionDeactivatePlugin(MinimalPlugin):
            async def on_deactivate(self):
                raise RuntimeError("Deactivate failed!")

        plugin = ExceptionDeactivatePlugin(tmp_path)

        with pytest.raises(RuntimeError, match="Deactivate failed!"):
            await plugin.on_deactivate()

    @pytest.mark.asyncio
    async def test_on_unload_exception_propagates(self, tmp_path):
        """Test exception in on_unload propagates."""

        class ExceptionUnloadPlugin(MinimalPlugin):
            async def on_unload(self):
                raise RuntimeError("Unload failed!")

        plugin = ExceptionUnloadPlugin(tmp_path)

        with pytest.raises(RuntimeError, match="Unload failed!"):
            await plugin.on_unload()


class TestBasePluginRegistrationMethods:
    """Tests for registration methods."""

    def test_register_services_default_is_noop(self, tmp_path):
        """Test default register_services does nothing."""
        plugin = MinimalPlugin(tmp_path)
        container = MagicMock()

        # Should not raise
        plugin.register_services(container)

        # No interactions expected
        container.register.assert_not_called()

    def test_register_services_can_be_overridden(self, tmp_path):
        """Test register_services can be overridden."""

        class ServicePlugin(MinimalPlugin):
            def register_services(self, container):
                container.register("my_service", MagicMock)

        plugin = ServicePlugin(tmp_path)
        container = MagicMock()

        plugin.register_services(container)

        container.register.assert_called_once_with("my_service", MagicMock)

    def test_get_command_handlers_default_empty(self, tmp_path):
        """Test default get_command_handlers returns empty list."""
        plugin = MinimalPlugin(tmp_path)

        handlers = plugin.get_command_handlers()

        assert handlers == []
        assert isinstance(handlers, list)

    def test_get_command_handlers_can_be_overridden(self, tmp_path):
        """Test get_command_handlers can return handlers."""

        class CommandPlugin(MinimalPlugin):
            def get_command_handlers(self):
                handler1 = MagicMock()
                handler2 = MagicMock()
                return [handler1, handler2]

        plugin = CommandPlugin(tmp_path)

        handlers = plugin.get_command_handlers()

        assert len(handlers) == 2

    def test_get_callback_prefix_default_none(self, tmp_path):
        """Test default get_callback_prefix returns None."""
        plugin = MinimalPlugin(tmp_path)

        prefix = plugin.get_callback_prefix()

        assert prefix is None

    def test_get_callback_prefix_can_be_overridden(self, tmp_path):
        """Test get_callback_prefix can return a prefix."""

        class CallbackPlugin(MinimalPlugin):
            def get_callback_prefix(self):
                return "myplugin"

        plugin = CallbackPlugin(tmp_path)

        prefix = plugin.get_callback_prefix()

        assert prefix == "myplugin"

    @pytest.mark.asyncio
    async def test_handle_callback_default_returns_false(self, tmp_path):
        """Test default handle_callback returns False."""
        plugin = MinimalPlugin(tmp_path)
        query = MagicMock()
        context = MagicMock()

        result = await plugin.handle_callback(query, "action", ["param1"], context)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_callback_can_be_overridden(self, tmp_path):
        """Test handle_callback can be overridden to handle callbacks."""

        class CallbackHandlerPlugin(MinimalPlugin):
            received_action = None
            received_params = None

            async def handle_callback(self, query, action, params, context):
                CallbackHandlerPlugin.received_action = action
                CallbackHandlerPlugin.received_params = params
                return True

        plugin = CallbackHandlerPlugin(tmp_path)
        query = MagicMock()
        context = MagicMock()

        result = await plugin.handle_callback(
            query, "test_action", ["p1", "p2"], context
        )

        assert result is True
        assert CallbackHandlerPlugin.received_action == "test_action"
        assert CallbackHandlerPlugin.received_params == ["p1", "p2"]

    def test_get_api_router_default_none(self, tmp_path):
        """Test default get_api_router returns None."""
        plugin = MinimalPlugin(tmp_path)

        router = plugin.get_api_router()

        assert router is None

    def test_get_api_router_can_be_overridden(self, tmp_path):
        """Test get_api_router can return a router."""

        class APIPlugin(MinimalPlugin):
            def get_api_router(self):
                # Return a mock router
                return MagicMock()

        plugin = APIPlugin(tmp_path)

        router = plugin.get_api_router()

        assert router is not None

    def test_get_message_processor_default_none(self, tmp_path):
        """Test default get_message_processor returns None."""
        plugin = MinimalPlugin(tmp_path)

        processor = plugin.get_message_processor()

        assert processor is None

    def test_get_message_processor_can_be_overridden(self, tmp_path):
        """Test get_message_processor can return a processor function."""

        class MessagePlugin(MinimalPlugin):
            def get_message_processor(self):
                async def process(combined):
                    return True

                return process

        plugin = MessagePlugin(tmp_path)

        processor = plugin.get_message_processor()

        assert processor is not None
        assert callable(processor)

    def test_get_database_models_default_empty(self, tmp_path):
        """Test default get_database_models returns empty list."""
        plugin = MinimalPlugin(tmp_path)

        models = plugin.get_database_models()

        assert models == []
        assert isinstance(models, list)

    def test_get_database_models_can_be_overridden(self, tmp_path):
        """Test get_database_models can return model classes."""

        class Model1:
            pass

        class Model2:
            pass

        class ModelPlugin(MinimalPlugin):
            def get_database_models(self):
                return [Model1, Model2]

        plugin = ModelPlugin(tmp_path)

        models = plugin.get_database_models()

        assert len(models) == 2
        assert Model1 in models
        assert Model2 in models


class TestBasePluginConfigValue:
    """Tests for get_config_value utility method."""

    def test_simple_key(self, tmp_path):
        """Test getting a simple key from config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"setting": "value"}}

        result = plugin.get_config_value("setting")

        assert result == "value"

    def test_nested_key(self, tmp_path):
        """Test getting a nested key with dot notation."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"level1": {"level2": "deep_value"}}}

        result = plugin.get_config_value("level1.level2")

        assert result == "deep_value"

    def test_deeply_nested_key(self, tmp_path):
        """Test getting a deeply nested key."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"a": {"b": {"c": {"d": "very_deep"}}}}}

        result = plugin.get_config_value("a.b.c.d")

        assert result == "very_deep"

    def test_missing_key_returns_default(self, tmp_path):
        """Test missing key returns the default value."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"existing": "value"}}

        result = plugin.get_config_value("nonexistent", "my_default")

        assert result == "my_default"

    def test_missing_key_default_is_none(self, tmp_path):
        """Test missing key returns None when no default specified."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {}}

        result = plugin.get_config_value("missing")

        assert result is None

    def test_missing_nested_key_returns_default(self, tmp_path):
        """Test missing nested key returns default."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"level1": {"exists": True}}}

        result = plugin.get_config_value("level1.missing.deep", "fallback")

        assert result == "fallback"

    def test_empty_config(self, tmp_path):
        """Test getting value from empty config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {}

        result = plugin.get_config_value("anything", "default")

        assert result == "default"

    def test_no_config_section(self, tmp_path):
        """Test getting value when config section doesn't exist."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"other": "data"}

        result = plugin.get_config_value("key", "default")

        assert result == "default"

    def test_config_value_is_list(self, tmp_path):
        """Test getting a list value from config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"items": [1, 2, 3]}}

        result = plugin.get_config_value("items")

        assert result == [1, 2, 3]

    def test_config_value_is_dict(self, tmp_path):
        """Test getting a dict value from config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"nested": {"a": 1, "b": 2}}}

        result = plugin.get_config_value("nested")

        assert result == {"a": 1, "b": 2}

    def test_config_value_is_int(self, tmp_path):
        """Test getting an int value from config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"count": 42}}

        result = plugin.get_config_value("count")

        assert result == 42

    def test_config_value_is_bool(self, tmp_path):
        """Test getting a bool value from config."""
        plugin = MinimalPlugin(tmp_path)
        plugin._config = {"config": {"enabled": True}}

        result = plugin.get_config_value("enabled")

        assert result is True


class TestBasePluginRepr:
    """Tests for plugin string representation."""

    def test_repr_contains_class_name(self, tmp_path):
        """Test repr contains class name."""
        plugin = MinimalPlugin(tmp_path)

        repr_str = repr(plugin)

        assert "MinimalPlugin" in repr_str

    def test_repr_contains_plugin_name(self, tmp_path):
        """Test repr contains plugin name from metadata."""
        plugin = MinimalPlugin(tmp_path, name="my-test-plugin")

        repr_str = repr(plugin)

        assert "my-test-plugin" in repr_str

    def test_repr_contains_state(self, tmp_path):
        """Test repr contains current state."""
        plugin = MinimalPlugin(tmp_path)

        repr_str = repr(plugin)

        assert "unloaded" in repr_str

    def test_repr_updates_with_state_change(self, tmp_path):
        """Test repr reflects state changes."""
        plugin = MinimalPlugin(tmp_path)
        plugin.state = PluginState.ACTIVE

        repr_str = repr(plugin)

        assert "active" in repr_str

    def test_repr_format(self, tmp_path):
        """Test repr has expected format."""
        plugin = MinimalPlugin(tmp_path, name="test-plugin")

        repr_str = repr(plugin)

        # Should match format: <ClassName name='test-plugin' state=unloaded>
        assert repr_str.startswith("<MinimalPlugin")
        assert "name=" in repr_str
        assert "state=" in repr_str
        assert repr_str.endswith(">")


class TestBasePluginStateManagement:
    """Tests for plugin state management."""

    def test_state_can_be_changed(self, tmp_path):
        """Test plugin state can be modified."""
        plugin = MinimalPlugin(tmp_path)

        plugin.state = PluginState.LOADING
        assert plugin.state == PluginState.LOADING

        plugin.state = PluginState.LOADED
        assert plugin.state == PluginState.LOADED

        plugin.state = PluginState.ACTIVE
        assert plugin.state == PluginState.ACTIVE

    def test_error_can_be_set(self, tmp_path):
        """Test error message can be set."""
        plugin = MinimalPlugin(tmp_path)

        plugin._error = "Something went wrong"
        plugin.state = PluginState.ERROR

        assert plugin.error == "Something went wrong"
        assert plugin.state == PluginState.ERROR

    def test_config_can_be_set(self, tmp_path):
        """Test config can be set externally."""
        plugin = MinimalPlugin(tmp_path)

        plugin._config = {"config": {"key": "value"}, "metadata": {"version": "1.0"}}

        assert plugin.config["config"]["key"] == "value"


class TestPluginIntegration:
    """Integration tests combining multiple features."""

    @pytest.mark.asyncio
    async def test_complete_plugin_implementation(self, tmp_path):
        """Test a fully-featured plugin implementation."""

        class CompletePlugin(BasePlugin):
            load_called = False
            activate_called = False

            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="complete-plugin",
                    version="2.0.0",
                    description="A complete plugin",
                    author="Test Author",
                    requires=[],
                    dependencies=[],
                    priority=50,
                )

            @property
            def capabilities(self) -> PluginCapabilities:
                return PluginCapabilities(
                    services=["complete_service"],
                    commands=["/complete"],
                    callbacks=["complete:action"],
                    api_routes=True,
                    message_handler=True,
                )

            async def on_load(self, container):
                CompletePlugin.load_called = True
                self.register_services(container)
                return True

            async def on_activate(self, app):
                CompletePlugin.activate_called = True
                return True

            def register_services(self, container):
                container.register("complete_service", lambda: "service_instance")

            def get_command_handlers(self):
                return [MagicMock()]

            def get_callback_prefix(self):
                return "complete"

            async def handle_callback(self, query, action, params, context):
                return action == "action"

            def get_api_router(self):
                return MagicMock()

            def get_message_processor(self):
                async def process(combined):
                    return True

                return process

        CompletePlugin.load_called = False
        CompletePlugin.activate_called = False

        plugin = CompletePlugin(tmp_path)
        plugin._config = {"config": {"timeout": 30}}

        # Check metadata
        assert plugin.metadata.name == "complete-plugin"
        assert plugin.metadata.priority == 50

        # Check capabilities
        assert "complete_service" in plugin.capabilities.services
        assert plugin.capabilities.api_routes is True

        # Check requirements
        ok, error = plugin.check_requirements()
        assert ok is True

        # Run lifecycle
        container = MagicMock()
        app = MagicMock()

        await plugin.on_load(container)
        assert CompletePlugin.load_called
        container.register.assert_called()

        await plugin.on_activate(app)
        assert CompletePlugin.activate_called

        # Check handlers
        assert len(plugin.get_command_handlers()) == 1
        assert plugin.get_callback_prefix() == "complete"
        assert plugin.get_api_router() is not None
        assert plugin.get_message_processor() is not None

        # Check config
        assert plugin.get_config_value("timeout") == 30

        # Check repr
        repr_str = repr(plugin)
        assert "CompletePlugin" in repr_str

    @pytest.mark.asyncio
    async def test_plugin_with_dependencies(self, tmp_path):
        """Test plugin declaring dependencies."""

        class DependentPlugin(MinimalPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="dependent-plugin",
                    version="1.0.0",
                    description="Depends on other plugins",
                    dependencies=["core-plugin", "auth-plugin"],
                )

        plugin = DependentPlugin(tmp_path)

        assert plugin.metadata.dependencies == ["core-plugin", "auth-plugin"]
        assert len(plugin.metadata.dependencies) == 2
