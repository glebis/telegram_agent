"""
Backward-compatibility shim -- all functionality moved to src.core.config.

Import from src.core.config instead.
"""

from pathlib import Path

from .config import (
    PROJECT_ROOT,
    clear_cache,
    deep_merge,
    expand_path,
    get_api_url,
    get_config_value,
    get_limit,
    get_message,
    get_model,
    get_nested,
    get_path,
    get_reaction,
    get_timeout,
    load_defaults,
    load_yaml_config,
)


def get_project_root() -> Path:
    """Get the project root directory."""
    return PROJECT_ROOT


def load_yaml_file(file_path) -> dict:
    """Backward compat -- delegates to config.load_yaml_config."""
    return load_yaml_config(
        Path(file_path) if not isinstance(file_path, Path) else file_path
    )


__all__ = [
    "clear_cache",
    "deep_merge",
    "expand_path",
    "get_api_url",
    "get_config_value",
    "get_limit",
    "get_message",
    "get_model",
    "get_nested",
    "get_path",
    "get_project_root",
    "get_reaction",
    "get_timeout",
    "load_defaults",
    "load_yaml_file",
]
