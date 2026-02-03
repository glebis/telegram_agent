"""Single source of truth for the application version.

Reads the version from pyproject.toml at import time using tomllib (stdlib, Python 3.11+).
"""

import tomllib
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_version() -> str:
    """Read and return the version string from pyproject.toml."""
    pyproject_path = _PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


__version__: str = get_version()
