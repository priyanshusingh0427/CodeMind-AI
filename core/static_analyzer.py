"""Static analysis with Pylint, merged with the AST checks.

Pylint runs in a subprocess (``python -m pylint --from-stdin``) inside an empty
temporary directory, so it cannot pick up project files and the submitted code
is never imported or executed. If Pylint is missing or times out, the analyzer
degrades gracefully to the AST findings only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

from core.syntax_checker import SyntaxReport, analyze_syntax
from utils.logger import get_logger
from utils.validators import Category, Confidence, Issue, Severity

logger = get_logger("static_analyzer")

# Messages that are pure noise for short snippets.
DISABLED_MESSAGES = ["missing-module-docstring", "too-few-public-methods", "import-outside-toplevel"]

SYMBOL_CATEGORY: dict[str, Category] = {
    "undefined-variable": Category.UNDEFINED_NAME,
    "undefined-loop-variable": Category.UNDEFINED_NAME,
    "used-before-assignment": Category.RUNTIME,
    "possibly-used-before-assignment": Category.RUNTIME,
    "import-error": Category.MISSING_IMPORT,
    "no-name-in-module": Category.MISSING_IMPORT,
    "unused-import": Category.UNUSED,
    "unused-variable": Category.UNUSED,
    "unused-argument": Category.UNUSED,
    "unreachable": Category.UNREACHABLE,
    "no-member": Category.TYPE,
    "not-callable": Category.TYPE,
    "unsubscriptable-object": Category.TYPE,
    "not-an-iterable": Category.TYPE,
    "unsupported-binary-operation": Category.TYPE,
    "invalid-unary-operand-type": Category.TYPE,
    "unsupported-membership-test": Category.TYPE,
    "no-value-for-parameter": Category.TYPE,
    "too-many-function-args": Category.TYPE,
    "unexpected-keyword-arg": Category.TYPE,
    "invalid-sequence-index": Category.TYPE,
    "assignment-from-no-return": Category.LOGIC,
    "assignment-from-none": Category.LOGIC,
    "self-assigning-variable": Category.LOGIC,
    "comparison-with-itself": Category.LOGIC,
    "pointless-statement": Category.LOGIC,
    "expression-not-assigned": Category.LOGIC,
    "function-redefined": Category.LOGIC,
    "inconsistent-return-statements": Category.LOGIC,
    "dangerous-default-value": Category.BAD_PRACTICE,
    "bare-except": Category.BAD_PRACTICE,
    "broad-exception-caught": Category.BAD_PRACTICE,
    "redefined-builtin": Category.BAD_PRACTICE,
    "global-statement": Category.BAD_PRACTICE,
    "eval-used": Category.BAD_PRACTICE,
    "exec-used": Category.BAD_PRACTICE,
    "too-many-branches": Category.COMPLEXITY,
    "too-many-statements": Category.COMPLEXITY,
    "too-many-nested-blocks": Category.COMPLEXITY,
    "too-many-return-statements": Category.COMPLEXITY,
    "too-many-locals": Category.COMPLEXITY,
    "too-many-arguments": Category.COMPLEXITY,
    "syntax-error": Category.SYNTAX,
}

TYPE_SEVERITY: dict[str, Severity] = {
    "fatal": Severity.CRITICAL,
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "refactor": Severity.INFO,
    "convention": Severity.INFO,
    "info": Severity.INFO,
}


@dataclass
class StaticReport:
    """Combined AST + Pylint result."""

    syntax: SyntaxReport
    issues: list[Issue] = field(default_factory=list)
    pylint_available: bool = True
    pylint_error: str = ""

    @property
    def is_valid(self) -> bool:
        return self.syntax.is_valid

    def count(self, severity: Severity) -> int:
        return sum(1 for issue in self.issues if issue.severity == severity)


def map_pylint_message(msg: dict) -> Issue:
    """Convert one Pylint JSON message into an :class:`Issue`."""
    symbol = str(msg.get("symbol", ""))
    msg_type = str(msg.get("type", "warning"))
    category = SYMBOL_CATEGORY.get(symbol)
    if category is None:
        category = Category.STYLE if msg_type == "convention" else (
            Category.COMPLEXITY if msg_type == "refactor" else Category.OTHER)
    severity = TYPE_SEVERITY.get(msg_type, Severity.WARNING)
    if symbol == "import-error":
        severity = Severity.WARNING  # may simply be a package not installed locally
    line = msg.get("line")
    column = msg.get("column")
    return Issue(line=int(line) if isinstance(line, int) and line >= 0 else None,
                 column=int(column) if isinstance(column, int) and column >= 0 else None,
                 category=category, severity=severity,
                 message=f"{msg.get('message', '')} [{msg.get('message-id', '')}]".strip(),
                 symbol=symbol, source="pylint", confidence=Confidence.CONFIRMED)


def run_pylint(code: str, timeout: int = 60) -> tuple[list[Issue], str]:
    """Run Pylint on ``code`` and return (issues, error_message)."""
    command = [sys.executable, "-m", "pylint", "--from-stdin", "--output-format=json", "--score=n",
               "--persistent=n", "--disable=" + ",".join(DISABLED_MESSAGES), "submitted_code.py"]
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONSTARTUP"}}
    try:
        with tempfile.TemporaryDirectory(prefix="codemind_lint_") as workdir:
            completed = subprocess.run(command, input=code, capture_output=True, text=True, timeout=timeout,
                                       cwd=workdir, env=env, check=False)
    except FileNotFoundError:
        return [], "Python interpreter for Pylint not found."
    except subprocess.TimeoutExpired:
        logger.warning("pylint timed out", extra={"timeout": timeout})
        return [], f"Pylint timed out after {timeout} s."

    stdout = completed.stdout.strip()
    if not stdout:
        if "No module named pylint" in completed.stderr:
            return [], "Pylint is not installed (pip install pylint)."
        return [], ""  # no findings
    try:
        messages = json.loads(stdout)
    except json.JSONDecodeError:
        logger.warning("could not parse pylint output", extra={"stderr": completed.stderr[-500:]})
        return [], "Could not parse Pylint output."
    return [map_pylint_message(m) for m in messages if isinstance(m, dict)], ""


def merge_issues(primary: list[Issue], secondary: list[Issue]) -> list[Issue]:
    """Merge two issue lists, dropping secondary issues that duplicate primary ones.

    Two issues are duplicates when they are on the same line with the same
    category. The merged issue records both sources and keeps the more severe
    of the two severities.
    """
    merged: dict[tuple, Issue] = {}
    for issue in primary:
        merged.setdefault(issue.key(), issue)
    for issue in secondary:
        key = issue.key()
        if key in merged:
            existing = merged[key]
            update: dict = {}
            if issue.source not in existing.source:
                update["source"] = f"{existing.source}+{issue.source}"
            if issue.severity.rank < existing.severity.rank:  # keep the more severe rating
                update["severity"] = issue.severity
            if update:
                merged[key] = existing.model_copy(update=update)
        else:
            merged[key] = issue
    return sorted(merged.values(), key=lambda i: (i.severity.rank, i.line or 0))


def analyze_static(code: str, use_pylint: bool = True, timeout: int = 60) -> StaticReport:
    """Run AST analysis and (if the code parses) Pylint, returning merged issues."""
    syntax = analyze_syntax(code)
    if not syntax.is_valid:
        return StaticReport(syntax=syntax, issues=list(syntax.issues), pylint_available=use_pylint)
    pylint_issues: list[Issue] = []
    error = ""
    if use_pylint:
        pylint_issues, error = run_pylint(code, timeout=timeout)
    issues = merge_issues(syntax.issues, pylint_issues)
    return StaticReport(syntax=syntax, issues=issues, pylint_available=use_pylint and not error, pylint_error=error)
