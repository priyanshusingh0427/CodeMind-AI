"""Reusable Streamlit UI components and shared session services."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from config import ASSETS_DIR, DATA_DIR, DATASETS_DIR, Settings, get_settings
from core.llm_engine import LLMStatus, OllamaClient
from core.sandbox import DockerSandbox, SandboxStatus
from core.test_validator import TestValidator
from utils.validators import Issue, Severity

try:
    from streamlit_ace import st_ace

    ACE_AVAILABLE = True
except ImportError:  # pragma: no cover - optional component
    ACE_AVAILABLE = False

USER_SETTINGS_FILE: Path = DATA_DIR / "user_settings.json"

SEVERITY_COLORS = {"critical": "#FF5C7A", "error": "#FF8A4C", "warning": "#F5C451", "info": "#5EA8FF"}
SEVERITY_ICONS = {"critical": ":material/dangerous:", "error": ":material/error:", "warning": ":material/warning:",
                  "info": ":material/info:"}

DEFAULT_STATE: dict[str, Any] = {
    "code": "",
    "expected_behavior": "",
    "editor_version": 0,
    "debug_result": None,
    "opt_report": None,
    "test_specs": [],
    "spec_version": 0,
    "test_code": "",
    "test_report": None,
    "chat_messages": [],
}


# ---------------------------------------------------------------------------
# State and settings
# ---------------------------------------------------------------------------


def init_state() -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value
    if "settings_overrides" not in st.session_state:
        st.session_state.settings_overrides = load_user_settings()


def load_user_settings() -> dict[str, Any]:
    try:
        return json.loads(USER_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_settings(overrides: dict[str, Any]) -> None:
    USER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_SETTINGS_FILE.write_text(json.dumps(overrides, indent=2), encoding="utf-8")


def current_settings() -> Settings:
    return get_settings().with_overrides(**st.session_state.get("settings_overrides", {}))


@st.cache_data(ttl=20, show_spinner=False)
def _cached_llm_status(host: str, model: str) -> LLMStatus:
    return OllamaClient(host=host, model=model).check_status()


@st.cache_data(ttl=30, show_spinner=False)
def _cached_sandbox_status(settings_json: str) -> SandboxStatus:
    return DockerSandbox(get_settings().with_overrides(**json.loads(settings_json))).status()


def llm_status(settings: Settings) -> LLMStatus:
    if not settings.llm_enabled:
        return LLMStatus(False, "AI engine disabled in Settings.", [])
    return _cached_llm_status(settings.ollama_host, settings.model_name)


def sandbox_status(settings: Settings) -> SandboxStatus:
    return _cached_sandbox_status(json.dumps(settings.to_dict(), sort_keys=True, default=str))


def get_llm(settings: Settings) -> Optional[OllamaClient]:
    """Return an Ollama client only when the model is reachable."""
    return OllamaClient.from_settings(settings) if llm_status(settings).available else None


def get_validator(settings: Settings) -> Optional[TestValidator]:
    return TestValidator(DockerSandbox(settings)) if sandbox_status(settings).available else None


def clear_status_caches() -> None:
    _cached_llm_status.clear()
    _cached_sandbox_status.clear()


# ---------------------------------------------------------------------------
# Visual components
# ---------------------------------------------------------------------------


def load_css() -> None:
    css_path = ASSETS_DIR / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str, icon: str = "") -> None:
    st.markdown(
        f'<div class="cm-header"><div class="cm-header-icon">{icon}</div><div><h1>{html.escape(title)}</h1>'
        f'<p>{html.escape(subtitle)}</p></div></div>', unsafe_allow_html=True)


def metric_card(label: str, value: Any, hint: str = "", tone: str = "default") -> str:
    """Return HTML for a metric card (render several with :func:`metric_row`)."""
    return (f'<div class="cm-card cm-tone-{tone}"><div class="cm-card-label">{html.escape(label)}</div>'
            f'<div class="cm-card-value">{html.escape(str(value))}</div>'
            f'<div class="cm-card-hint">{html.escape(hint)}</div></div>')


def metric_row(cards: list[str]) -> None:
    st.markdown(f'<div class="cm-card-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def badge(text: str, tone: str) -> str:
    return f'<span class="cm-badge cm-badge-{tone}">{html.escape(text)}</span>'


def status_pill(ok: bool, label: str) -> str:
    tone = "ok" if ok else "off"
    return f'<span class="cm-pill cm-pill-{tone}">● {html.escape(label)}</span>'


def render_issue_table(issues: list[Issue], empty_text: str = "No issues found.") -> None:
    """Render issues as styled rows with severity, confidence and suggestion."""
    if not issues:
        st.success(empty_text, icon=":material/check_circle:")
        return
    rows = []
    for issue in sorted(issues, key=lambda i: (i.severity.rank, i.line or 0)):
        sev = issue.severity.value
        confidence = {"confirmed": ("Confirmed", "ok"), "ai_inferred": ("AI-inferred", "ai"),
                      "heuristic": ("Heuristic", "warn")}[issue.confidence.value]
        suggestion = (f'<div class="cm-issue-fix">💡 {html.escape(issue.suggestion)}</div>'
                      if issue.suggestion else "")
        rows.append(
            f'<div class="cm-issue cm-sev-{sev}"><div class="cm-issue-top">'
            f'<span class="cm-line">L{issue.line if issue.line else "–"}</span>'
            f'{badge(sev.upper(), sev)}{badge(issue.category.value.replace("_", " "), "cat")}'
            f'{badge(confidence[0], confidence[1])}<span class="cm-src">{html.escape(issue.source)}</span></div>'
            f'<div class="cm-issue-msg">{html.escape(issue.message)}</div>{suggestion}</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


def severity_counts(issues: list[Issue]) -> dict[str, int]:
    counts = {s.value: 0 for s in Severity}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts


def ace_annotations(issues: list[Issue]) -> list[dict[str, Any]]:
    kind = {"critical": "error", "error": "error", "warning": "warning", "info": "info"}
    return [{"row": max(0, (i.line or 1) - 1), "column": 0, "type": kind[i.severity.value],
             "text": f"{i.category.value}: {i.message}"} for i in issues if i.line]


def code_editor(key_prefix: str = "main", height: int = 380, issues: Optional[list[Issue]] = None) -> str:
    """Syntax-highlighted editor bound to ``st.session_state.code``."""
    key = f"{key_prefix}_editor_{st.session_state.editor_version}"
    if ACE_AVAILABLE:
        value = st_ace(value=st.session_state.code, language="python", theme="tomorrow_night", keybinding="vscode",
                       font_size=14, tab_size=4, show_gutter=True, wrap=False, auto_update=True, min_lines=16,
                       height=height, annotations=ace_annotations(issues or []),
                       placeholder="# Paste or type your Python code here...", key=key)
        value = value if value is not None else st.session_state.code
    else:  # plain fallback
        value = st.text_area("Python code", value=st.session_state.code, height=height, key=key,
                             label_visibility="collapsed")
    st.session_state.code = value
    return value


def set_code(code: str, expected: Optional[str] = None) -> None:
    """Replace the editor content (forces the editor widget to refresh)."""
    st.session_state.code = code
    if expected is not None:
        st.session_state.expected_behavior = expected
    st.session_state.editor_version += 1
    st.session_state.debug_result = None
    st.session_state.opt_report = None


@st.cache_data(show_spinner=False)
def load_samples() -> list[dict[str, Any]]:
    try:
        data = json.loads((DATASETS_DIR / "sample_bugs.json").read_text(encoding="utf-8"))
        return data.get("samples", [])
    except (OSError, json.JSONDecodeError):
        return []


def require_code(message: str = "Add some code in the AI Code Debugger page first.") -> bool:
    if not st.session_state.get("code", "").strip():
        st.info(message, icon=":material/code:")
        page = st.session_state.get("_pages", {}).get("debugger")
        if page is not None:
            st.page_link(page, label="Open AI Code Debugger", icon=":material/bug_report:")
        return False
    return True


def plotly_layout(fig: Any, height: int = 320) -> Any:
    """Apply the dark dashboard theme to a Plotly figure."""
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=10, r=10, t=40, b=10),
                      font=dict(family="Inter, Segoe UI, sans-serif", color="#C9CEE3"),
                      colorway=["#7C6CFF", "#4C8DFF", "#2EC4B6", "#F5C451", "#FF8A4C", "#FF5C7A"])
    return fig
