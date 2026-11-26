"""AST-based syntax and semantic analysis.

This module never executes the submitted code. It uses :mod:`ast` to parse the
source, :mod:`symtable` to resolve variable scopes, and a set of AST visitors to
flag deterministic problems: syntax/indentation errors, undefined names,
missing imports, unreachable code, unused variables and common bad practices.
Every finding produced here is ``Confidence.CONFIRMED`` (or ``HEURISTIC`` for
pattern-based warnings) because it is derived from the code structure, not
guessed by an AI model.
"""

from __future__ import annotations

import ast
import builtins
import symtable
import sys
import warnings
from dataclasses import dataclass, field
from typing import Optional

from utils.validators import Category, Confidence, Issue, Severity

BUILTIN_NAMES: frozenset[str] = frozenset(dir(builtins)) | {"__file__", "__name__", "__doc__", "__builtins__",
                                                            "__spec__", "__loader__", "__package__", "__path__",
                                                            "__annotations__", "__dict__", "__module__",
                                                            "__qualname__", "__class__"}

# Common third-party aliases that people use without importing.
COMMON_ALIASES: dict[str, str] = {
    "np": "import numpy as np", "pd": "import pandas as pd", "plt": "import matplotlib.pyplot as plt",
    "sns": "import seaborn as sns", "tf": "import tensorflow as tf", "torch": "import torch",
    "defaultdict": "from collections import defaultdict", "Counter": "from collections import Counter",
    "deque": "from collections import deque", "namedtuple": "from collections import namedtuple",
    "OrderedDict": "from collections import OrderedDict", "dataclass": "from dataclasses import dataclass",
    "reduce": "from functools import reduce", "lru_cache": "from functools import lru_cache",
    "partial": "from functools import partial", "Path": "from pathlib import Path",
    "datetime": "from datetime import datetime", "List": "from typing import List",
    "Dict": "from typing import Dict", "Optional": "from typing import Optional", "Any": "from typing import Any",
    "Tuple": "from typing import Tuple", "sqrt": "from math import sqrt", "pi": "from math import pi",
    "randint": "from random import randint", "choice": "from random import choice",
    "heappush": "from heapq import heappush", "heappop": "from heapq import heappop",
}
STDLIB_MODULES: frozenset[str] = frozenset(getattr(sys, "stdlib_module_names", ()))


@dataclass
class FunctionInfo:
    """Lightweight description of a function found in the code."""

    name: str
    lineno: int
    end_lineno: int
    args: list[str]
    has_docstring: bool
    is_method: bool = False


@dataclass
class SyntaxReport:
    """Result of AST analysis."""

    is_valid: bool
    issues: list[Issue] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    error_message: str = ""


def _issue(line: Optional[int], category: Category, severity: Severity, message: str, symbol: str = "",
           suggestion: str = "", confidence: Confidence = Confidence.CONFIRMED, column: Optional[int] = None) -> Issue:
    return Issue(line=line, column=column, category=category, severity=severity, message=message, symbol=symbol,
                 suggestion=suggestion, source="ast", confidence=confidence)


def check_syntax(code: str) -> tuple[Optional[ast.Module], Optional[Issue], list[Issue]]:
    """Parse ``code``. Returns (tree, fatal_issue, compiler_warnings)."""
    compiler_warnings: list[Issue] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            tree = ast.parse(code, filename="<submitted>", type_comments=False)
            compile(tree, "<submitted>", "exec", dont_inherit=True)
        for warning in caught:
            if issubclass(warning.category, SyntaxWarning):
                compiler_warnings.append(_issue(getattr(warning, "lineno", None), Category.BAD_PRACTICE,
                                                Severity.WARNING, f"Compiler warning: {warning.message}",
                                                symbol="syntax-warning"))
        return tree, None, compiler_warnings
    except IndentationError as exc:  # includes TabError
        category = Category.INDENTATION
        name = "TabError" if isinstance(exc, TabError) else "IndentationError"
        return None, _issue(exc.lineno, category, Severity.CRITICAL, f"{name}: {exc.msg}", symbol=name.lower(),
                            suggestion="Use consistent 4-space indentation and check block structure.",
                            column=exc.offset), []
    except SyntaxError as exc:
        return None, _issue(exc.lineno, Category.SYNTAX, Severity.CRITICAL, f"SyntaxError: {exc.msg}",
                            symbol="syntax-error", column=exc.offset,
                            suggestion="Check for missing colons, brackets, quotes or misspelled keywords."), []
    except (ValueError, RecursionError, MemoryError) as exc:
        return None, _issue(None, Category.SYNTAX, Severity.CRITICAL, f"Could not parse code: {exc}",
                            symbol="parse-failure"), []


# ---------------------------------------------------------------------------
# Scope analysis with symtable
# ---------------------------------------------------------------------------


