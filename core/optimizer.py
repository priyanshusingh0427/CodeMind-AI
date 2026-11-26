"""Code optimisation analysis.

Three kinds of output are produced and always labelled separately:

* **Measured** – deterministic metrics from Radon (LOC, cyclomatic complexity,
  maintainability index, Halstead volume).
* **Rule-based** – AST pattern detectors (e.g. ``range(len(x))``, string
  concatenation in loops, manual sums, duplicated blocks). The patterns are
  confirmed; the *benefit* is a general guideline.
* **AI estimate** – suggestions and time/space complexity from the LLM, which
  may be wrong and must be reviewed.

Heuristic Big-O estimates (time from loop nesting depth and recursion shape;
auxiliary space from container allocations and recursion depth) are labelled as
heuristics, not measurements.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from core.complexity_analyzer import ComplexityReport, analyze_complexity
from core.llm_engine import LLMClient, LLMError
from utils.logger import get_logger
from utils.prompts import SYSTEM_PROMPT, build_optimize_prompt
from utils.validators import AIOptimizationResponse

logger = get_logger("optimizer")


@dataclass
class Suggestion:
    line: Optional[int]
    title: str
    detail: str
    category: str  # readability | performance | redundancy | complexity | standards | memory
    source: str = "rule"  # rule | measured | ai


@dataclass
class OptimizationReport:
    metrics: ComplexityReport
    suggestions: list[Suggestion] = field(default_factory=list)
    heuristic_time_complexity: str = "O(1)"
    heuristic_reason: str = ""
    heuristic_space_complexity: str = "O(1)"
    heuristic_space_reason: str = ""
    ai_suggestions: list[str] = field(default_factory=list)
    ai_time_complexity: str = ""
    ai_space_complexity: str = ""
    ai_optimized_code: str = ""
    ai_explanation: str = ""
    ai_error: str = ""


def _loop_depth(node: ast.AST, depth: int = 0) -> int:
    """Maximum nesting depth of for/while loops (comprehensions count as loops)."""
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
            best = max(best, _loop_depth(child, depth + 1))
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            best = max(best, depth + len(child.generators), _loop_depth(child, depth + len(child.generators)))
        else:
            best = max(best, _loop_depth(child, depth))
    return best


def _self_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return sum(1 for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == func.name)


def _has_cache_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name in {"lru_cache", "cache", "cached"}:
            return True
    return False


class _LoopPatternVisitor(ast.NodeVisitor):
    """Detect common inefficient or non-idiomatic patterns."""

    def __init__(self) -> None:
        self.suggestions: list[Suggestion] = []
        self._loop_stack: list[ast.AST] = []
        self._list_vars: set[str] = set()
        self._string_vars: set[str] = set()
        self._numeric_zero_vars: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            if isinstance(target, ast.Name):
                value = node.value
                if isinstance(value, ast.List) or (isinstance(value, ast.Call) and getattr(value.func, "id", "")
                                                    == "list"):
                    self._list_vars.add(target.id)
                if isinstance(value, ast.Constant) and value.value == "":
                    self._string_vars.add(target.id)
                if isinstance(value, ast.Constant) and value.value == 0 and not isinstance(value.value, bool):
                    self._numeric_zero_vars.add(target.id)
        self.generic_visit(node)

    def _visit_loop(self, node: ast.For | ast.While | ast.AsyncFor) -> None:
        self._loop_stack.append(node)
        if isinstance(node, ast.For):
            self._check_materialised_iter(node)
            self._check_range_len(node)
            self._check_append_loop(node)
            self._check_manual_sum(node)
        self.generic_visit(node)
        self._loop_stack.pop()

    visit_For = _visit_loop  # noqa: N815
    visit_AsyncFor = _visit_loop  # noqa: N815
    visit_While = _visit_loop  # noqa: N815

    def _check_materialised_iter(self, node: ast.For) -> None:
        """``for x in list(...)`` / ``for line in f.readlines()`` build a whole list just to iterate it."""
        it = node.iter
        if not isinstance(it, ast.Call):
            return
        if isinstance(it.func, ast.Name) and it.func.id == "list" and len(it.args) == 1 and not it.keywords:
            inner = ast.unparse(it.args[0])
            self.suggestions.append(Suggestion(
                node.lineno, "Iterate without building a list",
                f"`for ... in list({inner})` copies every item into a new list first. Iterate over `{inner}` "
                "directly (only keep `list()` if the loop modifies the original collection).", "memory"))
        elif isinstance(it.func, ast.Attribute) and it.func.attr == "readlines" and not it.args:
            handle = ast.unparse(it.func.value)
            self.suggestions.append(Suggestion(
                node.lineno, "Iterate over the file instead of readlines()",
                f"`{handle}.readlines()` loads the whole file into memory. `for line in {handle}:` reads one "
                "line at a time (O(1) extra memory).", "memory"))

    def _check_range_len(self, node: ast.For) -> None:
        it = node.iter
        if isinstance(it, ast.Call) and getattr(it.func, "id", "") == "range" and len(it.args) == 1:
            arg = it.args[0]
            if isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "len" and arg.args:
                seq = ast.unparse(arg.args[0])
                self.suggestions.append(Suggestion(
                    node.lineno, "Iterate directly instead of range(len(...))",
                    f"`for i in range(len({seq}))` can usually be written as `for item in {seq}` or "
                    f"`for i, item in enumerate({seq})`, which is clearer and avoids repeated indexing.",
                    "readability"))

    def _check_append_loop(self, node: ast.For) -> None:
        body = node.body
        stmt = body[0] if len(body) == 1 else None
        if isinstance(stmt, ast.If) and len(stmt.body) == 1 and not stmt.orelse:
            stmt = stmt.body[0]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func,
                                                                                          ast.Attribute) \
                and stmt.value.func.attr == "append" and not node.orelse:
            target = ast.unparse(stmt.value.func.value)
            self.suggestions.append(Suggestion(
                node.lineno, "Use a list comprehension",
                f"This loop only appends to `{target}`. A list comprehension is shorter and typically faster "
                "in CPython.", "performance"))

    def _check_manual_sum(self, node: ast.For) -> None:
        if len(node.body) == 1 and isinstance(node.body[0], ast.AugAssign) and isinstance(node.body[0].op, ast.Add):
            target = node.body[0].target
            if isinstance(target, ast.Name) and target.id in self._numeric_zero_vars:
                self.suggestions.append(Suggestion(
                    node.lineno, "Use the built-in sum()",
                    f"The loop accumulates into `{target.id}`; `sum(...)` expresses this directly and runs in C.",
                    "readability"))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802
        if self._loop_stack and isinstance(node.op, ast.Add) and isinstance(node.target, ast.Name) \
                and node.target.id in self._list_vars and isinstance(node.value, ast.List) and len(node.value.elts) == 1:
            self.suggestions.append(Suggestion(
                node.lineno, "Use append() instead of += [item]",
                f"`{node.target.id} += [x]` builds a temporary one-element list on every iteration; "
                f"`{node.target.id}.append(x)` avoids the extra allocation.", "memory"))
        if self._loop_stack and isinstance(node.op, ast.Add) and isinstance(node.target, ast.Name) \
                and node.target.id in self._string_vars:
            self.suggestions.append(Suggestion(
                node.lineno, "Avoid string concatenation in a loop",
                f"Repeated `{node.target.id} += ...` can be quadratic. Collect parts in a list and use "
                "`''.join(parts)`.", "performance"))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                if self._loop_stack and isinstance(comp, ast.Name) and comp.id in self._list_vars:
                    self.suggestions.append(Suggestion(
                        node.lineno, "Use a set for membership tests",
                        f"`in {comp.id}` inside a loop scans the list each time (O(n)). Converting `{comp.id}` "
                        "to a set gives O(1) average lookups.", "performance"))
                if isinstance(comp, ast.Call) and isinstance(comp.func, ast.Attribute) and comp.func.attr == "keys":
                    self.suggestions.append(Suggestion(node.lineno, "Drop the .keys() call",
                                                       "`key in d.keys()` is the same as `key in d`.", "redundancy"))
        if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq) and isinstance(node.left, ast.Call) \
                and getattr(node.left.func, "id", "") == "len" and isinstance(node.comparators[0], ast.Constant) \
                and node.comparators[0].value == 0:
            self.suggestions.append(Suggestion(node.lineno, "Use truthiness for emptiness checks",
                                               "`len(x) == 0` can be written as `not x` (PEP 8).", "standards"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id in {"sum", "any", "all", "min", "max"} \
                and len(node.args) == 1 and isinstance(node.args[0], ast.ListComp):
            self.suggestions.append(Suggestion(
                node.lineno, f"Pass a generator to {node.func.id}()",
                f"`{node.func.id}([...])` builds the whole list first. `{node.func.id}(... for ...)` (drop the "
                "square brackets) uses O(1) extra memory" + (" and can stop early." if node.func.id in {"any", "all"}
                                                            else "."), "memory"))
        if isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1 \
                and isinstance(node.args[0], ast.ListComp):
            self.suggestions.append(Suggestion(
                node.lineno, "Count without building a list",
                "`len([... for ...])` materialises a list only to count it; `sum(1 for ...)` counts in O(1) memory.",
                "memory"))
        if self._loop_stack:
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in {"sort", "sorted"}:
                self.suggestions.append(Suggestion(
                    node.lineno, "Sorting inside a loop",
                    "Sorting on every iteration costs O(n log n) each time. Sort once outside the loop or use "
                    "`heapq`/`bisect`.", "performance"))
        self.generic_visit(node)


def _duplicate_blocks(tree: ast.Module) -> list[Suggestion]:
    """Find compound statements (>=3 lines) that appear more than once verbatim."""
    seen: dict[str, list[int]] = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.If, ast.With, ast.Try)) and \
                (getattr(node, "end_lineno", node.lineno) - node.lineno) >= 2:
            seen[ast.dump(node, annotate_fields=False)].append(node.lineno)
    return [Suggestion(lines[1], "Repeated code block",
                       f"The block at line {lines[1]} duplicates line {lines[0]}. Extract it into a function.",
                       "redundancy") for lines in seen.values() if len(lines) > 1]


def estimate_time_complexity(tree: ast.Module) -> tuple[str, str]:
    """Heuristic Big-O estimate from loop depth and recursion (NOT a measurement)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _self_calls(node) >= 2 \
                and not _has_cache_decorator(node):
            return "O(2^n)", f"'{node.name}' calls itself more than once without memoisation."
    # _loop_depth stops at function boundaries, so measure the module body and every function body separately.
    depth = max([_loop_depth(tree)] + [_loop_depth(n) for n in ast.walk(tree)
                                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))])
    has_sort = any(isinstance(n, ast.Call) and (getattr(n.func, "id", "") == "sorted" or
                                                getattr(n.func, "attr", "") == "sort") for n in ast.walk(tree))
    if depth == 0:
        return ("O(n log n)", "Uses sorting.") if has_sort else ("O(1)", "No loops or recursion found.")
    if depth == 1 and has_sort:
        return "O(n log n)", "One loop level plus sorting."
    label = "O(n)" if depth == 1 else f"O(n^{depth})"
    return label, f"Maximum loop nesting depth is {depth}."


