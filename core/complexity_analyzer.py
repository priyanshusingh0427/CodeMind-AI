"""Code complexity and quality metrics using Radon.

All values here are *measured* (computed deterministically from the source),
as opposed to AI estimates. The quality score formula is documented in
:func:`compute_quality_score` and in ``docs/methodology.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from utils.validators import Issue, Severity

try:
    from radon.complexity import cc_rank, cc_visit
    from radon.metrics import h_visit, mi_visit
    from radon.raw import analyze as raw_analyze

    RADON_AVAILABLE = True
except ImportError:  # pragma: no cover - radon is a hard requirement
    RADON_AVAILABLE = False

# Weights used by the quality-score formula.
SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.CRITICAL: 25.0,
    Severity.ERROR: 10.0,
    Severity.WARNING: 3.0,
    Severity.INFO: 0.5,
}
MAX_INFO_PENALTY = 10.0
COMPLEXITY_THRESHOLD = 10
COMPLEXITY_PENALTY = 3.0


@dataclass
class FunctionComplexity:
    name: str
    lineno: int
    complexity: int
    rank: str


@dataclass
class ComplexityReport:
    """Measured metrics for a piece of code."""

    loc: int = 0
    lloc: int = 0
    sloc: int = 0
    comments: int = 0
    blank: int = 0
    average_complexity: float = 0.0
    max_complexity: int = 0
    maintainability_index: float = 0.0
    halstead_volume: float = 0.0
    halstead_difficulty: float = 0.0
    halstead_effort: float = 0.0
    functions: list[FunctionComplexity] = field(default_factory=list)
    available: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_complexity(code: str) -> ComplexityReport:
    """Compute raw metrics, cyclomatic complexity, MI and Halstead metrics.

    Code that does not parse returns a report with ``available=False``.
    """
    if not RADON_AVAILABLE:
        return ComplexityReport(available=False, error="radon is not installed")
    try:
        raw = raw_analyze(code)
        blocks = cc_visit(code)
        maintainability = float(mi_visit(code, multi=True))
        halstead = h_visit(code).total
    except (SyntaxError, ValueError, TypeError, IndentationError) as exc:
        lines = code.splitlines()
        return ComplexityReport(loc=len(lines), available=False, error=f"Metrics unavailable: {exc}")

    functions = [FunctionComplexity(name=getattr(b, "fullname", b.name), lineno=b.lineno, complexity=b.complexity,
                                    rank=cc_rank(b.complexity)) for b in blocks]
    complexities = [f.complexity for f in functions]
    return ComplexityReport(
        loc=raw.loc, lloc=raw.lloc, sloc=raw.sloc, comments=raw.comments + raw.multi, blank=raw.blank,
        average_complexity=round(sum(complexities) / len(complexities), 2) if complexities else 1.0,
        max_complexity=max(complexities) if complexities else 1,
        maintainability_index=round(maintainability, 2),
        halstead_volume=round(float(halstead.volume or 0.0), 2),
        halstead_difficulty=round(float(halstead.difficulty or 0.0), 2),
        halstead_effort=round(float(halstead.effort or 0.0), 2),
        functions=functions,
    )


def compute_quality_score(issues: list[Issue], metrics: ComplexityReport) -> float:
    """Return a 0–100 code quality score.

    Formula (documented and deterministic)::

        issue_penalty = 25*critical + 10*error + 3*warning + min(10, 0.5*info)
        complexity_penalty = 3 * (number of functions with cyclomatic complexity > 10)
        issue_score = max(0, 100 - issue_penalty - complexity_penalty)
        mi = radon maintainability index (0-100), or 50 if unavailable
        quality = 0.7 * issue_score + 0.3 * mi       (clipped to [0, 100])

    If the code has a syntax error the score is capped at 20, because the
    program cannot run at all.
    """
    info_penalty = min(MAX_INFO_PENALTY, sum(SEVERITY_PENALTY[Severity.INFO] for i in issues
                                             if i.severity == Severity.INFO))
    issue_penalty = sum(SEVERITY_PENALTY[i.severity] for i in issues if i.severity != Severity.INFO) + info_penalty
    complex_functions = sum(1 for f in metrics.functions if f.complexity > COMPLEXITY_THRESHOLD)
    issue_score = max(0.0, 100.0 - issue_penalty - COMPLEXITY_PENALTY * complex_functions)
    mi = metrics.maintainability_index if metrics.available else 50.0
    score = 0.7 * issue_score + 0.3 * max(0.0, min(100.0, mi))
    if any(i.severity == Severity.CRITICAL for i in issues):
        score = min(score, 20.0)
    return round(max(0.0, min(100.0, score)), 1)


def quality_grade(score: float) -> str:
    """Map a quality score to a letter grade."""
    for threshold, grade in ((90, "A"), (80, "B"), (65, "C"), (50, "D")):
        if score >= threshold:
            return grade
    return "F"
