# tests/test_preflight/test_models.py
"""Tests for preflight check models."""

import json

from src.preflight.models import CheckResult, CheckStatus, FixResult, PreflightReport


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_all_statuses_exist(self):
        """Verify all expected statuses are defined."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.FIXED.value == "fixed"

    def test_status_comparison(self):
        """Statuses should be comparable."""
        assert CheckStatus.PASS == CheckStatus.PASS
        assert CheckStatus.FAIL != CheckStatus.PASS


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_basic_creation(self):
        """Create a simple CheckResult."""
        result = CheckResult(
            name="test_check", status=CheckStatus.PASS, message="Check passed"
        )
        assert result.name == "test_check"
        assert result.status == CheckStatus.PASS
        assert result.message == "Check passed"
        assert result.details is None
        assert result.fix_applied is False

    def test_creation_with_details(self):
        """Create CheckResult with optional fields."""
        result = CheckResult(
            name="dependency_check",
            status=CheckStatus.FIXED,
            message="Missing packages installed",
            details="Installed: frontmatter, apscheduler",
            fix_applied=True,
        )
        assert result.details == "Installed: frontmatter, apscheduler"
        assert result.fix_applied is True

    def test_is_blocking_for_fail(self):
        """FAIL status should block startup."""
        result = CheckResult(
            name="critical_check", status=CheckStatus.FAIL, message="Critical failure"
        )
        assert result.is_blocking is True

    def test_is_blocking_for_pass(self):
        """PASS status should not block startup."""
        result = CheckResult(
            name="ok_check", status=CheckStatus.PASS, message="All good"
        )
        assert result.is_blocking is False

    def test_is_blocking_for_warning(self):
        """WARNING status should not block startup."""
        result = CheckResult(
            name="warn_check", status=CheckStatus.WARNING, message="Minor issue"
        )
        assert result.is_blocking is False

    def test_is_blocking_for_fixed(self):
        """FIXED status should not block startup."""
        result = CheckResult(
            name="fixed_check", status=CheckStatus.FIXED, message="Auto-fixed"
        )
        assert result.is_blocking is False

    def test_to_dict(self):
        """CheckResult should serialize to dict."""
        result = CheckResult(
            name="test", status=CheckStatus.PASS, message="OK", details="Extra info"
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "pass"
        assert d["message"] == "OK"
        assert d["details"] == "Extra info"
        assert d["fix_applied"] is False

    def test_to_dict_is_json_serializable(self):
        """to_dict output should be JSON serializable."""
        result = CheckResult(name="test", status=CheckStatus.FAIL, message="Failed")
        json_str = json.dumps(result.to_dict())
        assert '"status": "fail"' in json_str


class TestFixResult:
    """Tests for FixResult dataclass."""

    def test_success_creation(self):
        """Create successful FixResult."""
        result = FixResult(
            success=True,
            message="Dependencies installed",
            details="pip install completed",
        )
        assert result.success is True
        assert result.message == "Dependencies installed"
        assert result.details == "pip install completed"

    def test_failure_creation(self):
        """Create failed FixResult."""
        result = FixResult(
            success=False,
            message="Could not install dependencies",
            details="pip returned exit code 1",
        )
        assert result.success is False


class TestPreflightReport:
    """Tests for PreflightReport dataclass."""

    def test_empty_report(self):
        """Empty report should have zero counts."""
        report = PreflightReport(checks=[])
        assert report.passed == 0
        assert report.failed == 0
        assert report.warnings == 0
        assert report.fixed == 0
        assert report.should_block_startup is False

    def test_all_passing_checks(self):
        """Report with all passing checks."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.PASS, "OK"),
            CheckResult("check3", CheckStatus.PASS, "OK"),
        ]
        report = PreflightReport(checks=checks)
        assert report.passed == 3
        assert report.failed == 0
        assert report.warnings == 0
        assert report.fixed == 0
        assert report.should_block_startup is False

    def test_report_with_failure(self):
        """Report with one failure should block startup."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.FAIL, "Critical error"),
            CheckResult("check3", CheckStatus.PASS, "OK"),
        ]
        report = PreflightReport(checks=checks)
        assert report.passed == 2
        assert report.failed == 1
        assert report.should_block_startup is True

    def test_report_with_warnings(self):
        """Warnings should not block startup."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.WARNING, "Minor issue"),
        ]
        report = PreflightReport(checks=checks)
        assert report.warnings == 1
        assert report.should_block_startup is False

    def test_report_with_fixed(self):
        """Fixed checks should not block startup."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.FIXED, "Auto-fixed", fix_applied=True),
        ]
        report = PreflightReport(checks=checks)
        assert report.fixed == 1
        assert report.should_block_startup is False

    def test_mixed_report(self):
        """Report with mixed statuses."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.FAIL, "Error"),
            CheckResult("check3", CheckStatus.WARNING, "Warning"),
            CheckResult("check4", CheckStatus.FIXED, "Fixed"),
            CheckResult("check5", CheckStatus.PASS, "OK"),
        ]
        report = PreflightReport(checks=checks)
        assert report.passed == 2
        assert report.failed == 1
        assert report.warnings == 1
        assert report.fixed == 1
        assert report.should_block_startup is True

    def test_to_dict(self):
        """Report should serialize to dict."""
        checks = [
            CheckResult("check1", CheckStatus.PASS, "OK"),
            CheckResult("check2", CheckStatus.FAIL, "Error"),
        ]
        report = PreflightReport(checks=checks)
        d = report.to_dict()
        assert d["passed"] == 1
        assert d["failed"] == 1
        assert d["warnings"] == 0
        assert d["fixed"] == 0
        assert d["should_block_startup"] is True
        assert len(d["checks"]) == 2

    def test_to_dict_is_json_serializable(self):
        """Report to_dict should be JSON serializable."""
        checks = [
            CheckResult("test", CheckStatus.PASS, "OK"),
        ]
        report = PreflightReport(checks=checks)
        json_str = json.dumps(report.to_dict())
        assert '"passed": 1' in json_str

    def test_get_exit_code_success(self):
        """Exit code 0 for no failures."""
        report = PreflightReport(
            checks=[
                CheckResult("check1", CheckStatus.PASS, "OK"),
                CheckResult("check2", CheckStatus.WARNING, "Warn"),
            ]
        )
        assert report.get_exit_code() == 0

    def test_get_exit_code_failure(self):
        """Exit code 1 for failures."""
        report = PreflightReport(
            checks=[
                CheckResult("check1", CheckStatus.PASS, "OK"),
                CheckResult("check2", CheckStatus.FAIL, "Error"),
            ]
        )
        assert report.get_exit_code() == 1
