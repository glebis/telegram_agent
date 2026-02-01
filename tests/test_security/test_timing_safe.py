"""Test that all API key comparisons use timing-safe comparison."""

import ast
import os
from pathlib import Path


def _find_python_files(root: str):
    """Yield all .py files under root."""
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def _check_file_for_unsafe_comparison(filepath: str) -> list:
    """Check a file for direct string comparison of API keys/secrets."""
    issues = []
    try:
        with open(filepath, "r") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError):
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            # Check for comparisons involving variables named *key*, *secret*, *token*
            for name_node in ast.walk(node):
                if isinstance(name_node, ast.Name):
                    varname = name_node.id.lower()
                    if any(kw in varname for kw in ("api_key", "secret", "token")):
                        # Check if this comparison is inside hmac.compare_digest
                        # If the parent is a Call to hmac.compare_digest, it's fine
                        # Simple heuristic: flag direct == or != on key variables
                        for op in node.ops:
                            if isinstance(op, (ast.Eq, ast.NotEq)):
                                issues.append(
                                    f"{filepath}:{node.lineno}: "
                                    f"Direct comparison on '{name_node.id}' — "
                                    f"use hmac.compare_digest() instead"
                                )
    return issues


def test_no_timing_unsafe_comparisons():
    """Verify no API key/secret/token comparisons use == or !=."""
    src_root = str(Path(__file__).parent.parent.parent / "src")
    all_issues = []
    for filepath in _find_python_files(src_root):
        issues = _check_file_for_unsafe_comparison(filepath)
        all_issues.extend(issues)

    # Filter out known safe patterns (inside `not x or not hmac.compare_digest(...)`)
    # The AST check is conservative — review flagged items manually
    assert len(all_issues) == 0, (
        f"Found {len(all_issues)} potential timing-unsafe comparisons:\n"
        + "\n".join(all_issues)
    )
