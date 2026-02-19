"""
Typed config loader — parses YAML / env vars into typed domain objects.

Each loader reads a specific config file and returns an immutable Pydantic
model.  Cached singleton accessors (`get_*`) are provided for production use.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .typed_config import (
    AccountabilityConfig,
    ModeCatalog,
    ModeConfig,
    ModePreset,
    ModeSettings,
    PersonalityProfile,
    TrailSchedule,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Raw YAML loading helper
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.warning("Config file not found: %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Failed to load %s: %s", path, e)
        return {}


# ---------------------------------------------------------------------------
# Mode catalog
# ---------------------------------------------------------------------------

_FALLBACK_CATALOG = ModeCatalog(
    modes={
        "default": ModeConfig(
            name="Default",
            prompt="Describe the image in <=40 words.",
            embed=False,
        ),
    },
    aliases={},
)


def load_mode_catalog(path: Optional[Path] = None) -> ModeCatalog:
    """Parse modes.yaml into a ModeCatalog."""
    if path is None:
        path = PROJECT_ROOT / "config" / "modes.yaml"

    raw = _load_yaml(path)
    if not raw or "modes" not in raw:
        return _FALLBACK_CATALOG

    modes: Dict[str, ModeConfig] = {}
    for mode_key, mode_data in raw.get("modes", {}).items():
        if not isinstance(mode_data, dict):
            continue

        presets = []
        for preset_data in mode_data.get("presets", []):
            if isinstance(preset_data, dict) and "name" in preset_data:
                presets.append(
                    ModePreset(
                        name=preset_data["name"],
                        description=preset_data.get("description"),
                        prompt=preset_data.get("prompt", ""),
                    )
                )

        modes[mode_key] = ModeConfig(
            name=mode_data.get("name", mode_key),
            description=mode_data.get("description"),
            prompt=mode_data.get("prompt", "Describe this image."),
            embed=mode_data.get("embed", False),
            max_tokens=mode_data.get("max_tokens"),
            temperature=mode_data.get("temperature"),
            presets=presets,
        )

    aliases = raw.get("aliases", {}) or {}
    settings_raw = raw.get("settings", {}) or {}
    settings = ModeSettings(**{k: v for k, v in settings_raw.items() if v is not None})

    return ModeCatalog(modes=modes, aliases=aliases, settings=settings)


# ---------------------------------------------------------------------------
# Accountability config
# ---------------------------------------------------------------------------


def load_accountability_config(path: Optional[Path] = None) -> AccountabilityConfig:
    """Parse accountability section from defaults.yaml."""
    if path is None:
        path = PROJECT_ROOT / "config" / "defaults.yaml"

    raw = _load_yaml(path)
    acct = raw.get("accountability", {})
    if not acct:
        return AccountabilityConfig(personalities={})

    personalities: Dict[str, PersonalityProfile] = {}
    for name, pdata in acct.get("personalities", {}).items():
        if not isinstance(pdata, dict):
            continue
        try:
            personalities[name] = PersonalityProfile(
                voice=pdata.get("voice", ""),
                emotion=pdata.get("emotion", ""),
                struggle_threshold=pdata.get("struggle_threshold", 3),
                celebration_style=pdata.get("celebration_style", "moderate"),
            )
        except Exception as e:
            logger.warning("Skipping personality '%s': %s", name, e)

    default = acct.get("default_personality", "supportive")

    return AccountabilityConfig(
        personalities=personalities,
        default_personality=default,
    )


# ---------------------------------------------------------------------------
# Trail schedule
# ---------------------------------------------------------------------------


def load_trail_schedule() -> TrailSchedule:
    """Build TrailSchedule from environment variables."""
    enabled = os.getenv("TRAIL_REVIEW_ENABLED", "true").lower() == "true"
    chat_id = os.getenv("TRAIL_REVIEW_CHAT_ID")
    times_str = os.getenv("TRAIL_REVIEW_TIMES", "09:00,14:00,20:00")
    time_strings = [t.strip() for t in times_str.split(",")]

    return TrailSchedule.from_time_strings(
        enabled=enabled,
        chat_id=chat_id,
        time_strings=time_strings,
    )


# ---------------------------------------------------------------------------
# Cached singletons
# ---------------------------------------------------------------------------

_mode_catalog: Optional[ModeCatalog] = None
_accountability_config: Optional[AccountabilityConfig] = None
_trail_schedule: Optional[TrailSchedule] = None


def get_mode_catalog() -> ModeCatalog:
    global _mode_catalog
    if _mode_catalog is None:
        _mode_catalog = load_mode_catalog()
    return _mode_catalog


def get_accountability_config() -> AccountabilityConfig:
    global _accountability_config
    if _accountability_config is None:
        _accountability_config = load_accountability_config()
    return _accountability_config


def get_trail_schedule() -> TrailSchedule:
    global _trail_schedule
    if _trail_schedule is None:
        _trail_schedule = load_trail_schedule()
    return _trail_schedule


def _clear_caches() -> None:
    """Clear all cached typed config objects (for testing)."""
    global _mode_catalog, _accountability_config, _trail_schedule
    _mode_catalog = None
    _accountability_config = None
    _trail_schedule = None