def _first_lines_by_name(tree: ast.AST) -> tuple[dict[str, int], dict[str, int], set[str]]:
    """Map name -> first load line, name -> first store line, and attribute bases."""
    loads: dict[str, int] = {}
    stores: dict[str, int] = {}
    attr_bases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            target = loads if isinstance(node.ctx, ast.Load) else stores
            if node.id not in target or node.lineno < target[node.id]:
                target[node.id] = node.lineno
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            attr_bases.add(node.value.id)
    return loads, stores, attr_bases


def _iter_tables(table: symtable.SymbolTable):
    yield table
    for child in table.get_children():
        yield from _iter_tables(child)


def find_scope_issues(code: str, tree: ast.Module) -> list[Issue]:
    """Detect undefined names, missing imports and unused local variables."""
    issues: list[Issue] = []
    try:
        module_table = symtable.symtable(code, "<submitted>", "exec")
    except (SyntaxError, ValueError):
        return issues

    has_star_import = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
                          for n in ast.walk(tree))
    loads, stores, attr_bases = _first_lines_by_name(tree)

    module_defined = {s.get_name() for s in module_table.get_symbols()
                      if s.is_assigned() or s.is_imported() or s.is_namespace()}
    # Names declared `global` inside functions and assigned there also count.
    for table in _iter_tables(module_table):
        for sym in table.get_symbols():
            if sym.is_declared_global() and sym.is_assigned():
                module_defined.add(sym.get_name())

    reported: set[str] = set()
    if not has_star_import:
        for table in _iter_tables(module_table):
            is_module = table.get_type() == "module"
            for sym in table.get_symbols():
                name = sym.get_name()
                if not sym.is_referenced() or name in reported:
                    continue
                unresolved = (is_module and not (sym.is_assigned() or sym.is_imported())) or \
                             (not is_module and sym.is_global())
                if not unresolved or name in module_defined or name in BUILTIN_NAMES:
                    continue
                reported.add(name)
                line = loads.get(name)
                if name in COMMON_ALIASES or (name in STDLIB_MODULES and name in attr_bases):
                    fix = COMMON_ALIASES.get(name, f"import {name}")
                    issues.append(_issue(line, Category.MISSING_IMPORT, Severity.ERROR,
                                         f"'{name}' is used but never imported.", symbol="missing-import",
                                         suggestion=f"Add `{fix}` at the top of the file."))
                else:
                    issues.append(_issue(line, Category.UNDEFINED_NAME, Severity.ERROR,
                                         f"Name '{name}' is used but never defined (NameError at runtime).",
                                         symbol="undefined-name",
                                         suggestion="Define the variable before use or fix the spelling."))

    # Unused local variables inside functions.
    for table in _iter_tables(module_table):
        if table.get_type() != "function":
            continue
        for sym in table.get_symbols():
            name = sym.get_name()
            if (sym.is_assigned() and not sym.is_referenced() and not sym.is_parameter()
                    and not sym.is_global() and not sym.is_nonlocal() and not sym.is_imported()
                    and not sym.is_namespace() and not name.startswith("_")):
                issues.append(_issue(_find_store_line(tree, table.get_lineno(), name) or stores.get(name),
                                     Category.UNUSED, Severity.INFO,
                                     f"Local variable '{name}' in '{table.get_name()}' is assigned but never used.",
                                     symbol="unused-variable", suggestion="Remove it or prefix it with '_'."))
    return issues


def _find_store_line(tree: ast.Module, func_lineno: int, name: str) -> Optional[int]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno == func_lineno:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and inner.id == name and isinstance(inner.ctx, ast.Store):
                    return inner.lineno
    return None


# ---------------------------------------------------------------------------
# Pattern visitors
# ---------------------------------------------------------------------------

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_MUTABLE_DEFAULTS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)


