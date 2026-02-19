"""Tests for bounded context definitions and cross-context import rules."""

import ast
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.domain.contexts import (
    BOUNDED_CONTEXTS,
    get_allowed_imports,
    get_context_for_module,
)
from src.domain.interfaces import EmbeddingProvider, VoiceSynthesizer

# Root of the source tree
SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src"


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
                assert (
                    mod not in all_modules
                ), f"Module {mod} appears in multiple contexts"
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
            assert (
                "shared" in allowed
            ), f"Context {ctx_name} should be allowed to import from shared"


class TestCallbackInterfaces:
    """Verify Protocol interfaces exist and are implementable."""

    def test_voice_synthesizer_protocol_exists(self):
        """VoiceSynthesizer should be a runtime-checkable Protocol."""
        assert hasattr(VoiceSynthesizer, "synthesize_mp3")

    def test_embedding_provider_protocol_exists(self):
        """EmbeddingProvider should be a runtime-checkable Protocol."""
        assert hasattr(EmbeddingProvider, "generate_embedding")

    def test_mock_satisfies_voice_synthesizer(self):
        """A mock with synthesize_mp3 should satisfy VoiceSynthesizer."""
        mock = AsyncMock()
        mock.synthesize_mp3 = AsyncMock(return_value=b"fake-audio")
        # Protocol structural check
        assert isinstance(mock, VoiceSynthesizer)

    def test_mock_satisfies_embedding_provider(self):
        """A mock with generate_embedding should satisfy EmbeddingProvider."""
        mock = AsyncMock()
        mock.generate_embedding = AsyncMock(return_value=b"fake-emb")
        assert isinstance(mock, EmbeddingProvider)


class TestAccountabilityDecoupled:
    """AccountabilityService should accept a VoiceSynthesizer dependency."""

    def test_accountability_accepts_voice_synthesizer(self):
        from src.services.accountability_service import AccountabilityService

        mock_synth = AsyncMock(spec=VoiceSynthesizer)
        mock_synth.synthesize_mp3 = AsyncMock(return_value=b"audio")
        svc = AccountabilityService(voice_synthesizer=mock_synth)
        assert svc._voice_synthesizer is mock_synth

    def test_accountability_default_voice_synthesizer(self):
        """When no synthesizer is passed, it should still work (backward compat)."""
        from src.services.accountability_service import AccountabilityService

        svc = AccountabilityService()
        assert svc._voice_synthesizer is not None


class TestPollServiceDecoupled:
    """PollService should accept an EmbeddingProvider dependency."""

    def test_poll_service_accepts_embedding_provider(self):
        from src.services.poll_service import PollService

        mock_emb = AsyncMock(spec=EmbeddingProvider)
        svc = PollService(embedding_provider=mock_emb)
        assert svc._embedding_provider is mock_emb

    def test_poll_service_default_embedding_provider(self):
        """When no provider is passed, it should still work (backward compat)."""
        from src.services.poll_service import PollService

        svc = PollService()
        assert svc._embedding_provider is not None


class TestPollingServiceDecoupled:
    """PollingService should accept an EmbeddingProvider dependency."""

    def test_polling_service_accepts_embedding_provider(self):
        from src.services.polling_service import PollingService

        mock_emb = AsyncMock(spec=EmbeddingProvider)
        svc = PollingService(embedding_provider=mock_emb)
        assert svc._embedding_provider is mock_emb

    def test_polling_service_default_embedding_provider(self):
        from src.services.polling_service import PollingService

        svc = PollingService()
        assert svc._embedding_provider is not None


# ---------------------------------------------------------------------------
# Slice 3 — Static import linting
# ---------------------------------------------------------------------------


def _file_to_module(filepath: Path) -> str:
    """Convert a file path under SRC_ROOT to a dotted module path.

    Example: src/services/poll_service.py -> src.services.poll_service
    """
    rel = filepath.relative_to(SRC_ROOT.parent)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _extract_top_level_imports(filepath: Path):
    """Yield (imported_module_path, lineno) for top-level imports.

    Only considers ``from X import ...`` and ``import X`` statements
    that appear at module scope (not nested inside functions/classes).
    """
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # Resolve relative imports
            if node.level > 0:
                # e.g., from ..services.foo import bar  (level=2)
                pkg_parts = list(filepath.relative_to(SRC_ROOT.parent).parts[:-1])
                if node.level <= len(pkg_parts):
                    base = ".".join(pkg_parts[: len(pkg_parts) - node.level])
                    full_module = f"{base}.{node.module}" if base else node.module
                else:
                    full_module = node.module
            else:
                full_module = node.module
            yield full_module, node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno


def _collect_service_files():
    """Return all .py files under src/services/ (non-test)."""
    services_dir = SRC_ROOT / "services"
    files = []
    for root, _dirs, fnames in os.walk(services_dir):
        for fname in fnames:
            if fname.endswith(".py") and not fname.startswith("test_"):
                files.append(Path(root) / fname)
    return sorted(files)


class TestImportBoundaryLint:
    """Fail if a service module has a top-level import from a disallowed context."""

    def test_no_cross_context_top_level_imports(self):
        """Every top-level import in a service file must come from the
        same context or an explicitly allowed context."""
        violations = []

        for filepath in _collect_service_files():
            source_module = _file_to_module(filepath)
            source_ctx = get_context_for_module(source_module)

            if source_ctx is None:
                # Module not mapped to any context -- skip
                continue

            allowed = get_allowed_imports(source_ctx)
            allowed_set = set(allowed) | {source_ctx}

            for imported_module, lineno in _extract_top_level_imports(filepath):
                target_ctx = get_context_for_module(imported_module)

                if target_ctx is None:
                    # Target not in any bounded context (stdlib, third-party,
                    # or unmapped internal) -- allowed
                    continue

                if target_ctx not in allowed_set:
                    violations.append(
                        f"{source_module} (ctx={source_ctx}) imports "
                        f"{imported_module} (ctx={target_ctx}) at line {lineno}"
                    )

        if violations:
            msg = "Cross-context top-level import violations found:\n" + "\n".join(
                f"  - {v}" for v in violations
            )
            pytest.fail(msg)
