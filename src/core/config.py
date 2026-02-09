"""
Application configuration using Pydantic Settings with profile support.

Centralizes all configuration with environment variable support.
Loading priority (lowest to highest):
  1. config/defaults.yaml  - base defaults (checked into repo)
  2. config/settings.yaml  - user overrides (gitignored)
  3. config/profiles/{env}.yaml - environment-specific profile
  4. Environment variables / .env
"""

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Project root for finding config files
PROJECT_ROOT = Path(__file__).parent.parent.parent


def load_yaml_config(path: Path) -> Dict[str, Any]:
    """Load a YAML configuration file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load config from {path}: {e}")
        return {}


def deep_merge(base: Dict, override: Dict) -> Dict:
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


def load_profile_config(environment: str) -> Dict[str, Any]:
    """
    Load configuration for a specific environment profile.

    Priority (lowest to highest):
    1. Default config (config/defaults.yaml)
    2. User settings (config/settings.yaml, gitignored)
    3. Profile-specific config (config/profiles/{environment}.yaml)
    4. Environment variables (handled by Pydantic Settings, not here)
    """
    config = {}

    # 1. Load defaults first
    defaults_path = PROJECT_ROOT / "config" / "defaults.yaml"
    defaults = load_yaml_config(defaults_path)
    if defaults:
        config = deep_merge(config, defaults)

    # 2. Load user settings (gitignored)
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    settings = load_yaml_config(settings_path)
    if settings:
        config = deep_merge(config, settings)

    # 3. Load environment-specific profile
    profile_path = PROJECT_ROOT / "config" / "profiles" / f"{environment}.yaml"
    profile = load_yaml_config(profile_path)
    if profile:
        config = deep_merge(config, profile)
        logger.info(f"Loaded {environment} profile from {profile_path}")
    else:
        logger.debug(f"No profile found for {environment}, using defaults")

    return config


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_webhook_url: Optional[str] = None

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/telegram_agent.db"

    # Python executable path (for subprocess calls)
    # Defaults to sys.executable to be platform-independent
    python_executable: str = sys.executable

    # Working directories - Obsidian vault paths
    vault_path: str = "~/Research/vault"
    vault_temp_images_dir: str = "~/Research/vault/temp_images"
    vault_temp_docs_dir: str = "~/Research/vault/temp_docs"
    vault_people_dir: str = "~/Research/vault/People"

    # Aliases for backwards compatibility
    claude_code_work_dir: str = "~/Research/vault"
    temp_dir: str = "~/Research/vault/temp_images"

    # Timeouts (seconds)
    buffer_timeout: float = 2.5
    claude_query_timeout: int = 300
    session_idle_timeout_minutes: int = 60
    claude_session_timeout_seconds: int = 1800  # 30 minutes overall timeout

    # Limits
    max_buffer_messages: int = 10
    max_buffer_size: int = 20
    max_buffer_wait: float = 30.0

    # API Keys (optional, loaded from env)
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Dedicated secret for API key derivation (HMAC-SHA256).
    # When set, API keys are derived from this secret instead of
    # TELEGRAM_WEBHOOK_SECRET.  Strongly recommended for production.
    api_secret_key: Optional[str] = None

    # STT (Speech-to-Text) provider chain
    # Comma-separated list, tried in order. Options: groq, local_whisper
    stt_providers: str = "groq,local_whisper"

    # Environment
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Claude Code
    claude_code_model: str = "opus"  # Changed to Opus 4.6 for better quality
    claude_allowed_tools: Optional[str] = (
        None  # Comma-separated, e.g. "Read,Write,Edit,Glob,Grep,Bash"
    )
    claude_disallowed_tools: Optional[str] = (
        None  # Comma-separated, e.g. "WebFetch,WebSearch"
    )

    # Agent backend selection: "claude_code" or "opencode"
    ai_agent_backend: str = "claude_code"

    # OpenCode settings
    opencode_model: str = "anthropic:claude-sonnet-4-20250514"
    opencode_work_dir: Optional[str] = None  # Defaults to claude_code_work_dir if unset

    # Completion Reactions
    # Options: "emoji", "sticker", "animation", "none"
    completion_reaction_type: str = "emoji"
    # For emoji: single emoji or list comma-separated
    # For sticker/animation: file_id from Telegram or file path
    completion_reaction_value: str = "✅"
    # Probability of sending reaction (0.0-1.0, 1.0 = always)
    completion_reaction_probability: float = 1.0

    # ngrok
    ngrok_authtoken: Optional[str] = None
    ngrok_port: int = 8000
    ngrok_region: str = "us"

    # Tunnel provider
    tunnel_provider: Optional[str] = None
    tunnel_port: int = 8000

    # Cloudflare Tunnel
    cf_tunnel_name: Optional[str] = None
    cf_credentials_file: Optional[str] = None
    cf_config_file: Optional[str] = None

    # Tailscale Funnel
    tailscale_hostname: Optional[str] = None

    # Heartbeat
    heartbeat_chat_ids: Optional[str] = None

    # Authorization tiers
    owner_user_id: Optional[int] = None  # Telegram user ID of the bot owner
    admin_user_ids: str = ""  # Comma-separated Telegram user IDs for admin tier

    # User allowlist
    allowed_user_ids: str = ""  # Comma-separated Telegram user IDs. Empty = allow all.

    # Plugin restrictions
    plugin_allowlist: str = ""  # Comma-separated plugin IDs. Empty = allow all.
    plugin_safe_mode: bool = False  # If true, only load builtin plugins.

    # Request hardening
    rate_limit_requests_per_minute: int = 60  # Per-IP rate limit for webhook + admin
    user_rate_limit_rpm: int = 30  # Per-user (Telegram user_id) rate limit
    user_rate_limit_privileged_rpm: int = 120  # Per-user rate limit for OWNER/ADMIN
    max_request_body_bytes: int = 1048576  # 1 MB max request body
    webhook_max_concurrent: int = 20  # Max concurrent webhook processing tasks

    # Media pipeline
    allowed_media_mimes: str = (
        "image/jpeg,image/png,image/webp"  # Comma-separated allowed MIME types
    )
    media_sandbox_timeout: int = 30  # Seconds before sandboxed subprocesses are killed
    media_allowed_roots: str = "data/,logs/"  # Comma-separated dirs for outbound files

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars


# Global profile config cache
_profile_config: Optional[Dict[str, Any]] = None


def get_profile_config() -> Dict[str, Any]:
    """Get the loaded profile configuration (cached)."""
    global _profile_config
    if _profile_config is None:
        environment = os.getenv("ENVIRONMENT", "development").lower()
        _profile_config = load_profile_config(environment)
    return _profile_config


def get_config_value(path: str, default: Any = None, expand_paths: bool = False) -> Any:
    """
    Get a configuration value by dot-separated path.

    Args:
        path: Dot-separated path like "timeouts.claude_query_timeout"
        default: Default value if key not found
        expand_paths: If True and value is a string, expand ~ and env vars

    Example:
        get_config_value("timeouts.buffer_timeout", 2.5)
        get_config_value("paths.vault_path", expand_paths=True)
    """
    config = get_profile_config()
    keys = path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    if expand_paths and isinstance(value, str):
        value = expand_path(value)
    return value


def clear_cache() -> None:
    """Clear the profile configuration cache (useful for testing)."""
    global _profile_config
    _profile_config = None


def load_defaults(
    defaults_path: Optional[Path] = None,
    settings_path: Optional[Path] = None,
    reload: bool = False,
) -> Dict[str, Any]:
    """
    Load configuration from YAML files.

    Backward-compatible wrapper around get_profile_config(). When called
    without arguments, returns the same cached config. Custom paths and
    reload=True bypass the cache for testing.

    Args:
        defaults_path: Path to defaults.yaml (optional, uses project default)
        settings_path: Path to settings.yaml (optional, uses project default)
        reload: Force reload even if cached

    Returns:
        Merged configuration dictionary
    """
    global _profile_config

    # If custom paths given, build config from scratch (for tests)
    if defaults_path is not None or settings_path is not None:
        project_root = PROJECT_ROOT

        if defaults_path is None:
            defaults_path = project_root / "config" / "defaults.yaml"
        if settings_path is None:
            settings_path = project_root / "config" / "settings.yaml"

        config = load_yaml_config(defaults_path)
        user_settings = load_yaml_config(settings_path)
        if user_settings:
            config = deep_merge(config, user_settings)
        return config

    # Standard path: use the profile config cache
    if reload:
        _profile_config = None

    return get_profile_config()


# -- Convenience functions for common config sections ----------------------


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


def get_message(name: str, default: str = "", **kwargs: Any) -> str:
    """Get a message template, delegating to the i18n framework.

    Backward-compatible: callers that used get_message("error_prefix")
    now get the value from locales/en.yaml under messages.error_prefix.
    Falls back to config/defaults.yaml if the i18n key is missing.
    """
    from .i18n import t

    result = t(f"messages.{name}", "en", **kwargs)
    # If t() returned the raw key (missing), fall back to config
    if result == f"messages.{name}":
        return get_config_value(f"messages.{name}", default)
    return result


def get_reaction(name: str, default: str = "") -> str:
    """Get a reaction emoji from config."""
    return get_config_value(f"reactions.{name}", default)


def get_api_url(name: str, default: str = "") -> str:
    """Get an API URL from config."""
    return get_config_value(f"api.{name}", default)


# -- Pydantic Settings helpers ---------------------------------------------


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_python_executable() -> str:
    """Get the configured Python executable path."""
    return get_settings().python_executable


def is_development() -> bool:
    """Check if running in development mode."""
    return get_settings().environment.lower() == "development"


def is_production() -> bool:
    """Check if running in production mode."""
    return get_settings().environment.lower() == "production"


def is_testing() -> bool:
    """Check if running in testing mode."""
    return get_settings().environment.lower() == "testing"
