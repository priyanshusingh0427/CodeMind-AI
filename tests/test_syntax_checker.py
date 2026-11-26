"""Tests for core.syntax_checker."""

from core.syntax_checker import analyze_syntax, is_valid_python
from utils.validators import Category, Confidence, Severity


def categories(code: str) -> set[str]:
    return {issue.category.value for issue in analyze_syntax(code).issues}


def test_valid_code_has_no_errors():
    report = analyze_syntax("def add(a, b):\n    return a + b\n")
    assert report.is_valid
    assert not [i for i in report.issues if i.severity in (Severity.CRITICAL, Severity.ERROR)]
    assert report.functions[0].name == "add"
    assert report.functions[0].args == ["a", "b"]


def test_syntax_error_is_critical_with_line():
    report = analyze_syntax("def f(x)\n    return x\n")
    assert not report.is_valid
    issue = report.issues[0]
    assert issue.category == Category.SYNTAX
    assert issue.severity == Severity.CRITICAL
    assert issue.line == 1
    assert issue.confidence == Confidence.CONFIRMED


def test_indentation_error_detected():
    report = analyze_syntax("def f(x):\nreturn x\n")
    assert not report.is_valid
    assert report.issues[0].category == Category.INDENTATION


def test_undefined_variable_detected_with_line():
    report = analyze_syntax("def f():\n    total = 1\n    return totl\n")
    undefined = [i for i in report.issues if i.category == Category.UNDEFINED_NAME]
    assert len(undefined) == 1
    assert undefined[0].line == 3
    assert "totl" in undefined[0].message


def test_builtins_and_globals_are_not_undefined():
    code = "LIMIT = 3\ndef f(xs):\n    return len(xs) + LIMIT + max(xs)\n"
    assert Category.UNDEFINED_NAME.value not in categories(code)


def test_global_declared_in_function_counts_as_defined():
    code = "def setup():\n    global counter\n    counter = 0\n\ndef inc():\n    return counter + 1\n"
    assert Category.UNDEFINED_NAME.value not in categories(code)


def test_missing_import_detected():
    report = analyze_syntax("def h(a, b):\n    return math.sqrt(a * a + b * b)\n")
    missing = [i for i in report.issues if i.category == Category.MISSING_IMPORT]
    assert missing and "import math" in missing[0].suggestion


def test_star_import_disables_undefined_check():
    assert Category.UNDEFINED_NAME.value not in categories("from math import *\nprint(sqrt(2))\n")


def test_unreachable_code_detected():
    report = analyze_syntax("def f():\n    return 1\n    print('never')\n")
    unreachable = [i for i in report.issues if i.category == Category.UNREACHABLE]
    assert unreachable and unreachable[0].line == 3


def test_unused_local_variable_detected():
    report = analyze_syntax("def f():\n    temp = 5\n    return 1\n")
    assert any(i.category == Category.UNUSED and "temp" in i.message for i in report.issues)


def test_bad_practices_detected():
    code = ("def f(x, acc=[]):\n    try:\n        return x / 0\n    except:\n        pass\n"
            "    if x == None:\n        return 1\n")
    symbols = {i.symbol for i in analyze_syntax(code).issues}
    assert {"mutable-default", "bare-except", "silent-except", "none-comparison", "division-by-zero"} <= symbols


def test_string_plus_number_type_issue():
    assert Category.TYPE.value in categories("x = 'a' + 1\n")


def test_infinite_loop_is_heuristic():
    report = analyze_syntax("def f():\n    while True:\n        x = 1\n")
    loops = [i for i in report.issues if i.symbol == "infinite-loop"]
    assert loops and loops[0].confidence == Confidence.HEURISTIC


def test_comprehension_and_lambda_scopes_are_handled():
    code = "def f(xs):\n    return [y * 2 for y in xs] + list(map(lambda z: z + 1, xs))\n"
    assert Category.UNDEFINED_NAME.value not in categories(code)


def test_is_valid_python():
    assert is_valid_python("x = 1\n")
    assert not is_valid_python("x = (\n")
