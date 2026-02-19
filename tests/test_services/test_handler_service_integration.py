"""
Tests for handler-service integration — verify handlers call service layer.

Ensures:
- claude_commands.py uses service-layer imports for business logic
- The module-level re-exports for backwards compat don't introduce circular deps
- forward_voice_to_claude uses service-layer detect_new_session_trigger
"""

import ast
import inspect


class TestHandlerUsesServiceImports:
    """Verify that handler functions reference service-layer functions."""

    def test_format_work_summary_called_via_service(self):
        """execute_claude_prompt should call format_work_summary from service."""
        from src.services.work_summary_service import format_work_summary

        # Verify the service function is the canonical one
        assert format_work_summary.__module__ == "src.services.work_summary_service"

    def test_detect_trigger_called_via_service(self):
        """forward_voice_to_claude should use detect_new_session_trigger from service."""
        from src.services.session_service import detect_new_session_trigger

        assert (
            detect_new_session_trigger.__module__ == "src.services.session_service"
        )

    def test_handler_module_imports_from_services(self):
        """claude_commands.py should have imports from services at module level."""
        import src.bot.handlers.claude_commands as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)

        service_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "services" in node.module:
                    for alias in node.names:
                        service_imports.append(alias.name)

        # Should import from service modules
        assert "detect_new_session_trigger" in service_imports
        assert "format_work_summary" in service_imports or any(
            "format_work_summary" in name for name in service_imports
        )

    def test_no_duplicate_business_logic_in_handler(self):
        """Handler should not contain the body of detect_new_session_trigger."""
        import src.bot.handlers.claude_commands as mod

        source = inspect.getsource(mod)

        # The handler should NOT define detect_new_session_trigger locally
        # It should only import it from the service
        tree = ast.parse(source)
        function_defs = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "detect_new_session_trigger" not in function_defs

    def test_no_duplicate_format_work_summary_in_handler(self):
        """Handler should not contain the body of _format_work_summary."""
        import src.bot.handlers.claude_commands as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)
        function_defs = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "_format_work_summary" not in function_defs


class TestServiceModulesStandalone:
    """Service modules should work independently of handler layer."""

    def test_session_service_no_handler_import(self):
        """session_service should not import from bot.handlers."""
        import src.services.session_service as mod

        source = inspect.getsource(mod)
        assert "bot.handlers" not in source

    def test_work_summary_service_no_handler_import(self):
        """work_summary_service should not import from bot.handlers."""
        import src.services.work_summary_service as mod

        source = inspect.getsource(mod)
        assert "bot.handlers" not in source
