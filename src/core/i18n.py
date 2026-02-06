"""
Internationalization (i18n) framework for the Telegram Agent.

Provides YAML-based translation loading, dot-notation key lookup with
fallback chain (requested locale → en → raw key), and per-user locale
caching backed by the existing LRUCache.

Usage:
    from src.core.i18n import t, get_user_locale_from_update

    locale = get_user_locale_from_update(update)
    text = t("commands.start.welcome", locale, name=user.first_name)
"""

import glob
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

import yaml

from ..utils.lru_cache import LRUCache

logger = logging.getLogger(__name__)

# Module-level state
_translations: Dict[str, Dict[str, Any]] = {}  # locale -> nested dict
SUPPORTED_LOCALES: Set[str] = set()
DEFAULT_LOCALE = "en"

# Per-user locale cache: user_id -> locale string
_locale_cache: LRUCache[int, str] = LRUCache(max_size=10000)


def _get_locales_dir() -> Path:
    """Get the locales directory path, trying multiple resolution strategies."""
    # Strategy 1: Relative to this source file
    source_based = Path(__file__).resolve().parent.parent.parent / "locales"
    if source_based.is_dir():
        return source_based
    # Strategy 2: Relative to CWD (for CI environments)
    cwd_based = Path.cwd() / "locales"
    if cwd_based.is_dir():
        return cwd_based
    # Fallback to source-based (will produce empty translations)
    return source_based


def load_translations(locales_dir: Optional[Path] = None) -> None:
    """Load all locale YAML files from the locales directory.

    Args:
        locales_dir: Override path for testing. Defaults to project locales/.
    """
    if locales_dir is None:
        locales_dir = _get_locales_dir()

    _translations.clear()
    SUPPORTED_LOCALES.clear()

    yaml_files = sorted(glob.glob(str(locales_dir / "*.yaml")))
    for filepath in yaml_files:
        locale = Path(filepath).stem  # e.g. "en" from "en.yaml"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    _translations[locale] = data
                    SUPPORTED_LOCALES.add(locale)
                    logger.info(f"Loaded locale: {locale} ({len(data)} top-level keys)")
        except Exception as e:
            logger.error(f"Failed to load locale file {filepath}: {e}")

    if DEFAULT_LOCALE not in SUPPORTED_LOCALES:
        logger.warning(f"Default locale '{DEFAULT_LOCALE}' not found in {locales_dir}")


def _resolve_key(data: Dict[str, Any], key: str) -> Optional[str]:
    """Resolve a dot-notation key in a nested dict.

    Args:
        data: Nested translation dict for a locale.
        key: Dot-separated key like "commands.start.welcome".

    Returns:
        The string value, or None if not found.
    """
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    # Only return strings (or things that can be stringified)
    if current is None:
        return None
    return str(current) if not isinstance(current, (dict, list)) else None


def _plural_form(n: int, locale: str) -> str:
    """Return CLDR plural category for count n in the given locale.

    Implements rules for English and Russian.  Other locales fall back
    to the English rule (one / other).
    """
    if locale == "ru":
        mod10 = n % 10
        mod100 = n % 100
        if mod10 == 1 and mod100 != 11:
            return "one"
        if mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
            return "few"
        return "many"
    # English / default
    return "one" if n == 1 else "other"


def t(
    key: str, locale: Optional[str] = None, count: Optional[int] = None, **kwargs: Any
) -> str:
    """Translate a key with fallback chain, pluralization, and interpolation.

    Fallback order: requested locale → DEFAULT_LOCALE ("en") → raw key.

    When *count* is provided the resolver first tries ``key.<plural_form>``
    (e.g. ``key.one``, ``key.few``, ``key.many``, ``key.other``) before
    falling back to the plain *key*.

    Args:
        key: Dot-notation translation key (e.g. "commands.start.welcome").
        locale: Target locale code (e.g. "ru"). Falls back to DEFAULT_LOCALE.
        count: If given, selects the plural sub-key automatically.
        **kwargs: Interpolation variables for str.format_map().

    Returns:
        Translated string with interpolation applied.
    """
    # Ensure translations are loaded
    if not _translations:
        load_translations()

    locale = normalize_locale(locale)

    # If count is provided, add it to interpolation variables
    if count is not None:
        kwargs = {**kwargs, "count": count, "n": count}

    # Build ordered list of keys to try when count is provided
    if count is not None:
        form = _plural_form(count, locale)
        keys_to_try = [f"{key}.{form}", f"{key}.other", key]
    else:
        keys_to_try = [key]

    # Try requested locale
    if locale in _translations:
        for k in keys_to_try:
            value = _resolve_key(_translations[locale], k)
            if value is not None:
                return _interpolate(value, kwargs)

    # Fallback to default locale
    if locale != DEFAULT_LOCALE and DEFAULT_LOCALE in _translations:
        # Re-derive plural form for default locale
        if count is not None:
            form_default = _plural_form(count, DEFAULT_LOCALE)
            fallback_keys = [f"{key}.{form_default}", f"{key}.other", key]
        else:
            fallback_keys = [key]
        for k in fallback_keys:
            value = _resolve_key(_translations[DEFAULT_LOCALE], k)
            if value is not None:
                return _interpolate(value, kwargs)

    # Final fallback: return the raw key
    logger.debug(f"Missing translation: key={key}, locale={locale}")
    return key


