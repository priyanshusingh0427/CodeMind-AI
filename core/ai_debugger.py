"""The hybrid, self-verifying debugging pipeline.

Pipeline (``mode='hybrid'``, the proposed method)::

    input validation -> AST analysis -> Pylint -> Radon metrics
    -> structured prompt (code + confirmed findings + expected behaviour)
    -> local LLM (JSON) -> schema validation
    -> syntax revalidation -> static re-analysis -> optional sandboxed tests
    -> limited iterative repair (max N attempts) -> metrics comparison

Two baselines used in the evaluation share the same code path:

* ``mode='static'``   – static analysis only, no correction (Baseline 1)
* ``mode='llm_only'`` – one LLM call without static findings and without
  validation or repair (Baseline 2)
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from config import Settings
from core.complexity_analyzer import ComplexityReport, analyze_complexity, compute_quality_score
from core.llm_engine import LLMClient, LLMError, LLMUnavailableError
from core.static_analyzer import analyze_static
from core.syntax_checker import check_syntax
from core.test_validator import TestReport, TestValidator
from utils.helpers import new_session_id, normalize_code, strip_code_fences
from utils.logger import get_logger
from utils.prompts import SYSTEM_PROMPT, build_debug_prompt, build_repair_prompt
from utils.validators import AIDebugResponse, AIFinding, Category, Confidence, Issue, Severity, validate_code_input

logger = get_logger("ai_debugger")

MODES = ("static", "llm_only", "hybrid")

REPAIR_STATUS_LABELS = {
    "not_attempted": "Static analysis only (no AI correction)",
    "no_changes": "No changes needed according to the AI",
    "verified": "Correction passed all provided tests",
    "unverified": "Correction is valid Python but was not test-verified",
    "failed_validation": "Correction failed validation",
    "invalid_syntax": "AI output is not valid Python",
    "llm_failed": "AI model unavailable or returned unusable output",
}

_CATEGORY_KEYWORDS: list[tuple[tuple[str, ...], Category]] = [
    (("indent", "taberror"), Category.INDENTATION),
    (("syntax",), Category.SYNTAX),
    (("nameerror", "undefined", "not defined"), Category.UNDEFINED_NAME),
    (("import", "modulenotfound"), Category.MISSING_IMPORT),
    (("type",), Category.TYPE),
    (("logic", "off-by-one", "off by one", "wrong result", "incorrect"), Category.LOGIC),
    (("zerodivision", "index", "key", "attribute", "runtime", "exception", "recursion", "value"),
     Category.RUNTIME),
    (("unreachable", "dead code"), Category.UNREACHABLE),
    (("unused",), Category.UNUSED),
    (("style", "pep", "naming"), Category.STYLE),
]


@dataclass
class DebugResult:
    """Everything produced by one debugging run."""

    session_id: str
    mode: str
    original_code: str
    corrected_code: str
    expected_behavior: str = ""
    static_issues: list[Issue] = field(default_factory=list)
    ai_issues: list[Issue] = field(default_factory=list)
    after_issues: list[Issue] = field(default_factory=list)
    metrics_before: ComplexityReport = field(default_factory=ComplexityReport)
    metrics_after: Optional[ComplexityReport] = None
    quality_before: float = 0.0
    quality_after: Optional[float] = None
    explanation: str = ""
    changes: list[str] = field(default_factory=list)
    optimization_suggestions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    llm_used: bool = False
    llm_message: str = ""
    model_name: str = ""
    repair_status: str = "not_attempted"
    attempts: int = 0
    test_report: Optional[TestReport] = None
    notes: list[str] = field(default_factory=list)
    duration: float = 0.0
    stage_timings: dict[str, float] = field(default_factory=dict)
    pylint_error: str = ""

    @property
    def all_issues(self) -> list[Issue]:
        return self.static_issues + self.ai_issues

    @property
    def code_changed(self) -> bool:
        return normalize_code(self.original_code).strip() != normalize_code(self.corrected_code).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id, "mode": self.mode, "original_code": self.original_code,
            "corrected_code": self.corrected_code, "expected_behavior": self.expected_behavior,
            "static_issues": [i.model_dump(mode="json") for i in self.static_issues],
            "ai_issues": [i.model_dump(mode="json") for i in self.ai_issues],
            "after_issues": [i.model_dump(mode="json") for i in self.after_issues],
            "metrics_before": self.metrics_before.to_dict(),
            "metrics_after": self.metrics_after.to_dict() if self.metrics_after else None,
            "quality_before": self.quality_before, "quality_after": self.quality_after,
            "explanation": self.explanation, "changes": self.changes,
            "optimization_suggestions": self.optimization_suggestions, "assumptions": self.assumptions,
            "llm_used": self.llm_used, "llm_message": self.llm_message, "model_name": self.model_name,
            "repair_status": self.repair_status, "attempts": self.attempts,
            "test_report": self.test_report.to_dict() if self.test_report else None,
            "notes": self.notes, "duration": round(self.duration, 3),
            "stage_timings": {k: round(v, 3) for k, v in self.stage_timings.items()},
        }


def categorize_ai_error(error_type: str, description: str = "") -> Category:
    """Map a free-text AI error type onto the project's category enum."""
    text = f"{error_type} {description}".lower()
    for keywords, category in _CATEGORY_KEYWORDS:
        if any(k in text for k in keywords):
            return category
    return Category.OTHER


