"""Tests for the hybrid debugging pipeline using a scripted LLM (no model needed)."""

import json

import pytest

from core.ai_debugger import AIDebugger, ai_findings_to_issues, categorize_ai_error
from core.sandbox import SandboxResult, TestCaseResult
from core.test_validator import TestValidator
from utils.validators import AIFinding, Category, Confidence, InputValidationError

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"


def reply(code, findings=None, **extra):
    return json.dumps({"findings": findings or [], "corrected_code": code, "explanation": "because",
                       "changes": ["line 2"], **extra})


def test_static_mode_never_calls_llm(settings, scripted_llm):
    llm = scripted_llm([])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug(BUGGY, mode="static")
    assert result.repair_status == "not_attempted" and not llm.prompts
    assert result.corrected_code == result.original_code


def test_no_llm_falls_back_to_static(settings):
    result = AIDebugger(settings, llm=None, use_pylint=False).debug("def f():\n    return x\n")
    assert result.repair_status == "not_attempted"
    assert any(i.category == Category.UNDEFINED_NAME for i in result.static_issues)


def test_empty_input_rejected(settings):
    with pytest.raises(InputValidationError):
        AIDebugger(settings).debug("   ")


def test_hybrid_repairs_invalid_syntax_within_limit(settings, scripted_llm):
    llm = scripted_llm([reply("def add(a, b)\n    return a + b\n"), reply(FIXED)])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug(BUGGY, "add two numbers")
    assert result.attempts == 2
    assert result.corrected_code == FIXED
    assert result.repair_status == "unverified"
    assert "syntax error" in llm.prompts[1]


def test_repair_attempts_are_capped(settings, scripted_llm):
    bad = reply("def add(a, b)\n    return a + b\n")
    llm = scripted_llm([bad] * 10)
    result = AIDebugger(settings.with_overrides(max_repair_attempts=2), llm=llm, use_pylint=False).debug(BUGGY)
    assert result.attempts == 2 and len(llm.prompts) == 2
    assert result.repair_status == "invalid_syntax"


def test_verified_only_when_tests_pass(settings, scripted_llm):
    class Sandbox:
        def __init__(self):
            self.seen = []

        def run_tests(self, code, test_code):
            self.seen.append(code)
            ok = "a + b" in code
            return SandboxResult(executed=True, passed=1 if ok else 0, failed=0 if ok else 1,
                                 cases=[TestCaseResult("test_add", "passed" if ok else "failed", "" if ok else
                                                       "assert -1 == 5")])

    sandbox = Sandbox()
    llm = scripted_llm([reply("def add(a, b):\n    return b - a\n"), reply(FIXED)])
    debugger = AIDebugger(settings, llm=llm, validator=TestValidator(sandbox), use_pylint=False)
    result = debugger.debug(BUGGY, test_code="def test_add():\n    assert add(2, 3) == 5\n")
    assert result.repair_status == "verified"
    assert result.test_report.status == "passed"
    assert len(sandbox.seen) == 2
    assert "assert -1 == 5" in llm.prompts[1]


def test_llm_only_mode_single_attempt_no_static_context(settings, scripted_llm):
    llm = scripted_llm([reply("def add(a, b)\n    return a + b\n")])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug("def f():\n    return x\n", mode="llm_only")
    assert result.attempts == 1 and result.repair_status == "invalid_syntax"
    assert result.static_issues == []
    assert "No issues reported" in llm.prompts[0]


def test_no_changes_status(settings, scripted_llm):
    llm = scripted_llm([reply(FIXED, no_bugs_found=True)])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug(FIXED)
    assert result.repair_status == "no_changes" and not result.code_changed


def test_unparseable_llm_output_falls_back(settings, scripted_llm):
    llm = scripted_llm(["this is not json"])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug(BUGGY)
    assert result.repair_status == "llm_failed" and result.corrected_code == result.original_code


def test_hallucinated_lines_are_dropped():
    findings = [AIFinding(error_type="NameError", line_number=2, description="typo"),
                AIFinding(error_type="Bug", line_number=40, description="invented"),
                AIFinding(error_type="Bug", line_number=1, description="")]
    issues, dropped = ai_findings_to_issues(findings, BUGGY)
    assert len(issues) == 1 and dropped == 2
    assert issues[0].confidence == Confidence.AI_INFERRED and issues[0].category == Category.UNDEFINED_NAME


def test_categorize_ai_error():
    assert categorize_ai_error("IndentationError") == Category.INDENTATION
    assert categorize_ai_error("logic", "off-by-one in loop") == Category.LOGIC
    assert categorize_ai_error("weird") == Category.OTHER


def test_interface_change_is_reported(settings, scripted_llm):
    llm = scripted_llm([reply("def plus(a, b):\n    return a + b\n")])
    result = AIDebugger(settings, llm=llm, use_pylint=False).debug(BUGGY)
    assert any("add" in note for note in result.notes)
