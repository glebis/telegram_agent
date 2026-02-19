"""
Test that the dependency layering rule is enforced:
  src/services/ and src/utils/ must NEVER import from src/bot/.

This catches reversed dependencies where lower-level layers reach up
into the presentation/handler layer.
"""

import ast
import os
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src"

# Directories that must not import from src.bot
LOWER_LAYERS = ["services", "utils"]

# Known exceptions that are acceptable (e.g. TYPE_CHECKING blocks)
# Format: (file_relative_to_src, imported_module_substring)
# TODO: llm_service.py imports keyboard_utils from bot — tracked separately
ALLOWED_EXCEPTIONS: list[tuple[str, str]] = [
    ("services/llm_service.py", "src.bot.keyboard_utils"),
]


def _collect_imports(filepath: Path) -> list[tuple[int, str, int]]:
    """Parse a Python file and return (line_number, module_string, level) for all imports.

    For ast.ImportFrom, level is the number of leading dots (relative import depth).
    For ast.Import, level is always 0.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                results.append((node.lineno, node.module, node.level or 0))
    return results


def _resolve_import(filepath: Path, module: str, level: int) -> str:
    """Resolve an import to its absolute dotted form.

    Args:
        filepath: The .py file containing the import.
        module: The module string (without leading dots).
        level: Number of dots for relative imports (0 = absolute).
    """
    if level == 0:
        return module

    # Python relative imports: from the current package directory
    # (filepath.parent), go up (level - 1) directories.
    #   level=1 (.X)  -> same package dir
    #   level=2 (..X) -> parent of package dir
    package_dir = filepath.parent
    for _ in range(level - 1):
        package_dir = package_dir.parent

    # Build absolute module path relative to project root
    project_root = SRC_ROOT.parent
    try:
        relative_to_root = package_dir.relative_to(project_root)
    except ValueError:
        return module

    base_str = str(relative_to_root).replace(os.sep, ".")
    if module:
        return f"{base_str}.{module}"
    return base_str


def _find_bot_imports_in_layer(layer: str) -> list[str]:
    """Find all imports from src.bot in the given layer directory."""
    violations = []
    layer_dir = SRC_ROOT / layer

    if not layer_dir.exists():
        return violations

    for py_file in layer_dir.rglob("*.py"):
        rel_path = str(py_file.relative_to(SRC_ROOT))
        imports = _collect_imports(py_file)

        for lineno, module, level in imports:
            # Resolve relative imports to absolute form
            resolved = _resolve_import(py_file, module, level)

            # Check if it imports from src.bot
            is_bot_import = (
                resolved.startswith("src.bot")
                or resolved.startswith("src.bot.")
                or ".bot." in resolved
                and resolved.startswith("src")
            )

            if is_bot_import:
                # Check if it's an allowed exception
                is_allowed = any(
                    rel_path == exc_file and exc_mod in resolved
                    for exc_file, exc_mod in ALLOWED_EXCEPTIONS
                )
                if not is_allowed:
                    violations.append(
                        f"{rel_path}:{lineno} imports {module} "
                        f"(resolves to {resolved})"
                    )

    return violations


class TestNoReversedDependencies:
    """Verify services/ and utils/ never import from bot/."""

    def test_services_do_not_import_bot(self):
        """src/services/ must not import from src/bot/."""
        violations = _find_bot_imports_in_layer("services")
        assert violations == [], (
            "services/ has reversed imports from bot/:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_utils_do_not_import_bot(self):
        """src/utils/ must not import from src/bot/."""
        violations = _find_bot_imports_in_layer("utils")
        assert violations == [], (
            "utils/ has reversed imports from bot/:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
