"""Tests for core.static_analyzer and core.complexity_analyzer."""

import pytest

from core.complexity_analyzer import analyze_complexity, compute_quality_score, quality_grade
from core.static_analyzer import analyze_static, map_pylint_message, merge_issues
from utils.validators import Category, Issue, Severity

pylint = pytest.importorskip("pylint")


def test_pylint_findings_are_merged_with_ast():
    report = analyze_static("import os\n\ndef f(x):\n    return y\n")
    assert report.is_valid
    assert report.pylint_available, report.pylint_error
    sources = {i.source for i in report.issues}
    assert any("pylint" in s for s in sources)
    undefined = [i for i in report.issues if i.category == Category.UNDEFINED_NAME]
    assert len(undefined) == 1, "duplicate AST/Pylint findings must be merged"
    assert "ast" in undefined[0].source and "pylint" in undefined[0].source
    assert any(i.category == Category.UNUSED and "os" in i.message for i in report.issues)


def test_invalid_code_skips_pylint():
    report = analyze_static("def f(:\n")
    assert not report.is_valid
    assert report.issues[0].severity == Severity.CRITICAL


def test_map_pylint_message():
    issue = map_pylint_message({"type": "error", "symbol": "undefined-variable", "message": "Undefined 'z'",
                                "message-id": "E0602", "line": 4, "column": 2})
    assert issue.category == Category.UNDEFINED_NAME
    assert issue.severity == Severity.ERROR
    assert issue.line == 4 and "E0602" in issue.message


def test_merge_issues_deduplicates():
    a = Issue(line=2, category=Category.UNUSED, severity=Severity.INFO, message="x", source="ast")
    b = Issue(line=2, category=Category.UNUSED, severity=Severity.WARNING, message="y", source="pylint")
    merged = merge_issues([a], [b])
    assert len(merged) == 1 and merged[0].source == "ast+pylint"
    assert merged[0].severity == Severity.WARNING  # the more severe rating wins


def test_complexity_metrics():
    code = ("def grade(score):\n    if score > 90:\n        return 'A'\n    elif score > 80:\n        return 'B'\n"
            "    return 'C'\n")
    metrics = analyze_complexity(code)
    assert metrics.available
    assert metrics.functions[0].complexity == 3
    assert 0 <= metrics.maintainability_index <= 100
    assert metrics.loc == 6


def test_complexity_unavailable_for_invalid_code():
    assert not analyze_complexity("def f(:\n").available


def test_quality_score_formula():
    metrics = analyze_complexity("def f():\n    return 1\n")
    clean = compute_quality_score([], metrics)
    expected = round(0.7 * 100 + 0.3 * metrics.maintainability_index, 1)
    assert clean == expected
    one_error = compute_quality_score([Issue(line=1, severity=Severity.ERROR, message="e")], metrics)
    assert one_error == round(clean - 7.0, 1)
    critical = compute_quality_score([Issue(line=1, severity=Severity.CRITICAL, message="c")], metrics)
    assert critical <= 20
    assert quality_grade(95) == "A" and quality_grade(10) == "F"