_CONTAINER_CALLS = {"list", "dict", "set", "sorted", "tuple", "bytearray"}


def _is_container_alloc(node: ast.AST) -> bool:
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONTAINER_CALLS \
        and bool(node.args)


def _grows_in_loop(tree: ast.Module) -> bool:
    """True if a container is appended/added to inside a loop (size proportional to the input)."""
    for loop in ast.walk(tree):
        if isinstance(loop, (ast.For, ast.AsyncFor, ast.While)):
            for n in ast.walk(loop):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                        n.func.attr in {"append", "extend", "add", "insert", "update", "setdefault"}:
                    return True
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) for t in n.targets):
                    return True
    return False


def estimate_space_complexity(tree: ast.Module) -> tuple[str, str]:
    """Heuristic auxiliary-space estimate (NOT a measurement).

    Looks for nested comprehensions (O(n^2) tables), containers built from the
    input or grown in a loop (O(n)) and recursion (O(n) call stack in the worst
    case). Input arguments themselves are not counted.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)) and \
                isinstance(getattr(node, "elt", None), (ast.ListComp, ast.SetComp, ast.DictComp)):
            return "O(n^2)", "Builds a nested comprehension (a 2-D table)."
    recursive = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and _self_calls(n) >= 1]
    if any(_is_container_alloc(n) for n in ast.walk(tree)):
        return "O(n)", "Builds a new list/dict/set whose size can grow with the input."
    if _grows_in_loop(tree):
        return "O(n)", "Adds items to a container inside a loop."
    if recursive:
        return "O(n)", f"Recursion in '{recursive[0]}' uses call-stack space proportional to its depth."
    return "O(1)", "No input-sized containers or recursion found."


def analyze_optimizations(code: str, llm: Optional[LLMClient] = None) -> OptimizationReport:
    """Run measured + rule-based analysis, and optionally ask the LLM."""
    metrics = analyze_complexity(code)
    report = OptimizationReport(metrics=metrics)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        report.heuristic_reason = f"Code does not parse ({exc.msg}); fix syntax errors first."
        report.heuristic_time_complexity = "n/a"
        report.heuristic_space_complexity = "n/a"
        report.heuristic_space_reason = "Not estimated until the code parses."
        return report

    visitor = _LoopPatternVisitor()
    visitor.visit(tree)
    suggestions = visitor.suggestions + _duplicate_blocks(tree)
    for func in metrics.functions:
        if func.complexity > 10:
            suggestions.append(Suggestion(func.lineno, f"High cyclomatic complexity in '{func.name}'",
                                          f"Complexity {func.complexity} (rank {func.rank}). Split it into smaller "
                                          "functions or use early returns.", "complexity", "measured"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
            if length > 50:
                suggestions.append(Suggestion(node.lineno, f"Long function '{node.name}'",
                                              f"{length} lines long; consider splitting it.", "readability",
                                              "measured"))
            if _self_calls(node) >= 2 and not _has_cache_decorator(node):
                suggestions.append(Suggestion(node.lineno, f"Memoise recursive function '{node.name}'",
                                              "It calls itself more than once; `@functools.lru_cache` can avoid "
                                              "recomputing the same sub-problems.", "performance"))
            if ast.get_docstring(node) is None:
                suggestions.append(Suggestion(node.lineno, f"Add a docstring to '{node.name}'",
                                              "Docstrings document purpose, parameters and return values (PEP 257).",
                                              "standards"))
    # De-duplicate identical suggestions on the same line.
    unique: dict[tuple, Suggestion] = {}
    for s in suggestions:
        unique.setdefault((s.line, s.title), s)
    report.suggestions = sorted(unique.values(), key=lambda s: s.line or 0)
    report.heuristic_time_complexity, report.heuristic_reason = estimate_time_complexity(tree)
    report.heuristic_space_complexity, report.heuristic_space_reason = estimate_space_complexity(tree)

    if llm is not None:
        summary = (f"LOC={metrics.loc}, avg cyclomatic complexity={metrics.average_complexity}, "
                   f"maintainability index={metrics.maintainability_index}, heuristic time complexity="
                   f"{report.heuristic_time_complexity}, heuristic space complexity="
                   f"{report.heuristic_space_complexity}. Rule-based findings: "
                   + "; ".join(f"line {s.line}: {s.title}" for s in report.suggestions[:10]))
        try:
            ai = llm.generate_json(build_optimize_prompt(code, summary), AIOptimizationResponse, system=SYSTEM_PROMPT)
            report.ai_suggestions = ai.suggestions
            report.ai_time_complexity = ai.estimated_time_complexity
            report.ai_space_complexity = ai.estimated_space_complexity
            report.ai_optimized_code = ai.optimized_code.strip()
            report.ai_explanation = ai.explanation
        except LLMError as exc:
            report.ai_error = str(exc)
            logger.warning("ai optimisation failed", extra={"error": str(exc)})
    return report
