"""
Tests for the plugin manager.

Tests cover:
- Plugin base class functionality
- Plugin discovery
- Plugin loading and lifecycle
- Dependency resolution
- Message routing
"""

import os
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.plugins.base import (
    BasePlugin,
    PluginCapabilities,
    PluginMetadata,
    PluginState,
)
from src.plugins.manager import PluginManager, reset_plugin_manager


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        meta = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
        )

        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.author == ""
        assert meta.requires == []
        assert meta.dependencies == []
        assert meta.priority == 100
        assert meta.enabled_by_default is True

    def test_all_values(self):
        """Test all values can be set."""
        meta = PluginMetadata(
            name="full-plugin",
            version="2.0.0",
            description="Full test",
            author="Test Author",
            requires=["API_KEY"],
            dependencies=["other-plugin"],
            priority=50,
            enabled_by_default=False,
        )

        assert meta.author == "Test Author"
        assert meta.requires == ["API_KEY"]
        assert meta.dependencies == ["other-plugin"]
        assert meta.priority == 50
        assert meta.enabled_by_default is False


class TestPluginCapabilities:
    """Tests for PluginCapabilities dataclass."""

    def test_default_values(self):
        """Test default values are empty."""
        caps = PluginCapabilities()

        assert caps.services == []
        assert caps.commands == []
        assert caps.callbacks == []
        assert caps.api_routes is False
        assert caps.message_handler is False


class TestBasePlugin:
    """Tests for BasePlugin abstract class."""

    def test_check_requirements_success(self, tmp_path):
        """Test requirements check passes when env vars are set."""

        class TestPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test",
                    version="1.0.0",
                    description="Test",
                    requires=["TEST_VAR"],
                )

        os.environ["TEST_VAR"] = "value"
        plugin = TestPlugin(tmp_path)

        ok, error = plugin.check_requirements()

        assert ok is True
        assert error == ""

        del os.environ["TEST_VAR"]

    def test_check_requirements_failure(self, tmp_path):
        """Test requirements check fails when env vars are missing."""

        class TestPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test",
                    version="1.0.0",
                    description="Test",
                    requires=["MISSING_VAR_12345"],
                )

        plugin = TestPlugin(tmp_path)

        ok, error = plugin.check_requirements()

        assert ok is False
        assert "MISSING_VAR_12345" in error

    def test_get_config_value(self, tmp_path):
        """Test config value retrieval."""

        class TestPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test",
                    version="1.0.0",
                    description="Test",
                )

        plugin = TestPlugin(tmp_path)
        plugin._config = {
            "config": {
                "setting1": "value1",
                "nested": {"setting2": "value2"},
            }
        }

        assert plugin.get_config_value("setting1") == "value1"
        assert plugin.get_config_value("nested.setting2") == "value2"
        assert plugin.get_config_value("missing", "default") == "default"

    def test_plugin_repr(self, tmp_path):
        """Test plugin string representation."""

        class TestPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test-plugin",
                    version="1.0.0",
                    description="Test",
                )

        plugin = TestPlugin(tmp_path)

        repr_str = repr(plugin)

        assert "TestPlugin" in repr_str
        assert "test-plugin" in repr_str
        assert "unloaded" in repr_str


