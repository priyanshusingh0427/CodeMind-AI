"""Structured (JSON-lines) logging for CodeMind AI."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from config import LOGS_DIR

_CONFIGURED = False
_STANDARD_ATTRS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once: JSON file log plus concise console log."""
    global _CONFIGURED  # pylint: disable=global-statement
    if _CONFIGURED:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("codemind")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False

    file_handler = RotatingFileHandler(LOGS_DIR / "codemind.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    console.setLevel(logging.WARNING)
    root.addHandler(console)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the ``codemind`` namespace."""
    configure_logging()
    return logging.getLogger(f"codemind.{name}")
