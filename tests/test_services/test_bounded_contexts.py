"""Tests for bounded context definitions and cross-context import rules."""

import pytest

from src.domain.contexts import (
    BOUNDED_CONTEXTS,
    get_context_for_module,
    get_allowed_imports,
)


class TestBoundedContextDefinitions:
    """Verify bounded contexts are properly defined."""

    def test_bounded_contexts_is_dict(self):
        assert isinstance(BOUNDED_CONTEXTS, dict)

    def test_all_contexts_have_modules(self):
        for ctx_name, ctx_def in BOUNDED_CONTEXTS.items():
            assert "modules" in ctx_def, f"Context {ctx_name} missing 'modules'"
            assert len(ctx_def["modules"]) > 0, f"Context {ctx_name} has no modules"

    def test_keyboard_service_in_ui_context(self):
        ctx = get_context_for_module("src.services.keyboard_service")
        assert ctx == "ui"

    def test_srs_service_in_learning_context(self):
        ctx = get_context_for_module("src.services.srs_service")
        assert ctx == "learning"

    def test_poll_service_in_polling_context(self):
        ctx = get_context_for_module("src.services.poll_service")
        assert ctx == "polling"

    def test_accountability_service_in_accountability_context(self):
        ctx = get_context_for_module("src.services.accountability_service")
        assert ctx == "accountability"

    def test_unknown_module_returns_none(self):
        ctx = get_context_for_module("src.services.nonexistent_service")
        assert ctx is None

    def test_no_module_in_multiple_contexts(self):
        """Each module must belong to exactly one context."""
        all_modules = []
        for ctx_name, ctx_def in BOUNDED_CONTEXTS.items():
            for mod in ctx_def["modules"]:
                assert mod not in all_modules, (
                    f"Module {mod} appears in multiple contexts"
                )
                all_modules.append(mod)

    def test_core_modules_shared(self):
        """Core/infra modules should be in 'shared' context."""
        ctx = get_context_for_module("src.core.database")
        assert ctx == "shared"

    def test_get_allowed_imports_returns_list(self):
        allowed = get_allowed_imports("ui")
        assert isinstance(allowed, list)
        assert "shared" in allowed

    def test_all_contexts_can_import_shared(self):
        for ctx_name in BOUNDED_CONTEXTS:
            if ctx_name == "shared":
                continue
            allowed = get_allowed_imports(ctx_name)
            assert "shared" in allowed, (
                f"Context {ctx_name} should be allowed to import from shared"
            )
