"""
Plugin System for Verity.

This module provides a plugin architecture for extending bot functionality
without modifying core code.

Usage:
    from src.plugins import get_plugin_manager, BasePlugin

    # Get the plugin manager
    manager = get_plugin_manager()

    # Load plugins from plugins/ directory
    await manager.load_plugins(container)

    # Activate plugins (register handlers)
    await manager.activate_plugins(app)

Plugin authors should subclass BasePlugin and implement the required methods.
See plugins/claude_code/ for a reference implementation.
"""

from .base import BasePlugin, PluginCapabilities, PluginMetadata, PluginState
from .manager import PluginManager, get_plugin_manager

__all__ = [
    "BasePlugin",
    "PluginMetadata",
    "PluginCapabilities",
    "PluginState",
    "PluginManager",
    "get_plugin_manager",
]
