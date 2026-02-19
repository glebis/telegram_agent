"""
Typed configuration domain objects.

Replaces raw dict/env access with Pydantic-validated, immutable config classes:
- PersonalityProfile / AccountabilityConfig  (accountability_service.py)
- ModeConfig / ModeCatalog                   (mode_manager.py)
- TrailSchedule                              (trail_scheduler.py)
"""

import logging
from datetime import time
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Accountability Partner
# ---------------------------------------------------------------------------

VALID_CELEBRATION_STYLES = {"quiet", "moderate", "enthusiastic"}


class PersonalityProfile(BaseModel):
    """Single accountability-partner personality preset."""

    model_config = ConfigDict(frozen=True)

    voice: str
    emotion: str
    struggle_threshold: int
    celebration_style: str

    @field_validator("struggle_threshold")
    @classmethod
    def threshold_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("struggle_threshold must be >= 0")
        return v

    @field_validator("celebration_style")
    @classmethod
    def celebration_style_valid(cls, v: str) -> str:
        if v not in VALID_CELEBRATION_STYLES:
            raise ValueError(
                f"celebration_style must be one of {VALID_CELEBRATION_STYLES}, got '{v}'"
            )
        return v


class AccountabilityConfig(BaseModel):
    """Collection of personality profiles with a default."""

    model_config = ConfigDict(frozen=True)

    personalities: Dict[str, PersonalityProfile]
    default_personality: str = "supportive"

    def get_personality(self, name: str) -> Optional[PersonalityProfile]:
        """Get a personality by name, falling back to default."""
        if name in self.personalities:
            return self.personalities[name]
        if self.default_personality in self.personalities:
            return self.personalities[self.default_personality]
        return None


# ---------------------------------------------------------------------------
# Mode Catalog (image analysis modes)
# ---------------------------------------------------------------------------


class ModePreset(BaseModel):
    """A preset within a mode."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: Optional[str] = None
    prompt: str


class ModeConfig(BaseModel):
    """A single image-analysis mode."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: Optional[str] = None
    prompt: str = "Describe this image."
    embed: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    presets: List[ModePreset] = []


class ModeSettings(BaseModel):
    """Global settings for the mode system."""

    model_config = ConfigDict(frozen=True)

    similarity_threshold: float = 0.7
    max_similar_images: int = 5
    image_max_size: int = 1024
    image_quality: int = 85
    supported_formats: List[str] = ["jpg", "jpeg", "png", "webp"]


class ModeCatalog(BaseModel):
    """All modes, aliases, and global settings."""

    model_config = ConfigDict(frozen=True)

    modes: Dict[str, ModeConfig]
    aliases: Dict[str, str] = {}
    settings: ModeSettings = ModeSettings()

    def get_mode(self, name: str) -> Optional[ModeConfig]:
        return self.modes.get(name)

    def available_modes(self) -> List[str]:
        return list(self.modes.keys())

    def resolve_alias(self, command: str) -> Optional[str]:
        return self.aliases.get(command)


# ---------------------------------------------------------------------------
# Trail Schedule
# ---------------------------------------------------------------------------

_DEFAULT_POLL_TIMES = [time(9, 0), time(14, 0), time(20, 0)]


class TrailSchedule(BaseModel):
    """Configuration for trail review scheduling."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    chat_id: Optional[str] = None
    poll_times: List[time] = _DEFAULT_POLL_TIMES

    def is_active(self) -> bool:
        """Active when enabled AND a chat_id is configured."""
        return self.enabled and self.chat_id is not None

    @classmethod
    def from_time_strings(
        cls,
        enabled: bool = True,
        chat_id: Optional[str] = None,
        time_strings: Optional[List[str]] = None,
    ) -> "TrailSchedule":
        """Build from HH:MM strings, skipping unparseable entries."""
        parsed: List[time] = []
        for ts in time_strings or []:
            try:
                h, m = ts.strip().split(":")
                parsed.append(time(int(h), int(m)))
            except (ValueError, TypeError):
                logger.warning("Invalid time format: %s, skipping", ts)
        return cls(
            enabled=enabled,
            chat_id=chat_id,
            poll_times=parsed if parsed else _DEFAULT_POLL_TIMES,
        )
