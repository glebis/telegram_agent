"""
Verify that all public handler functions use the @handle_errors decorator.

Scans handler modules using AST to find async functions with (update, context)
signature and checks they are wrapped with @handle_errors. This is the contract
test that ensures standardized error reporting across all bot handlers.
"""

import ast
from pathlib import Path

import pytest

_HANDLERS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "bot" / "handlers"
)

# Modules that are utilities, not handler entry points
_SKIP_MODULES = {"__init__", "base", "formatting"}


def _get_handler_modules() -> list[Path]:
    """Return all handler .py files excluding utility modules."""
    return sorted(p for p in _HANDLERS_DIR.glob("*.py") if p.stem not in _SKIP_MODULES)


def _find_undecorated_handlers(filepath: Path) -> list[str]:
    """Find async handler functions missing @handle_errors decorator.

    A function is considered a handler if:
    - It's a top-level async function (not nested)
    - Its first two parameters are named 'update' and 'context'
    - It does NOT start with '_' (private helper)
    - It does NOT start with 'register' (registration function)
    - It does NOT start with 'cancel' (conversation cancel helpers)
    """
    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))

    undecorated = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        name = node.name

        # Skip private, registration, and cancel helpers
        if (
            name.startswith("_")
            or name.startswith("register")
            or name.startswith("cancel")
        ):
            continue

        # Check signature: first two params should be update, context
        args = node.args
        param_names = [a.arg for a in args.args]
        if len(param_names) < 2:
            continue
        if param_names[0] != "update" or param_names[1] != "context":
            continue

        # Check if @handle_errors is among decorators
        has_decorator = False
        for dec in node.decorator_list:
            # @handle_errors("name") is a Call node
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Name) and func.id == "handle_errors":
                    has_decorator = True
                    break
                if isinstance(func, ast.Attribute) and func.attr == "handle_errors":
                    has_decorator = True
                    break
            # @handle_errors without call (unlikely but handle it)
            if isinstance(dec, ast.Name) and dec.id == "handle_errors":
                has_decorator = True
                break

        if not has_decorator:
            undecorated.append(name)

    return undecorated


def _handler_modules_with_ids():
    """Yield (module_path, id_string) for parametrize."""
    for p in _get_handler_modules():
        yield pytest.param(p, id=p.stem)


class TestHandleErrorsDecoratorCoverage:
    """Every public handler function must use @handle_errors."""

    @pytest.mark.parametrize("module_path", _handler_modules_with_ids())
    def test_all_handlers_decorated(self, module_path: Path):
        undecorated = _find_undecorated_handlers(module_path)
        assert undecorated == [], (
            f"{module_path.stem}.py has handler functions without @handle_errors: "
            f"{', '.join(undecorated)}"
        )

    def test_handler_modules_import_handle_errors(self):
        """Every handler module with handlers should import handle_errors."""
        missing_import = []
        for module_path in _get_handler_modules():
            source = module_path.read_text()
            # Only check modules that have handler functions
            tree = ast.parse(source, filename=str(module_path))
            has_handlers = any(
                isinstance(n, ast.AsyncFunctionDef)
                and not n.name.startswith("_")
                and not n.name.startswith("register")
                and not n.name.startswith("cancel")
                and len(n.args.args) >= 2
                and n.args.args[0].arg == "update"
                and n.args.args[1].arg == "context"
                for n in ast.iter_child_nodes(tree)
            )
            if has_handlers and "handle_errors" not in source:
                missing_import.append(module_path.stem)

        assert missing_import == [], (
            f"These handler modules don't import handle_errors: "
            f"{', '.join(missing_import)}"
        )
