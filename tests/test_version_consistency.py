"""Tests for version consistency between pyproject.toml and application code."""

import tomllib
from pathlib import Path

# Path to project root (two levels up from tests/)
PROJECT_ROOT = Path(__file__).parent.parent


def _read_pyproject_version() -> str:
    """Read version from pyproject.toml using tomllib."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


class TestVersionConsistency:
    """Verify that all version references use a single source of truth."""

    def test_get_version_returns_string(self):
        """get_version() should return a non-empty version string."""
        from src.version import get_version

        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_get_version_matches_pyproject(self):
        """get_version() must match pyproject.toml version."""
        from src.version import get_version

        pyproject_version = _read_pyproject_version()
        assert get_version() == pyproject_version

    def test_fastapi_app_version_matches_pyproject(self):
        """FastAPI app.version must match pyproject.toml version."""
        from src.main import app
        from src.version import get_version

        pyproject_version = _read_pyproject_version()
        assert app.version == pyproject_version
        assert app.version == get_version()

    def test_version_is_valid_semver_format(self):
        """Version should look like a valid semver string (X.Y.Z)."""
        from src.version import get_version

        version = get_version()
        parts = version.split(".")
        assert len(parts) == 3, f"Expected 3-part semver, got: {version}"
        for part in parts:
            assert part.isdigit(), f"Non-numeric semver component: {part}"

    def test_version_module_attribute(self):
        """__version__ module-level attribute should be accessible."""
        from src.version import __version__

        assert isinstance(__version__, str)
        assert __version__ == _read_pyproject_version()
