"""Validate candidate code against test cases using the sandbox.

This module is the single entry point for dynamic validation. It checks that
both the candidate code and the test file are valid Python before handing them
to :class:`core.sandbox.DockerSandbox`. When the sandbox is unavailable the
result is ``status='skipped'`` and the caller continues in static-only mode.

Passing tests is evidence, not proof, of correctness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from core.sandbox import SandboxResult, TestCaseResult
from core.syntax_checker import check_syntax
from utils.logger import get_logger

logger = get_logger("test_validator")

CORRECTNESS_DISCLAIMER = ("Passing tests increases confidence but does not guarantee the program is correct "
                          "for every possible input.")


class SandboxLike(Protocol):
    def run_tests(self, code: str, test_code: str) -> SandboxResult: ...


@dataclass
class TestReport:
    """Validation outcome in a UI/database friendly form."""

    __test__ = False  # not a pytest test class

    status: str  # passed | failed | error | skipped
    passed: int = 0
    failed: int = 0
    errors: int = 0
    cases: list[dict] = field(default_factory=list)
    message: str = ""
    duration: float = 0.0
    failure_details: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def pass_rate(self) -> float:
        return round(self.passed / self.total, 4) if self.total else 0.0

    def to_dict(self) -> dict:
        return {"status": self.status, "passed": self.passed, "failed": self.failed, "errors": self.errors,
                "total": self.total, "pass_rate": self.pass_rate, "cases": self.cases, "message": self.message,
                "duration": round(self.duration, 3)}


def _case_dict(case: TestCaseResult) -> dict:
    return {"name": case.name, "outcome": case.outcome, "message": case.message, "duration": case.duration}


class TestValidator:
    """Run tests for a piece of code, if a sandbox is available."""

    __test__ = False  # not a pytest test class

    def __init__(self, sandbox: Optional[SandboxLike]) -> None:
        self.sandbox = sandbox

    def validate(self, code: str, test_code: str) -> TestReport:
        if self.sandbox is None:
            return TestReport(status="skipped", message="Isolated execution is unavailable; tests were not run.")
        if not test_code.strip():
            return TestReport(status="skipped", message="No tests provided.")
        _tree, fatal, _ = check_syntax(code)
        if fatal is not None:
            return TestReport(status="error", errors=1, message=f"Code under test is invalid: {fatal.message}",
                              failure_details=fatal.message)
        _tree, fatal, _ = check_syntax(test_code)
        if fatal is not None:
            return TestReport(status="error", errors=1, message=f"Test file is invalid: {fatal.message}",
                              failure_details=fatal.message)

        result = self.sandbox.run_tests(code, test_code)
        if not result.executed:
            return TestReport(status="skipped", message=result.error or "Sandbox unavailable.")
        if result.all_passed:
            status = "passed"
            message = f"All {result.total} test(s) passed. {CORRECTNESS_DISCLAIMER}"
        elif result.total == 0 or (result.error and result.passed == 0 and result.failed == 0):
            status = "error"
            message = result.error or "No tests were executed."
        else:
            status = "failed"
            message = f"{result.passed}/{result.total} test(s) passed."
        if result.timed_out:
            message = result.error
        report = TestReport(status=status, passed=result.passed, failed=result.failed, errors=result.errors,
                            cases=[_case_dict(c) for c in result.cases], message=message, duration=result.duration,
                            failure_details=result.failure_summary())
        logger.info("validation finished", extra={"status": status, "passed": result.passed, "total": result.total})
        return report