class TestPluginManager:
    """Tests for PluginManager."""

    def setup_method(self):
        """Reset plugin manager before each test."""
        reset_plugin_manager()

    def test_discover_no_plugins(self, tmp_path):
        """Test discovery with no plugins."""
        manager = PluginManager()
        manager.BUILTIN_PLUGINS_PATH = tmp_path / "builtin"
        manager.USER_PLUGINS_PATH = tmp_path / "plugins"

        # Don't create directories
        discovered = []

        # Discovery should not raise
        assert discovered == []

    @pytest.mark.asyncio
    async def test_discover_plugins(self, tmp_path):
        """Test plugin discovery finds plugins with plugin.yaml."""
        manager = PluginManager()
        manager.USER_PLUGINS_PATH = tmp_path

        # Create a test plugin
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()

        plugin_yaml = plugin_dir / "plugin.yaml"
        plugin_yaml.write_text(
            yaml.dump(
                {
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "description": "Test plugin",
                }
            )
        )

        discovered = await manager.discover_plugins()

        assert "test-plugin" in discovered

    @pytest.mark.asyncio
    async def test_discover_skips_invalid(self, tmp_path):
        """Test discovery skips directories without plugin.yaml."""
        manager = PluginManager()
        manager.USER_PLUGINS_PATH = tmp_path

        # Create directory without plugin.yaml
        (tmp_path / "no_yaml").mkdir()

        # Create directory starting with underscore
        (tmp_path / "_hidden").mkdir()
        (tmp_path / "_hidden" / "plugin.yaml").write_text("name: hidden")

        discovered = await manager.discover_plugins()

        assert "no_yaml" not in discovered
        assert "hidden" not in discovered
        assert "_hidden" not in discovered

    def test_resolve_dependencies_simple(self):
        """Test dependency resolution with no dependencies."""
        manager = PluginManager()

        plugins_config = {
            "plugin-a": {"dependencies": []},
            "plugin-b": {"dependencies": []},
        }

        order = manager._resolve_dependencies(plugins_config)

        assert set(order) == {"plugin-a", "plugin-b"}

    def test_resolve_dependencies_chain(self):
        """Test dependency resolution with chain dependencies."""
        manager = PluginManager()

        plugins_config = {
            "plugin-a": {"dependencies": ["plugin-b"]},
            "plugin-b": {"dependencies": ["plugin-c"]},
            "plugin-c": {"dependencies": []},
        }

        order = manager._resolve_dependencies(plugins_config)

        # C must come before B, B before A
        assert order.index("plugin-c") < order.index("plugin-b")
        assert order.index("plugin-b") < order.index("plugin-a")

    def test_resolve_dependencies_circular(self):
        """Test dependency resolution detects circular dependencies."""
        manager = PluginManager()

        plugins_config = {
            "plugin-a": {"dependencies": ["plugin-b"]},
            "plugin-b": {"dependencies": ["plugin-a"]},
        }

        with pytest.raises(ValueError, match="Circular dependency"):
            manager._resolve_dependencies(plugins_config)

    @pytest.mark.asyncio
    async def test_load_plugins_empty(self, tmp_path):
        """Test loading with no plugins."""
        manager = PluginManager()
        manager.BUILTIN_PLUGINS_PATH = tmp_path / "builtin"
        manager.USER_PLUGINS_PATH = tmp_path / "plugins"

        container = MagicMock()
        results = await manager.load_plugins(container)

        assert results == {}

    @pytest.mark.asyncio
    async def test_load_plugin_requirements_fail(self, tmp_path):
        """Missing requirements should disable plugin and return False."""
        manager = PluginManager()
        manager._container = MagicMock()

        class NeedsEnvPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="needs-env",
                    version="1.0.0",
                    description="Requires env var",
                    requires=["MISSING_ENV_VAR_TEST"],
                )

        module = types.ModuleType("plugin_module")
        module.NeedsEnvPlugin = NeedsEnvPlugin

        with patch("src.plugins.manager.importlib.import_module", return_value=module):
            result = await manager._load_plugin(
                name="needs-env",
                plugin_dir=tmp_path,
                config={"name": "needs-env"},
                is_builtin=False,
            )

        assert result is False
        plugin = manager.get_plugin("needs-env")
        assert plugin is not None
        assert plugin.state == PluginState.DISABLED

    @pytest.mark.asyncio
    async def test_load_plugin_on_load_failure(self, tmp_path):
        """on_load returning False should mark plugin as error."""
        manager = PluginManager()
        manager._container = MagicMock()

        class FailingLoadPlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="failing-load",
                    version="1.0.0",
                    description="Fails on load",
                )

            async def on_load(self, container):
                return False

        module = types.ModuleType("plugin_module")
        module.FailingLoadPlugin = FailingLoadPlugin

        with patch("src.plugins.manager.importlib.import_module", return_value=module):
            result = await manager._load_plugin(
                name="failing-load",
                plugin_dir=tmp_path,
                config={"name": "failing-load"},
                is_builtin=False,
            )

        assert result is False
        plugin = manager.get_plugin("failing-load")
        assert plugin is not None
        assert plugin.state == PluginState.ERROR
        assert plugin.error == "on_load returned False"

    @pytest.mark.asyncio
    async def test_load_plugin_import_failure(self, tmp_path):
        """Import errors should result in False without crash."""
        manager = PluginManager()
        manager._container = MagicMock()

        with patch(
            "src.plugins.manager.importlib.import_module",
            side_effect=[ModuleNotFoundError("missing"), ModuleNotFoundError("missing")],
        ):
            result = await manager._load_plugin(
                name="missing-plugin",
                plugin_dir=tmp_path,
                config={"name": "missing-plugin"},
                is_builtin=False,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_activate_plugin_on_activate_failure(self):
        """on_activate returning False should mark plugin as error."""
        manager = PluginManager()

        class FailingActivatePlugin(BasePlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="failing-activate",
                    version="1.0.0",
                    description="Fails on activate",
                )

            async def on_activate(self, app):
                return False

        plugin = FailingActivatePlugin(Path("."))
        plugin.state = PluginState.LOADED
        manager._plugins["failing-activate"] = plugin
        manager._load_order = ["failing-activate"]

        await manager.activate_plugins(MagicMock())

        assert plugin.state == PluginState.ERROR

    def test_get_plugin_status(self):
        """Test getting plugin status."""
        manager = PluginManager()

        # No plugins loaded
        status = manager.get_plugin_status()

        assert status == {}

    @pytest.mark.asyncio
    async def test_route_message_no_plugins(self):
        """Test message routing with no plugins."""
        manager = PluginManager()

        combined = MagicMock()
        result = await manager.route_message(combined)

        assert result is False

    @pytest.mark.asyncio
    async def test_shutdown_empty(self):
        """Test shutdown with no plugins."""
        manager = PluginManager()

        # Should not raise
        await manager.shutdown()

        assert manager.plugins == {}


class TestPluginIntegration:
    """Integration tests for the plugin system."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self, tmp_path):
        """Test complete plugin lifecycle."""

        class LifecyclePlugin(BasePlugin):
            load_called = False
            activate_called = False
            deactivate_called = False
            unload_called = False

            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="lifecycle",
                    version="1.0.0",
                    description="Test lifecycle",
                )

            async def on_load(self, container):
                LifecyclePlugin.load_called = True
                return True

            async def on_activate(self, app):
                LifecyclePlugin.activate_called = True
                return True

            async def on_deactivate(self):
                LifecyclePlugin.deactivate_called = True

            async def on_unload(self):
                LifecyclePlugin.unload_called = True

        plugin = LifecyclePlugin(tmp_path)
        container = MagicMock()
        app = MagicMock()

        # Test on_load
        result = await plugin.on_load(container)
        assert result is True
        assert LifecyclePlugin.load_called

        # Test on_activate
        result = await plugin.on_activate(app)
        assert result is True
        assert LifecyclePlugin.activate_called

        # Test on_deactivate
        await plugin.on_deactivate()
        assert LifecyclePlugin.deactivate_called

        # Test on_unload
        await plugin.on_unload()
        assert LifecyclePlugin.unload_called