def ai_findings_to_issues(findings: list[AIFinding], code: str) -> tuple[list[Issue], int]:
    """Convert AI findings to issues, dropping unsupported ones.

    A finding is discarded if it has no description or points to a line that
    does not exist (a common hallucination). Returns (issues, dropped_count).
    """
    line_count = len(code.splitlines())
    issues: list[Issue] = []
    dropped = 0
    for finding in findings:
        if not finding.description.strip():
            dropped += 1
            continue
        if finding.line_number is not None and not (1 <= finding.line_number <= line_count):
            dropped += 1
            continue
        issues.append(Issue(line=finding.line_number, category=categorize_ai_error(finding.error_type,
                                                                                      finding.description),
                            severity=finding.severity, message=finding.description.strip(),
                            symbol=finding.error_type[:60], source="llm", confidence=Confidence.AI_INFERRED,
                            suggestion=finding.suggested_correction.strip()))
    return issues, dropped


def top_level_names(code: str) -> set[str]:
    """Top-level function and class names (used to check interface preservation)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _clean_candidate(text: str, fallback: str) -> str:
    candidate = strip_code_fences(text or "").strip("\n")
    return normalize_code(candidate) if candidate.strip() else fallback


def _serious(issues: list[Issue]) -> set[tuple]:
    return {(i.category.value, i.message.split(" [")[0]) for i in issues
            if i.severity in (Severity.CRITICAL, Severity.ERROR)}


class AIDebugger:
    """Orchestrates analysis, AI correction, verification and repair."""

    def __init__(self, settings: Settings, llm: Optional[LLMClient] = None,
                 validator: Optional[TestValidator] = None, use_pylint: bool = True) -> None:
        self.settings = settings
        self.llm = llm
        self.validator = validator
        self.use_pylint = use_pylint

    # ------------------------------------------------------------------
    def debug(self, code: str, expected_behavior: str = "", test_code: str = "", mode: str = "hybrid") -> DebugResult:
        """Run the pipeline and return a :class:`DebugResult`.

        Raises:
            utils.validators.InputValidationError: if ``code`` is empty or too large.
        """
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        started = time.perf_counter()
        validate_code_input(code, self.settings.max_code_chars, self.settings.max_code_lines)
        code = normalize_code(code)
        result = DebugResult(session_id=new_session_id(), mode=mode, original_code=code, corrected_code=code,
                             expected_behavior=expected_behavior.strip(),
                             model_name=getattr(self.llm, "model", "") if self.llm else "")

        # 1-3. Static analysis and metrics -----------------------------------
        t0 = time.perf_counter()
        static = analyze_static(code, use_pylint=self.use_pylint,
                                timeout=self.settings.static_analysis_timeout)
        result.static_issues = static.issues if mode != "llm_only" else []
        result.pylint_error = static.pylint_error
        result.stage_timings["static_analysis"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        result.metrics_before = analyze_complexity(code)
        result.quality_before = compute_quality_score(static.issues, result.metrics_before)
        result.stage_timings["complexity"] = time.perf_counter() - t0

        if mode == "static":
            result.repair_status = "not_attempted"
            result.llm_message = "Static-analysis baseline: no AI correction requested."
        elif self.llm is None:
            result.repair_status = "not_attempted"
            result.llm_message = "AI engine disabled or unavailable: showing static analysis only."
        else:
            self._run_llm(result, static.issues, test_code, mode)

        # Post-correction analysis -----------------------------------------
        if result.code_changed:
            t0 = time.perf_counter()
            after = analyze_static(result.corrected_code, use_pylint=self.use_pylint,
                                   timeout=self.settings.static_analysis_timeout)
            result.after_issues = after.issues
            result.metrics_after = analyze_complexity(result.corrected_code)
            result.quality_after = compute_quality_score(after.issues, result.metrics_after)
            result.stage_timings["re_analysis"] = time.perf_counter() - t0
            missing = top_level_names(code) - top_level_names(result.corrected_code)
            if missing:
                result.notes.append("The correction removed or renamed: " + ", ".join(sorted(missing))
                                    + ". Review that the public interface is preserved.")
        elif result.llm_used:
            result.after_issues = result.static_issues
            result.metrics_after = result.metrics_before
            result.quality_after = result.quality_before

        result.duration = time.perf_counter() - started
        logger.info("debug run finished", extra={"session": result.session_id, "mode": mode,
                                                 "status": result.repair_status, "attempts": result.attempts,
                                                 "seconds": round(result.duration, 2)})
        return result

    # ------------------------------------------------------------------
    def _ask(self, prompt: str) -> AIDebugResponse:
        assert self.llm is not None
        return self.llm.generate_json(prompt, AIDebugResponse, system=SYSTEM_PROMPT)

    def _run_llm(self, result: DebugResult, issues: list[Issue], test_code: str, mode: str) -> None:
        code = result.original_code
        max_attempts = 1 if mode == "llm_only" else max(1, self.settings.max_repair_attempts)
        prompt = build_debug_prompt(code, issues if mode == "hybrid" else [], result.expected_behavior)
        t0 = time.perf_counter()
        try:
            response = self._ask(prompt)
        except LLMUnavailableError as exc:
            result.repair_status, result.llm_message = "llm_failed", f"{exc} Showing static analysis only."
            result.stage_timings["llm"] = time.perf_counter() - t0
            return
        except LLMError as exc:
            result.repair_status, result.llm_message = "llm_failed", f"AI response unusable: {exc}"
            result.stage_timings["llm"] = time.perf_counter() - t0
            return
        result.llm_used = True
        result.attempts = 1
        result.llm_message = f"Analysed with {result.model_name or 'LLM'}."
        candidate = _clean_candidate(response.corrected_code, code)
        self._absorb(result, response)

        if mode == "llm_only":
            result.corrected_code = candidate
            result.repair_status = "unverified" if check_syntax(candidate)[1] is None else "invalid_syntax"
            if not result.code_changed and response.no_bugs_found:
                result.repair_status = "no_changes"
            result.stage_timings["llm"] = time.perf_counter() - t0
            return

        baseline_serious = _serious(issues)
        test_report: Optional[TestReport] = None
        while True:
            failure, test_report = self._verify(candidate, code, test_code, baseline_serious)
            if not failure or result.attempts >= max_attempts:
                break
            result.attempts += 1
            result.notes.append(f"Attempt {result.attempts - 1} failed validation; requesting a repair.")
            try:
                response = self._ask(build_repair_prompt(code, candidate, failure, result.expected_behavior))
            except LLMError as exc:
                result.notes.append(f"Repair attempt {result.attempts} failed: {exc}")
                break
            candidate = _clean_candidate(response.corrected_code, candidate)
            self._absorb(result, response)
        result.stage_timings["llm_and_validation"] = time.perf_counter() - t0

        result.corrected_code = candidate
        result.test_report = test_report
        if check_syntax(candidate)[1] is not None:
            result.repair_status = "invalid_syntax"
        elif test_report is not None and test_report.status == "passed":
            result.repair_status = "verified"
        elif failure:
            result.repair_status = "failed_validation"
            result.notes.append("Final validation failure: " + failure[:500])
        elif not result.code_changed:
            result.repair_status = "no_changes"
        else:
            result.repair_status = "unverified"

    def _absorb(self, result: DebugResult, response: AIDebugResponse) -> None:
        """Merge an LLM response into the result (latest response wins for text)."""
        ai_issues, dropped = ai_findings_to_issues(response.findings, result.original_code)
        if ai_issues or not result.ai_issues:
            result.ai_issues = ai_issues
        if dropped:
            result.notes.append(f"Discarded {dropped} AI finding(s) that referenced non-existent lines or had no "
                                "description.")
        result.explanation = response.explanation.strip() or result.explanation
        result.changes = response.changes or result.changes
        result.optimization_suggestions = response.optimization_suggestions or result.optimization_suggestions
        result.assumptions = response.assumptions or result.assumptions

    def _verify(self, candidate: str, original: str, test_code: str,
                baseline_serious: set[tuple]) -> tuple[str, Optional[TestReport]]:
        """Return (failure_description, test_report). Empty failure means it passed."""
        _tree, fatal, _ = check_syntax(candidate)
        if fatal is not None:
            return f"The corrected code has a syntax error on line {fatal.line}: {fatal.message}", None
        if candidate.strip() != original.strip():
            after = analyze_static(candidate, use_pylint=self.use_pylint,
                                   timeout=self.settings.static_analysis_timeout)
            new_problems = _serious(after.issues) - baseline_serious
            if new_problems:
                details = "; ".join(f"{cat}: {msg}" for cat, msg in sorted(new_problems))
                return f"Static analysis found new errors in the correction: {details}", None
        if test_code.strip() and self.validator is not None:
            report = self.validator.validate(candidate, test_code)
            if report.status in ("failed", "error"):
                return report.failure_details or report.message, report
            return "", report
        return "", None
