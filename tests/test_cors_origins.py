"""Tests for CORS origins parsing in main.py."""

import os
from unittest.mock import patch


def _parse_cors_origins():
    """Import and return the cors_origins list from main module.

    We must re-import to pick up the patched env var.
    """
    import importlib

    import src.main as main_mod

    importlib.reload(main_mod)
    return main_mod.cors_origins


class TestCorsOriginsParsing:
    """Verify CORS_ORIGINS env var is parsed with whitespace stripped."""

    @patch.dict(
        os.environ,
        {"CORS_ORIGINS": "http://localhost:3000, http://localhost:8000"},
    )
    def test_strips_whitespace_from_origins(self):
        origins = _parse_cors_origins()
        for origin in origins:
            assert (
                origin == origin.strip()
            ), f"Origin has leading/trailing whitespace: {origin!r}"

    @patch.dict(
        os.environ,
        {"CORS_ORIGINS": " http://a.com , http://b.com , http://c.com "},
    )
    def test_strips_heavy_whitespace(self):
        origins = _parse_cors_origins()
        assert origins == ["http://a.com", "http://b.com", "http://c.com"]

    @patch.dict(
        os.environ,
        {"CORS_ORIGINS": "http://a.com,,, http://b.com,"},
    )
    def test_filters_empty_strings(self):
        origins = _parse_cors_origins()
        assert "" not in origins
        assert all(o.strip() for o in origins)

    @patch.dict(os.environ, {}, clear=False)
    def test_default_origins_when_env_unset(self):
        # Remove CORS_ORIGINS if present
        env_copy = os.environ.copy()
        env_copy.pop("CORS_ORIGINS", None)
        with patch.dict(os.environ, env_copy, clear=True):
            origins = _parse_cors_origins()
            assert "http://localhost:3000" in origins
            assert "http://localhost:8000" in origins
