"""Central configuration for CodeMind AI.

Settings are read from environment variables (optionally loaded from a ``.env``
file) and can be overridden at runtime from the Streamlit *Settings* page.
No secrets are required: the project only talks to a local Ollama server.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

BASE_DIR: Path = Path(__file__).resolve().parent

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")  # always the project's .env, whatever the working directory
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass

DATA_DIR: Path = BASE_DIR / "data"
REPORTS_DIR: Path = BASE_DIR / "reports"
LOGS_DIR: Path = BASE_DIR / "logs"
DATASETS_DIR: Path = BASE_DIR / "datasets"
ASSETS_DIR: Path = BASE_DIR / "assets"
SANDBOX_DIR: Path = BASE_DIR / "sandbox"
EVAL_RESULTS_DIR: Path = BASE_DIR / "evaluation" / "results"

APP_NAME = "CodeMind AI"
APP_TAGLINE = "AI-Powered Python Code Debugger and Optimization System"
APP_VERSION = "1.0.0"


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable application settings. Use :meth:`with_overrides` to change."""

    # --- LLM / Ollama -----------------------------------------------------
    ollama_host: str = field(default_factory=lambda: _env_str("OLLAMA_HOST", "http://localhost:11434"))
    model_name: str = field(default_factory=lambda: _env_str("OLLAMA_MODEL", "qwen2.5-coder:1.5b"))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.1))
    request_timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 180))
    max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 2))
    context_length: int = field(default_factory=lambda: _env_int("LLM_CONTEXT_LENGTH", 8192))
    llm_enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", True))

    # --- Repair loop --------------------------------------------------------
    max_repair_attempts: int = field(default_factory=lambda: _env_int("MAX_REPAIR_ATTEMPTS", 3))

    # --- Sandbox -------------------------------------------------------------
    sandbox_enabled: bool = field(default_factory=lambda: _env_bool("SANDBOX_ENABLED", True))
    sandbox_image: str = field(default_factory=lambda: _env_str("SANDBOX_IMAGE", "codemind-sandbox:latest"))
    sandbox_timeout: int = field(default_factory=lambda: _env_int("SANDBOX_TIMEOUT", 20))
    sandbox_memory_mb: int = field(default_factory=lambda: _env_int("SANDBOX_MEMORY_MB", 256))
    sandbox_cpus: float = field(default_factory=lambda: _env_float("SANDBOX_CPUS", 0.5))
    sandbox_output_limit: int = field(default_factory=lambda: _env_int("SANDBOX_OUTPUT_LIMIT", 20000))

    # --- Storage -------------------------------------------------------------
    history_enabled: bool = field(default_factory=lambda: _env_bool("HISTORY_ENABLED", True))
    database_url: str = field(
        default_factory=lambda: _env_str("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'codemind.db').as_posix()}")
    )

    # --- Input limits --------------------------------------------------------
    max_code_chars: int = field(default_factory=lambda: _env_int("MAX_CODE_CHARS", 30000))
    max_code_lines: int = field(default_factory=lambda: _env_int("MAX_CODE_LINES", 800))
    static_analysis_timeout: int = field(default_factory=lambda: _env_int("STATIC_ANALYSIS_TIMEOUT", 60))

    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))

    def with_overrides(self, **overrides: Any) -> "Settings":
        """Return a copy with the given fields replaced (unknown keys ignored)."""
        names = {f.name for f in fields(self)}
        valid = {k: v for k, v in overrides.items() if k in names}
        return replace(self, **valid)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RECOMMENDED_MODELS: list[dict[str, str]] = [
    {"name": "qwen2.5-coder:1.5b", "size": "~1.0 GB", "ram": "8 GB", "note": "Fastest; good default for laptops"},
    {"name": "qwen2.5-coder:3b", "size": "~1.9 GB", "ram": "8 GB", "note": "Better reasoning, still CPU friendly"},
    {"name": "qwen2.5-coder:7b", "size": "~4.7 GB", "ram": "16 GB", "note": "Best quality; slow without a GPU"},
    {"name": "deepseek-coder:1.3b", "size": "~0.8 GB", "ram": "8 GB", "note": "Alternative small coding model"},
]


def get_settings() -> Settings:
    """Return settings built from the current environment."""
    for directory in (DATA_DIR, REPORTS_DIR, LOGS_DIR, EVAL_RESULTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    return Settings()
