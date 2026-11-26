"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings  # noqa: E402
from core.llm_engine import LLMResponseError, parse_structured  # noqa: E402


class ScriptedLLM:
    """Test double that returns pre-scripted raw replies (no network, no model)."""

    model = "scripted-test-model"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def check_status(self):  # pragma: no cover - not used
        raise NotImplementedError

    def chat(self, messages, json_mode=False) -> str:
        self.prompts.append(messages[-1]["content"])
        return self.replies.pop(0)

    def generate_json(self, prompt, schema, system=""):
        self.prompts.append(prompt)
        if not self.replies:
            raise LLMResponseError("no scripted replies left")
        return parse_structured(self.replies.pop(0), schema)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings().with_overrides(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
                                     max_repair_attempts=3, sandbox_enabled=False, history_enabled=True)


@pytest.fixture
def scripted_llm():
    return ScriptedLLM
