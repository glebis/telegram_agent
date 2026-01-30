# src/preflight/models.py
"""Data models for preflight check system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CheckStatus(Enum):
    """Status of a preflight check."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    FIXED = "fixed"


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    fix_applied: bool = False

    @property
    def is_blocking(self) -> bool:
        """Return True if this result should block startup."""
        return self.status == CheckStatus.FAIL

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "fix_applied": self.fix_applied,
        }


@dataclass
class FixResult:
    """Result of an attempted fix operation."""

    success: bool
    message: str
    details: Optional[str] = None


@dataclass
class PreflightReport:
    """Aggregated report of all preflight checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def failed(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def warnings(self) -> int:
        """Count of warning checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.WARNING)

    @property
    def fixed(self) -> int:
        """Count of auto-fixed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FIXED)

    @property
    def should_block_startup(self) -> bool:
        """Return True if any check failed."""
        return self.failed > 0

    def get_exit_code(self) -> int:
        """Return appropriate exit code (0 for success, 1 for failure)."""
        return 1 if self.should_block_startup else 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "checks": [c.to_dict() for c in self.checks],
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "fixed": self.fixed,
            "should_block_startup": self.should_block_startup,
        }
