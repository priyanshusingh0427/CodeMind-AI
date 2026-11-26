"""Small, dependency-free helper functions shared across modules."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator


def new_session_id() -> str:
    """Return a short unique identifier for a debugging session."""
    return uuid.uuid4().hex[:12]


def now_str() -> str:
    """Current local time formatted for display."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def code_hash(code: str) -> str:
    """Stable SHA-256 hash of source code (used for de-duplication)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def truncate(text: str, limit: int, marker: str = "\n... [truncated]") -> str:
    """Truncate ``text`` to ``limit`` characters, appending a marker if cut."""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - len(marker))] + marker


def normalize_code(code: str) -> str:
    """Normalise line endings and tabs-at-EOF; keep content otherwise intact."""
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    if code and not code.endswith("\n"):
        code += "\n"
    return code


def strip_code_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence (```python ... ```) if present."""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL)
    return match.group(1) if match else text


def count_loc(code: str) -> int:
    """Count non-blank, non-comment lines."""
    return sum(1 for line in code.splitlines() if line.strip() and not line.strip().startswith("#"))


@contextmanager
def timer() -> Iterator[dict[str, float]]:
    """Context manager that records elapsed seconds in ``result['elapsed']``."""
    result: dict[str, float] = {"elapsed": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed"] = time.perf_counter() - start


def safe_filename(name: str, default: str = "code") -> str:
    """Return a filesystem-safe version of ``name``."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return cleaned or default
