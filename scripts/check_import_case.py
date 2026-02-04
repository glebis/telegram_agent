#!/usr/bin/env python3
"""Check that Python import paths match actual filesystem case.

macOS is case-insensitive by default, so `from src.Models.User import User`
works locally but breaks on Linux (case-sensitive).  This script catches
those mismatches before they reach CI or production.

Usage:
    python scripts/check_import_case.py          # check src/ and scripts/
    python scripts/check_import_case.py src/     # check specific dirs
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Optional


def _real_case_name(parent: Path, name: str) -> Optional[str]:
    """Return the true filesystem-cased entry in *parent* matching *name*.

    Comparison is case-insensitive so that we can detect when a developer
    writes ``from src.Models ...`` but the directory is ``src/models``.
    Returns ``None`` when *name* does not exist in *parent* at all.
    """
    try:
        entries = {e.name.lower(): e.name for e in parent.iterdir()}
    except (OSError, PermissionError):
        return None
    return entries.get(name.lower())


def resolve_import_path(
    module_parts: list[str], project_root: Path
) -> list[tuple[str, str]]:
    """Walk *module_parts* against the filesystem, returning mismatches.

    Returns a list of ``(imported_name, actual_name)`` pairs where the
    casing differs.
    """
    mismatches: list[tuple[str, str]] = []
    current = project_root

    for part in module_parts:
        actual = _real_case_name(current, part)
        if actual is None:
            # Path segment doesn't exist -- could be a third-party or
            # stdlib import, or a sub-attribute; stop checking.
            break
        if actual != part:
            mismatches.append((part, actual))
        # Advance into the directory (or .py file).  If it's a file we stop.
        candidate_dir = current / actual
        candidate_file = current / f"{actual}.py"
        if candidate_dir.is_dir():
            current = candidate_dir
        elif candidate_file.is_file():
            break
        else:
            break

    return mismatches


def _is_local_import(module: str, project_root: Path) -> bool:
    """Return True if *module* looks like a project-local import."""
    first = module.split(".")[0]
    return (project_root / first).exists()


def extract_imports(source: str, filepath: Path) -> list[tuple[int, str]]:
    """Parse *source* and return ``(lineno, dotted_module)`` pairs.

    Handles both ``import X.Y`` and ``from X.Y import Z`` forms.
    Relative imports are converted to absolute using *filepath*.
    """
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    results: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level and node.level > 0:
                # Relative import -- resolve to absolute.
                pkg = filepath.parent
                for _ in range(node.level - 1):
                    pkg = pkg.parent
                # Build the absolute module path relative to project root.
                try:
                    rel = pkg.relative_to(filepath.parents[len(filepath.parts) - 2])
                except ValueError:
                    continue
                prefix = ".".join(rel.parts)
                full = f"{prefix}.{node.module}" if prefix else node.module
                results.append((node.lineno, full))
            else:
                results.append((node.lineno, node.module))

    return results


def check_file(
    filepath: Path, project_root: Path
) -> list[tuple[Path, int, str, list[tuple[str, str]]]]:
    """Check a single file for import-case mismatches.

    Returns list of ``(filepath, lineno, module, mismatches)``.
    """
    errors: list[tuple[Path, int, str, list[tuple[str, str]]]] = []
    try:
        source = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors

    for lineno, module in extract_imports(source, filepath):
        parts = module.split(".")
        if not _is_local_import(module, project_root):
            continue
        mismatches = resolve_import_path(parts, project_root)
        if mismatches:
            errors.append((filepath, lineno, module, mismatches))

    return errors


def check_directories(
    dirs: list[Path], project_root: Path
) -> list[tuple[Path, int, str, list[tuple[str, str]]]]:
    """Scan all ``*.py`` files under *dirs* for case mismatches."""
    all_errors: list[tuple[Path, int, str, list[tuple[str, str]]]] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for pyfile in sorted(directory.rglob("*.py")):
            all_errors.extend(check_file(pyfile, project_root))
    return all_errors


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns 0 on success, 1 if mismatches found."""
    args = argv if argv is not None else sys.argv[1:]
    project_root = Path(__file__).resolve().parent.parent

    if args:
        dirs = [project_root / d for d in args]
    else:
        dirs = [project_root / "src", project_root / "scripts"]

    errors = check_directories(dirs, project_root)

    if not errors:
        print("OK: All import paths match filesystem case.")
        return 0

    print(f"Found {len(errors)} import-case mismatch(es):\n")
    for filepath, lineno, module, mismatches in errors:
        rel = filepath.relative_to(project_root)
        mismatch_details = ", ".join(
            f"'{imp}' should be '{actual}'" for imp, actual in mismatches
        )
        print(f"  {rel}:{lineno}  import {module}")
        print(f"    -> {mismatch_details}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
