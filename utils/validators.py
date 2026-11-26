"""Pydantic schemas and input validation.

All data that crosses a module boundary (analysis issues, LLM responses, test
cases) is described here so that malformed data is rejected early and every
component speaks the same language.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


class Severity(str, Enum):
    """Issue severity, ordered from most to least serious."""

    CRITICAL = "critical"  # code cannot run at all (syntax / indentation)
    ERROR = "error"  # will very likely fail at runtime (undefined name, ...)
    WARNING = "warning"  # suspicious, may be a bug
    INFO = "info"  # style / convention / refactoring

    @property
    def rank(self) -> int:
        return {"critical": 0, "error": 1, "warning": 2, "info": 3}[self.value]


class Confidence(str, Enum):
    """Whether a finding is confirmed by a deterministic tool or inferred by AI."""

    CONFIRMED = "confirmed"
    AI_INFERRED = "ai_inferred"
    HEURISTIC = "heuristic"


class Category(str, Enum):
    SYNTAX = "syntax_error"
    INDENTATION = "indentation_error"
    UNDEFINED_NAME = "undefined_variable"
    TYPE = "type_issue"
    MISSING_IMPORT = "missing_import"
    LOGIC = "logical_error"
    RUNTIME = "potential_runtime_error"
    UNREACHABLE = "unreachable_code"
    UNUSED = "unused_variable"
    BAD_PRACTICE = "bad_practice"
    STYLE = "style"
    COMPLEXITY = "complexity"
    OTHER = "other"


class Issue(BaseModel):
    """A single detected problem in the submitted code."""

    line: Optional[int] = Field(default=None, ge=0)
    column: Optional[int] = Field(default=None, ge=0)
    category: Category = Category.OTHER
    severity: Severity = Severity.WARNING
    message: str
    symbol: str = ""
    source: str = "ast"  # ast | pylint | radon | llm
    confidence: Confidence = Confidence.CONFIRMED
    suggestion: str = ""

    def key(self) -> tuple[Optional[int], str]:
        """De-duplication key: same line + same category means same issue."""
        return (self.line, self.category.value)


# --------------------------------------------------------------------------
# LLM response schemas
# --------------------------------------------------------------------------


def _coerce_severity(value: Any) -> str:
    text = str(value or "warning").strip().lower()
    aliases = {"high": "error", "medium": "warning", "low": "info", "fatal": "critical", "major": "error",
               "minor": "info", "convention": "info", "refactor": "info"}
    text = aliases.get(text, text)
    return text if text in {s.value for s in Severity} else "warning"


def to_str_list(value: Any) -> list[str]:
    """Coerce a model-provided value (None, str, list of str/dict) into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) if not isinstance(v, dict) else "; ".join(f"{k}: {x}" for k, x in v.items()) for v in value]
    return [str(value)]


class AIFinding(BaseModel):
    """One bug reported by the LLM (always treated as AI-inferred)."""

    error_type: str = "unknown"
    line_number: Optional[int] = None
    severity: Severity = Severity.WARNING
    description: str = ""
    suggested_correction: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, value: Any) -> str:
        return _coerce_severity(value)

    @field_validator("line_number", mode="before")
    @classmethod
    def _line(cls, value: Any) -> Optional[int]:
        try:
            number = int(value)
            return number if number >= 0 else None
        except (TypeError, ValueError):
            return None


class AIDebugResponse(BaseModel):
    """Structured response expected from the LLM for a debugging request."""

    findings: list[AIFinding] = Field(default_factory=list)
    corrected_code: str = ""
    optimization_suggestions: list[str] = Field(default_factory=list)
    explanation: str = ""
    changes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validation_status: str = "unverified"
    no_bugs_found: bool = False

    @field_validator("optimization_suggestions", "changes", "assumptions", mode="before")
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        return to_str_list(value)


class AIOptimizationResponse(BaseModel):
    """Structured response for optimisation suggestions."""

    suggestions: list[str] = Field(default_factory=list)
    estimated_time_complexity: str = "unknown"
    estimated_space_complexity: str = "unknown"
    optimized_code: str = ""
    explanation: str = ""

    @field_validator("suggestions", mode="before")
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        return to_str_list(value)


class TestCaseSpec(BaseModel):
    """A single test case in a language-neutral, reviewable form."""

    __test__ = False  # not a pytest test class

    name: str = "test_case"
    category: str = "normal"  # normal | edge | boundary | invalid
    call: str  # Python expression, e.g. "add(2, 3)"
    expected: str = ""  # Python literal/expression for the expected result
    expects_exception: str = ""  # Exception class name if an error is expected
    description: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: Any) -> str:
        text = str(value or "normal").strip().lower()
        return text if text in {"normal", "edge", "boundary", "invalid"} else "normal"

    @field_validator("expected", "expects_exception", "description", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> str:
        return "" if value is None else str(value)


class AITestResponse(BaseModel):
    tests: list[TestCaseSpec] = Field(default_factory=list)


class InputValidationError(ValueError):
    """Raised when user-submitted code fails basic validation."""


def validate_code_input(code: str, max_chars: int, max_lines: int) -> str:
    """Validate submitted source code and return it unchanged.

    Raises:
        InputValidationError: for empty, oversized or binary input.
    """
    if code is None or not code.strip():
        raise InputValidationError("Please provide some Python code to analyse.")
    if "\x00" in code:
        raise InputValidationError("The input looks like a binary file, not Python source.")
    if len(code) > max_chars:
        raise InputValidationError(f"Code is too long ({len(code)} characters, limit {max_chars}).")
    line_count = code.count("\n") + 1
    if line_count > max_lines:
        raise InputValidationError(f"Code has too many lines ({line_count}, limit {max_lines}).")
    return code


def decode_uploaded_file(raw: bytes, max_chars: int) -> str:
    """Decode an uploaded ``.py`` file as UTF-8 (with BOM handling)."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputValidationError("Uploaded file is not valid UTF-8 text.") from exc
    if len(text) > max_chars:
        raise InputValidationError(f"Uploaded file is too large ({len(text)} characters, limit {max_chars}).")
    return text


__all__ = [
    "AIDebugResponse", "AIFinding", "AIOptimizationResponse", "AITestResponse", "Category", "Confidence",
    "InputValidationError", "Issue", "Severity", "TestCaseSpec", "ValidationError", "decode_uploaded_file",
    "validate_code_input",
]
