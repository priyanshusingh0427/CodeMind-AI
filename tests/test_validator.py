"""Tests for input validation, test rendering, the sandbox wrapper and the test validator.

Docker is NOT required: the sandbox is exercised through its command builder,
its output parser and a fake sandbox object. A real end-to-end Docker run is
covered by tests/test_sandbox_docker.py, which is skipped when Docker is absent.
"""

import json

import pytest

from config import Settings
from core.sandbox import RESULT_MARKER, DockerSandbox, SandboxResult, TestCaseResult
from core.test_generator import UnsafeTestError, check_expression, render_pytest, template_specs
from core.test_validator import TestValidator
from utils.validators import InputValidationError, TestCaseSpec, decode_uploaded_file, validate_code_input


# -- input validation -----------------------------------------------------
def test_validate_code_input():
    assert validate_code_input("x = 1\n", 100, 10) == "x = 1\n"
    for bad in ("", "   ", "a\x00b"):
        with pytest.raises(InputValidationError):
            validate_code_input(bad, 100, 10)
    with pytest.raises(InputValidationError):
        validate_code_input("x" * 101, 100, 10)
    with pytest.raises(InputValidationError):
        validate_code_input("\n" * 20, 100, 10)


def test_decode_uploaded_file():
    assert decode_uploaded_file("\ufeffx = 1".encode("utf-8"), 100) == "x = 1"
    with pytest.raises(InputValidationError):
        decode_uploaded_file(b"\xff\xfe\x00", 100)


# -- test rendering ---------------------------------------------------------
def test_check_expression_rejects_unsafe():
    check_expression("add(1, 2)")
    for bad in ("__import__('os').system('ls')", "open('x')", "x.__class__", "add(1,", "lambda: 1"):
        with pytest.raises(UnsafeTestError):
            check_expression(bad)


def test_render_pytest_generates_valid_module():
    specs = [TestCaseSpec(name="adds numbers", call="add(2, 3)", expected="5"),
             TestCaseSpec(name="bad input", category="invalid", call="add('a', None)", expects_exception="TypeError"),
             TestCaseSpec(name="unsafe", call="open('/etc/passwd')", expected="''"),
             TestCaseSpec(name="incomplete", call="add(1, 1)", expected="")]
    code, warnings = render_pytest(specs)
    compile(code, "test_solution.py", "exec")
    assert "def test_adds_numbers():" in code
    assert "pytest.raises(TypeError)" in code
    assert len(warnings) == 2


def test_rendered_tests_actually_run(tmp_path):
    """Run rendered tests with pytest on trusted, known code (our own fixture, not user code)."""
    (tmp_path / "solution.py").write_text("def add(a, b):\n    return a + b\n")
    code, _ = render_pytest([TestCaseSpec(name="ok", call="add(0.1, 0.2)", expected="0.3"),
                             TestCaseSpec(name="lists", call="add([1], [2])", expected="[1, 2]"),
                             TestCaseSpec(name="wrong", call="add(1, 1)", expected="3")])
    (tmp_path / "test_solution.py").write_text(code)
    exit_code = pytest.main(["-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path), str(tmp_path)])
    assert exit_code == 1  # exactly the 'wrong' test fails


def test_template_specs():
    specs = template_specs("def add(a, b):\n    return a + b\n\ndef _private():\n    pass\n")
    assert [s.call for s in specs] == ["add(..., ...)"]


# -- sandbox wrapper --------------------------------------------------------
def test_sandbox_command_has_security_flags():
    sandbox = DockerSandbox(Settings().with_overrides(sandbox_memory_mb=128, sandbox_cpus=0.5))
    cmd = " ".join(sandbox.build_command("/tmp/x", "codemind-test"))
    for flag in ("--network none", "--user 65534:65534", "--memory 128m", "--cpus 0.5", "--read-only",
                 "--cap-drop ALL", "no-new-privileges", "--pids-limit", "/tmp/x:/work:ro"):
        assert flag in cmd


def test_sandbox_disabled_reports_static_mode():
    status = DockerSandbox(Settings().with_overrides(sandbox_enabled=False)).status()
    assert not status.available and "static" in status.message.lower()


def test_sandbox_parse_output():
    sandbox = DockerSandbox(Settings().with_overrides(sandbox_output_limit=50))
    summary = {"exit_code": 1, "cases": [{"name": "test_a", "outcome": "passed"},
                                         {"name": "test_b", "outcome": "failed", "message": "assert 1 == 2"}],
               "collect_errors": []}
    stdout = "user print output " * 20 + RESULT_MARKER + json.dumps(summary) + RESULT_MARKER
    result = sandbox.parse_output(stdout, "", 0, 0.5)
    assert result.passed == 1 and result.failed == 1 and not result.all_passed
    assert len(result.stdout) <= 50
    killed = sandbox.parse_output("", "", 137, 1.0)
    assert killed.errors == 1 and "killed" in killed.error


# -- validator ----------------------------------------------------------------
class FakeSandbox:
    def __init__(self, result: SandboxResult):
        self.result = result
        self.calls = 0

    def run_tests(self, code, test_code):
        self.calls += 1
        return self.result


def test_validator_skips_without_sandbox():
    assert TestValidator(None).validate("x = 1\n", "def test_a():\n    pass\n").status == "skipped"


def test_validator_rejects_invalid_code_without_running():
    fake = FakeSandbox(SandboxResult(executed=True))
    report = TestValidator(fake).validate("def f(:\n", "def test_a():\n    pass\n")
    assert report.status == "error" and fake.calls == 0


def test_validator_pass_and_fail():
    passed = SandboxResult(executed=True, passed=2, cases=[TestCaseResult("t1", "passed"), TestCaseResult("t2",
                                                                                                          "passed")])
    report = TestValidator(FakeSandbox(passed)).validate("x = 1\n", "def test_a():\n    pass\n")
    assert report.status == "passed" and report.pass_rate == 1.0
    assert "does not guarantee" in report.message
    failed = SandboxResult(executed=True, passed=1, failed=1,
                           cases=[TestCaseResult("t1", "passed"), TestCaseResult("t2", "failed", "boom")])
    report = TestValidator(FakeSandbox(failed)).validate("x = 1\n", "def test_a():\n    pass\n")
    assert report.status == "failed" and "boom" in report.failure_details