def _interpolate(template: str, variables: Dict[str, Any]) -> str:
    """Safely interpolate variables into a template string.

    Uses str.format_map with a defaultdict-like wrapper so missing
    variables don't raise KeyError.
    """
    if not variables:
        return template
    try:
        return template.format_map(variables)
    except (KeyError, ValueError, IndexError):
        # If interpolation fails, return template as-is
        logger.debug(f"Interpolation failed for template: {template[:80]}")
        return template


def normalize_locale(raw: Optional[str]) -> str:
    """Normalize a locale string to a supported locale code.

    Examples:
        "en-US" → "en"
        "ru"    → "ru"
        None    → "en"
        "xx"    → "en" (unsupported)

    Args:
        raw: Raw locale string from Telegram or DB.

    Returns:
        Normalized locale code.
    """
    if not raw:
        return DEFAULT_LOCALE

    # Take just the language part (before hyphen/underscore)
    base = raw.lower().split("-")[0].split("_")[0].strip()

    if not base:
        return DEFAULT_LOCALE

    # Ensure translations are loaded before checking support
    if not SUPPORTED_LOCALES:
        load_translations()

    if base in SUPPORTED_LOCALES:
        return base

    return DEFAULT_LOCALE


def get_user_locale_from_update(update: Any) -> str:
    """Get the locale for the user from an Update object.

    Checks the LRU cache first, then falls back to
    update.effective_user.language_code, then to DEFAULT_LOCALE.

    Args:
        update: telegram.Update object.

    Returns:
        Normalized locale string.
    """
    user = getattr(update, "effective_user", None)
    if not user:
        return DEFAULT_LOCALE

    user_id = getattr(user, "id", None)
    if user_id is None:
        return DEFAULT_LOCALE

    # Check cache
    cached = _locale_cache.get(user_id)
    if cached is not None:
        return cached

    # Fall back to Telegram's language_code
    raw = getattr(user, "language_code", None)
    locale = normalize_locale(raw)

    # Cache it
    _locale_cache.set(user_id, locale)
    return locale


def get_user_locale(user_id: int) -> str:
    """Get a user's locale from the cache.

    Args:
        user_id: Telegram user ID.

    Returns:
        Locale code (normalized), or DEFAULT_LOCALE if not cached.
    """
    cached = _locale_cache.get(user_id)
    return cached if cached is not None else DEFAULT_LOCALE


def set_user_locale(user_id: int, locale: str) -> None:
    """Set a user's locale in the cache.

    Args:
        user_id: Telegram user ID.
        locale: Locale code (will be normalized).
    """
    _locale_cache.set(user_id, normalize_locale(locale))


def clear_locale_cache() -> None:
    """Clear the entire locale cache."""
    _locale_cache.clear()


async def init_locale_cache() -> None:
    """Pre-populate locale cache from the database at startup.

    Mirrors the pattern of init_claude_mode_cache() in base.py.
    """
    try:
        from ..core.database import get_db_session
        from ..models.user import User

        async with get_db_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(User).where(User.language_code.isnot(None))
            )
            users = result.scalars().all()
            count = 0
            for user in users:
                if user.language_code:
                    _locale_cache.set(
                        user.user_id, normalize_locale(user.language_code)
                    )
                    count += 1
            logger.info(f"Initialized locale cache with {count} users")
    except Exception as e:
        logger.error(f"Error initializing locale cache: {e}")

    # Also ensure translations are loaded
    if not _translations:
        load_translations()