class _PatternVisitor(ast.NodeVisitor):
    """Collect pattern-based findings in a single tree walk."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []

    # -- unreachable code ---------------------------------------------------
    def _check_body(self, body: list[ast.stmt]) -> None:
        for index, stmt in enumerate(body[:-1]):
            if isinstance(stmt, _TERMINATORS):
                nxt = body[index + 1]
                kind = type(stmt).__name__.lower()
                self.issues.append(_issue(nxt.lineno, Category.UNREACHABLE, Severity.WARNING,
                                          f"Code after '{kind}' on line {stmt.lineno} can never execute.",
                                          symbol="unreachable-code",
                                          suggestion="Remove the dead code or fix the control flow."))
                break

    def generic_visit(self, node: ast.AST) -> None:
        for attr in ("body", "orelse", "finalbody"):
            body = getattr(node, attr, None)
            if isinstance(body, list) and body and isinstance(body[0], ast.stmt):
                self._check_body(body)
        super().generic_visit(node)

    # -- functions ------------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._check_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_defaults(node)
        self.generic_visit(node)

    def _check_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]:
            if isinstance(default, _MUTABLE_DEFAULTS) or (
                    isinstance(default, ast.Call) and isinstance(default.func, ast.Name)
                    and default.func.id in {"list", "dict", "set"}):
                self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.WARNING,
                                          f"Function '{node.name}' uses a mutable default argument; it is shared "
                                          "between calls.", symbol="mutable-default",
                                          suggestion="Use None as the default and create the object inside."))
                break

    # -- exceptions -----------------------------------------------------------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if node.type is None:
            self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.WARNING,
                                      "Bare 'except:' also catches KeyboardInterrupt and SystemExit.",
                                      symbol="bare-except", suggestion="Catch a specific exception type."))
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.WARNING,
                                      "Exception is silently ignored ('except ...: pass').",
                                      symbol="silent-except", suggestion="Log or handle the exception."))
        self.generic_visit(node)

    # -- comparisons ------------------------------------------------------------
    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant) \
                    and comparator.value is None:
                self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.INFO,
                                          "Comparison to None should use 'is' / 'is not'.",
                                          symbol="none-comparison", suggestion="Use `x is None`."))
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant) \
                    and isinstance(comparator.value, bool):
                self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.INFO,
                                          "Comparison to True/False is redundant.",
                                          symbol="bool-comparison", suggestion="Use `if x:` or `if not x:`."))
        self.generic_visit(node)

    # -- runtime / type hazards -------------------------------------------------
    def visit_BinOp(self, node: ast.BinOp) -> None:  # noqa: N802
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and isinstance(node.right, ast.Constant) \
                and node.right.value == 0 and not isinstance(node.right.value, bool):
            self.issues.append(_issue(node.lineno, Category.RUNTIME, Severity.ERROR,
                                      "Division or modulo by the constant 0 raises ZeroDivisionError.",
                                      symbol="division-by-zero"))
        if isinstance(node.op, ast.Add) and isinstance(node.left, ast.Constant) and isinstance(node.right,
                                                                                               ast.Constant):
            left, right = node.left.value, node.right.value
            if isinstance(left, str) != isinstance(right, str) and not isinstance(left, bytes) \
                    and not isinstance(right, bytes):
                self.issues.append(_issue(node.lineno, Category.TYPE, Severity.ERROR,
                                          "Adding a string and a number raises TypeError.", symbol="str-num-add",
                                          suggestion="Convert with str() or int() first."))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"list", "dict", "str", "int", "set", "sum", "max",
                                                               "min", "len", "input", "id", "type", "filter",
                                                               "map", "sorted", "tuple", "float", "range"}:
                self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.WARNING,
                                          f"Assignment shadows the built-in '{target.id}'.",
                                          symbol="shadowed-builtin", suggestion="Choose a different name."))
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            has_exit = any(isinstance(n, (ast.Break, ast.Return, ast.Raise)) for n in ast.walk(node))
            if not has_exit:
                self.issues.append(_issue(node.lineno, Category.LOGIC, Severity.WARNING,
                                          "'while True' loop has no break/return/raise: possible infinite loop.",
                                          symbol="infinite-loop", confidence=Confidence.HEURISTIC))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            self.issues.append(_issue(node.lineno, Category.BAD_PRACTICE, Severity.WARNING,
                                      f"Use of {node.func.id}() can execute arbitrary code.",
                                      symbol="dangerous-call", suggestion="Use ast.literal_eval or explicit logic."))
        self.generic_visit(node)


def collect_structure(tree: ast.Module) -> tuple[list[FunctionInfo], list[str], list[str]]:
    """Return functions, class names and imported modules for display/prompting."""
    functions: list[FunctionInfo] = []
    classes: list[str] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(_function_info(item, is_method=True))
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or ".")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function_info(node))
    functions.sort(key=lambda f: f.lineno)
    return functions, classes, imports


def _function_info(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False) -> FunctionInfo:
    return FunctionInfo(name=node.name, lineno=node.lineno, end_lineno=getattr(node, "end_lineno", node.lineno),
                        args=[a.arg for a in node.args.args], has_docstring=ast.get_docstring(node) is not None,
                        is_method=is_method)


def analyze_syntax(code: str) -> SyntaxReport:
    """Run the complete AST analysis on ``code``.

    Returns a :class:`SyntaxReport`. If the code does not parse, the report is
    marked invalid and contains a single critical issue.
    """
    tree, fatal, compiler_warnings = check_syntax(code)
    if tree is None:
        assert fatal is not None
        return SyntaxReport(is_valid=False, issues=[fatal], error_message=fatal.message)

    visitor = _PatternVisitor()
    visitor.visit(tree)
    issues = compiler_warnings + find_scope_issues(code, tree) + visitor.issues
    functions, classes, imports = collect_structure(tree)
    issues.sort(key=lambda i: (i.line or 0, i.severity.rank))
    return SyntaxReport(is_valid=True, issues=issues, functions=functions, classes=classes, imports=imports)


def is_valid_python(code: str) -> bool:
    """Return True when ``code`` parses and compiles."""
    tree, _fatal, _warn = check_syntax(code)
    return tree is not None
