"""
Application configuration using Pydantic Settings.

Centralizes all configuration with environment variable support.
"""

import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


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

    # Working directories
    claude_code_work_dir: str = "~/Research/vault"
    temp_dir: str = "~/Research/vault/temp_images"

    # Timeouts (seconds)
    buffer_timeout: float = 2.5
    claude_query_timeout: int = 300
    session_idle_timeout_minutes: int = 60

    # Limits
    max_buffer_messages: int = 10
    max_buffer_wait: float = 30.0

    # API Keys (optional, loaded from env)
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Environment
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Claude Code
    claude_code_model: str = "sonnet"

    # ngrok
    ngrok_authtoken: Optional[str] = None
    ngrok_port: int = 8000
    ngrok_region: str = "us"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_python_executable() -> str:
    """Get the configured Python executable path."""
    return get_settings().python_executable
