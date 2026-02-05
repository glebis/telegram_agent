"""
Application configuration using Pydantic Settings with profile support.

Centralizes all configuration with environment variable support.
Profile loading: ENVIRONMENT -> config/profiles/{env}.yaml -> defaults.yaml -> .env
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


def load_profile_config(environment: str) -> Dict[str, Any]:
    """
    Load configuration for a specific environment profile.

    Priority (highest to lowest):
    1. Environment variables
    2. Profile-specific config (config/profiles/{environment}.yaml)
    3. Default config (config/defaults.yaml)
    """
    config = {}

    # Load defaults first
    defaults_path = PROJECT_ROOT / "config" / "defaults.yaml"
    defaults = load_yaml_config(defaults_path)
    if defaults:
        config = deep_merge(config, defaults)

    # Load environment-specific profile
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
    max_buffer_wait: float = 30.0

    # API Keys (optional, loaded from env)
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # STT (Speech-to-Text) provider chain
    # Comma-separated list, tried in order. Options: groq, local_whisper
    stt_providers: str = "groq,local_whisper"

    # Environment
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Claude Code
    claude_code_model: str = "sonnet"
    claude_allowed_tools: Optional[str] = (
        None  # Comma-separated, e.g. "Read,Write,Edit,Glob,Grep,Bash"
    )
    claude_disallowed_tools: Optional[str] = (
        None  # Comma-separated, e.g. "WebFetch,WebSearch"
    )

    # Completion Reactions
    # Options: "emoji", "sticker", "animation", "none"
    completion_reaction_type: str = "emoji"
    # For emoji: single emoji or list comma-separated (e.g., "✨,🎉,👍")
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

    # User allowlist
    allowed_user_ids: str = ""  # Comma-separated Telegram user IDs. Empty = allow all.

    # Plugin restrictions
    plugin_allowlist: str = ""  # Comma-separated plugin IDs. Empty = allow all.
    plugin_safe_mode: bool = False  # If true, only load builtin plugins.

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


def get_config_value(path: str, default: Any = None) -> Any:
    """
    Get a configuration value by dot-separated path.

    Example:
        get_config_value("timeouts.buffer_timeout", 2.5)
        get_config_value("bot.verbose_errors", False)
    """
    config = get_profile_config()
    keys = path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


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
