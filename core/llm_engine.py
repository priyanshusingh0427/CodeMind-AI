"""Ollama LLM integration.

Talks to a local Ollama server over its HTTP API (``/api/tags``, ``/api/chat``).
Features: connection checking, configurable model/temperature/context length,
request timeouts, limited retries, JSON-mode generation with Pydantic
validation and tolerant parsing of malformed model output.

No API keys are used. If Ollama is not running, callers receive an
:class:`LLMUnavailableError` and the application falls back to static analysis.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from config import Settings
from utils.logger import get_logger

logger = get_logger("llm_engine")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Base error for LLM problems."""


class LLMUnavailableError(LLMError):
    """Ollama is not reachable or the model is not installed."""


class LLMResponseError(LLMError):
    """The model answered, but the answer could not be parsed/validated."""


@dataclass
class LLMStatus:
    available: bool
    message: str
    models: list[str]
    model_installed: bool = False


class LLMClient(Protocol):
    """Interface shared by the real Ollama client and test doubles."""

    model: str

    def check_status(self) -> LLMStatus: ...

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str: ...

    def generate_json(self, prompt: str, schema: type[T], system: str = "") -> T: ...


# ---------------------------------------------------------------------------
# Tolerant JSON extraction
# ---------------------------------------------------------------------------


def _balanced_object(text: str) -> Optional[str]:
    """Return the first balanced {...} substring, respecting JSON strings."""
    start = text.find("{")
    while start != -1:
        depth, in_string, escape = 0, False, False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        start = text.find("{", start + 1)
    return None


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model reply.

    Handles Markdown fences, leading/trailing prose, and trailing commas.

    Raises:
        LLMResponseError: when no JSON object can be recovered.
    """
    if not text or not text.strip():
        raise LLMResponseError("Empty response from model.")
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    balanced = _balanced_object(text)
    if balanced:
        candidates.append(balanced)
    for candidate in candidates:
        for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    raise LLMResponseError("Model response did not contain a valid JSON object.")


def parse_structured(text: str, schema: type[T]) -> T:
    """Parse ``text`` into ``schema``, raising :class:`LLMResponseError` on failure."""
    data = extract_json(text)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMResponseError(f"Model JSON did not match the expected schema: {exc.error_count()} error(s).") \
            from exc


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------


class OllamaClient:
    """Minimal, dependency-light client for the Ollama HTTP API."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5-coder:1.5b",
                 temperature: float = 0.1, timeout: int = 180, max_retries: int = 2, context_length: int = 8192,
                 session: Optional[requests.Session] = None) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = max(0.0, min(2.0, temperature))
        self.timeout = max(5, timeout)
        self.max_retries = max(0, min(5, max_retries))
        self.context_length = max(1024, context_length)
        self.session = session or requests.Session()

    @classmethod
    def from_settings(cls, settings: Settings) -> "OllamaClient":
        return cls(host=settings.ollama_host, model=settings.model_name, temperature=settings.temperature,
                   timeout=settings.request_timeout, max_retries=settings.max_retries,
                   context_length=settings.context_length)

    # -- health -------------------------------------------------------------
    def list_models(self) -> list[str]:
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            response.raise_for_status()
            return [m.get("name", "") for m in response.json().get("models", []) if m.get("name")]
        except (requests.RequestException, ValueError) as exc:
            raise LLMUnavailableError(f"Cannot reach Ollama at {self.host}: {exc.__class__.__name__}") from exc

    def check_status(self) -> LLMStatus:
        """Check that Ollama is running and that the configured model is pulled."""
        try:
            models = self.list_models()
        except LLMUnavailableError as exc:
            return LLMStatus(False, f"{exc}. Start it with `ollama serve`.", [])
        installed = any(m == self.model or m.split(":")[0] == self.model or m == f"{self.model}:latest"
                        for m in models)
        if not installed:
            return LLMStatus(False, f"Ollama is running but model '{self.model}' is not installed. "
                                    f"Run `ollama pull {self.model}`.", models, False)
        return LLMStatus(True, f"Connected to Ollama ({self.model}).", models, True)

    # -- generation ---------------------------------------------------------
    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        """Send a chat request and return the assistant's text.

        Retries transient network errors up to ``max_retries`` times with
        exponential backoff.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.context_length},
        }
        if json_mode:
            payload["format"] = "json"
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                started = time.perf_counter()
                response = self.session.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
                if response.status_code == 404:
                    raise LLMUnavailableError(f"Model '{self.model}' not found. Run `ollama pull {self.model}`.")
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "")
                logger.info("llm chat completed", extra={"model": self.model, "attempt": attempt,
                                                         "seconds": round(time.perf_counter() - started, 2),
                                                         "chars": len(content)})
                return content
            except requests.ConnectionError as exc:
                last_error = exc
                if attempt == self.max_retries:
                    raise LLMUnavailableError(f"Cannot reach Ollama at {self.host}.") from exc
            except (requests.Timeout, requests.HTTPError, ValueError) as exc:
                last_error = exc
            logger.warning("llm request failed, retrying", extra={"attempt": attempt, "error": repr(last_error)})
            if attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 8))
        raise LLMError(f"LLM request failed after {self.max_retries + 1} attempt(s): {last_error!r}")

    def generate_json(self, prompt: str, schema: type[T], system: str = "") -> T:
        """Generate a JSON response validated against ``schema``.

        If the first reply is malformed, the model is asked (a limited number of
        times) to resend valid JSON only.
        """
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user",
                                                                                   "content": prompt}]
        last_error: Optional[LLMResponseError] = None
        for attempt in range(self.max_retries + 1):
            raw = self.chat(messages, json_mode=True)
            try:
                return parse_structured(raw, schema)
            except LLMResponseError as exc:
                last_error = exc
                logger.warning("malformed llm json", extra={"attempt": attempt, "error": str(exc)})
                messages = messages + [
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": "That was not valid JSON for the requested schema. "
                                                "Reply again with ONLY the JSON object."},
                ]
        raise last_error or LLMResponseError("Unknown parsing failure.")


def get_llm_client(settings: Settings) -> Optional[OllamaClient]:
    """Return an Ollama client if the LLM is enabled in settings, else None."""
    return OllamaClient.from_settings(settings) if settings.llm_enabled else None
