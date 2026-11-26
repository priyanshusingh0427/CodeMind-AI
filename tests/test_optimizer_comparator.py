"""Tests for the optimizer, code comparison and report generation."""

import json

from core.code_comparator import compare_code, render_side_by_side_html
from core.optimizer import analyze_optimizations, estimate_time_complexity
from utils.report_generator import generate_json_report, generate_pdf_report

import ast


def titles(code):
    return {s.title for s in analyze_optimizations(code).suggestions}


def test_range_len_and_append_loop():
    code = "def f(xs):\n    out = []\n    for i in range(len(xs)):\n        out.append(xs[i] * 2)\n    return out\n"
    found = titles(code)
    assert "Iterate directly instead of range(len(...))" in found
    assert "Use a list comprehension" in found


def test_string_concat_membership_and_sum():
    code = ("def f(words, banned_list):\n    banned = []\n    text = ''\n    total = 0\n    for w in words:\n"
            "        if w in banned:\n            continue\n        text += w\n    for n in words:\n"
            "        total += n\n    return text, total\n")
    found = titles(code)
    assert {"Avoid string concatenation in a loop", "Use a set for membership tests", "Use the built-in sum()"} <= found


def test_heuristic_complexity():
    assert estimate_time_complexity(ast.parse("x = 1\n"))[0] == "O(1)"
    nested = "for i in range(3):\n    for j in range(3):\n        pass\n"
    assert estimate_time_complexity(ast.parse(nested))[0] == "O(n^2)"
    fib = "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n"
    assert estimate_time_complexity(ast.parse(fib))[0] == "O(2^n)"
    # Loops inside functions count too (regression: they used to be skipped, giving O(1)).
    in_func = "def f(xs):\n    for a in xs:\n        for b in xs:\n            print(a, b)\n"
    assert estimate_time_complexity(ast.parse(in_func))[0] == "O(n^2)"
    method = "class C:\n    def m(self, xs):\n        return [x for x in xs]\n"
    assert estimate_time_complexity(ast.parse(method))[0] == "O(n)"


def test_optimizer_handles_invalid_code():
    report = analyze_optimizations("def f(:\n")
    assert report.heuristic_time_complexity == "n/a"


def test_compare_code_counts():
    diff = compare_code("a = 1\nb = 2\nc = 3\n", "a = 1\nb = 20\nc = 3\nd = 4\n")
    assert (diff.added, diff.removed, diff.modified) == (1, 0, 1)
    assert diff.changed and "+d = 4" in diff.unified
    html = render_side_by_side_html(diff)
    assert "cm-add" in html and "cm-del" in html


def test_compare_identical():
    assert not compare_code("x = 1\n", "x = 1\n").changed


def test_html_escaping_in_diff():
    html = render_side_by_side_html(compare_code("s = '<b>'\n", "s = '<i>'\n"))
    assert "<b>" not in html and "&lt;" in html


def test_reports(settings):
    from core.ai_debugger import AIDebugger
    payload = AIDebugger(settings, use_pylint=False).debug("def f():\n    return x\n").to_dict()
    data = json.loads(generate_json_report(payload))
    assert data["project"] == "CodeMind AI" and data["limitations"] and data["recommendations"]
    pdf = generate_pdf_report(payload)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500


def test_memory_rules():
    code = ("def f(xs, path):\n    out = []\n    total = sum([x * x for x in xs])\n    ok = any([x > 3 for x in xs])\n"
            "    n = len([x for x in xs if x])\n    for x in list(range(10)):\n        out += [x]\n"
            "    with open(path) as fh:\n        for line in fh.readlines():\n            print(line)\n"
            "    return out, total, ok, n\n")
    report = analyze_optimizations(code)
    memory = {s.title for s in report.suggestions if s.category == "memory"}
    assert {"Pass a generator to sum()", "Pass a generator to any()", "Count without building a list",
            "Iterate without building a list", "Use append() instead of += [item]",
            "Iterate over the file instead of readlines()"} <= memory


def test_memory_rules_do_not_fire_on_idiomatic_code():
    code = "def f(xs):\n    total = sum(x * x for x in xs)\n    for x in xs:\n        print(x)\n    return total\n"
    assert not [s for s in analyze_optimizations(code).suggestions if s.category == "memory"]


def test_heuristic_space_complexity():
    from core.optimizer import estimate_space_complexity

    assert estimate_space_complexity(ast.parse("def f(xs):\n    return max(xs)\n"))[0] == "O(1)"
    assert estimate_space_complexity(ast.parse("def f(xs):\n    return [x * 2 for x in xs]\n"))[0] == "O(n)"
    grow = "def f(xs):\n    seen = set()\n    for x in xs:\n        seen.add(x)\n    return seen\n"
    assert estimate_space_complexity(ast.parse(grow))[0] == "O(n)"
    table = "def f(n):\n    return [[0 for _ in range(n)] for _ in range(n)]\n"
    assert estimate_space_complexity(ast.parse(table))[0] == "O(n^2)"
    rec = "def fact(n):\n    return 1 if n <= 1 else n * fact(n - 1)\n"
    space, reason = estimate_space_complexity(ast.parse(rec))
    assert space == "O(n)" and "fact" in reason
    assert analyze_optimizations("def f(:\n").heuristic_space_complexity == "n/a"
