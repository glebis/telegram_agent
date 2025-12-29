"""
Defaults loader for configuration from YAML files.

Provides a hierarchical configuration system:
1. config/defaults.yaml - Base defaults (checked into repo)
2. config/settings.yaml - User overrides (gitignored)
3. Environment variables - Final override (highest priority)
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Cache for loaded config
_config_cache: Optional[Dict[str, Any]] = None
_config_path: Optional[Path] = None


def get_project_root() -> Path:
    """Get the project root directory."""
    # Navigate up from src/core/defaults_loader.py
    return Path(__file__).parent.parent.parent


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents as a dictionary."""
    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
        return content if content else {}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def expand_path(path: str) -> str:
    """Expand ~ and environment variables in a path."""
    if not path:
        return path
    return os.path.expanduser(os.path.expandvars(path))


def get_nested(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get a nested value from config using dot notation.

    Example:
        get_nested(config, "timeouts.claude_query_timeout", 300)
    """
    keys = key_path.split(".")
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def load_defaults(
    defaults_path: Optional[Path] = None,
    settings_path: Optional[Path] = None,
    reload: bool = False,
) -> Dict[str, Any]:
    """
    Load configuration from YAML files.

    Args:
        defaults_path: Path to defaults.yaml (optional, uses project default)
        settings_path: Path to settings.yaml (optional, uses project default)
        reload: Force reload even if cached

    Returns:
        Merged configuration dictionary
    """
    global _config_cache, _config_path

    project_root = get_project_root()

    if defaults_path is None:
        defaults_path = project_root / "config" / "defaults.yaml"

    if settings_path is None:
        settings_path = project_root / "config" / "settings.yaml"

    # Return cached config if available and not forcing reload
    if not reload and _config_cache is not None and _config_path == defaults_path:
        return _config_cache

    # Load base defaults
    config = load_yaml_file(defaults_path)

    # Merge user settings (if exists)
    user_settings = load_yaml_file(settings_path)
    if user_settings:
        config = deep_merge(config, user_settings)

    # Cache the result
    _config_cache = config
    _config_path = defaults_path

    return config


def get_config_value(
    key_path: str,
    default: Any = None,
    expand_paths: bool = False,
) -> Any:
    """
    Get a configuration value using dot notation.

    Args:
        key_path: Dot-separated path like "timeouts.claude_query_timeout"
        default: Default value if key not found
        expand_paths: If True and value is a string, expand ~ and env vars

    Returns:
        Configuration value or default
    """
    config = load_defaults()
    value = get_nested(config, key_path, default)

    if expand_paths and isinstance(value, str):
        value = expand_path(value)

    return value


# Convenience functions for common config sections
def get_timeout(name: str, default: float = 30.0) -> float:
    """Get a timeout value from config."""
    return float(get_config_value(f"timeouts.{name}", default))


def get_limit(name: str, default: int = 100) -> int:
    """Get a limit value from config."""
    return int(get_config_value(f"limits.{name}", default))


def get_path(name: str, default: str = "") -> str:
    """Get an expanded path from config."""
    return get_config_value(f"paths.{name}", default, expand_paths=True)


def get_model(name: str, default: str = "") -> str:
    """Get a model name from config."""
    return get_config_value(f"models.{name}", default)


def get_message(name: str, default: str = "") -> str:
    """Get a message template from config."""
    return get_config_value(f"messages.{name}", default)


def get_reaction(name: str, default: str = "") -> str:
    """Get a reaction emoji from config."""
    return get_config_value(f"reactions.{name}", default)


def get_api_url(name: str, default: str = "") -> str:
    """Get an API URL from config."""
    return get_config_value(f"api.{name}", default)


def clear_cache() -> None:
    """Clear the configuration cache (useful for testing)."""
    global _config_cache, _config_path
    _config_cache = None
    _config_path = None
