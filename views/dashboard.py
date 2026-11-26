"""Home Dashboard page."""

from __future__ import annotations

import streamlit as st

from config import APP_NAME, APP_TAGLINE
from database.operations import get_statistics, list_sessions
from views.components import current_settings, llm_status, metric_card, metric_row, sandbox_status

PIPELINE = ["Code input", "AST syntax analysis", "Pylint static analysis", "Radon complexity", "Structured prompt",
            "Ollama coding LLM", "AI correction (JSON)", "Syntax revalidation", "Sandboxed tests",
            "Verification & repair loop", "Diff", "SQLite history", "Dashboard & reports"]


def render() -> None:
    settings = current_settings()
    st.markdown(f"""<div class="cm-hero"><h1>🧠 <span class="cm-gradient-text">{APP_NAME}</span></h1>
<p>{APP_TAGLINE}. Hybrid static analysis + local LLM + independent test validation, running fully offline.</p>
</div>""", unsafe_allow_html=True)

    llm = llm_status(settings)
    sandbox = sandbox_status(settings)
    try:
        stats = get_statistics(settings.database_url)
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        stats = {"total_sessions": 0, "avg_quality_before": 0, "avg_quality_after": 0, "avg_duration": 0,
                 "total_issues": 0, "status_counts": {}}
    verified = stats["status_counts"].get("verified", 0)
    metric_row([
        metric_card("AI engine", "Online" if llm.available else "Offline", settings.model_name,
                    "green" if llm.available else "red"),
        metric_card("Sandbox", "Ready" if sandbox.available else "Off", "Docker isolation" if sandbox.available
                    else "static-analysis-only", "green" if sandbox.available else "yellow"),
        metric_card("Sessions analysed", stats["total_sessions"], "stored locally", "purple"),
        metric_card("Issues detected", stats["total_issues"], "all sessions", "blue"),
        metric_card("Verified repairs", verified, "passed provided tests", "green"),
        metric_card("Avg. analysis time", f"{stats['avg_duration']:.1f}s", "per session", "default"),
    ])
    if not llm.available:
        st.info(f"**AI engine offline:** {llm.message} The debugger still works in static-analysis mode.",
                icon=":material/smart_toy:")
    if not sandbox.available:
        st.caption(f"Sandbox: {sandbox.message}")

    pages = st.session_state.get("_pages", {})
    st.markdown('<div class="cm-section-title">Quick start</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    links = [("debugger", "Debug code", ":material/bug_report:"), ("optimizer", "Optimise code", ":material/speed:"),
             ("tests", "Generate tests", ":material/science:"), ("assistant", "Ask the assistant", ":material/forum:")]
    for col, (key, label, icon) in zip(cols, links):
        with col, st.container(border=True):
            if key in pages:
                st.page_link(pages[key], label=label, icon=icon)

    st.markdown('<div class="cm-section-title">How it works</div>', unsafe_allow_html=True)
    steps = '<span class="cm-arrow">→</span>'.join(f'<span class="cm-step">{s}</span>' for s in PIPELINE)
    st.markdown(steps, unsafe_allow_html=True)

    st.markdown('<div class="cm-section-title">Recent sessions</div>', unsafe_allow_html=True)
    if not settings.history_enabled:
        st.caption("History storage is disabled in Settings.")
        return
    try:
        recent = list_sessions(settings.database_url, limit=5)
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        recent = []
    if not recent:
        st.caption("No sessions yet. Analyse some code to see it here.")
        return
    st.dataframe([{"date": r["created_at"].strftime("%Y-%m-%d %H:%M"), "title": r["title"],
                   "issues": r["total_issues"], "quality": r["quality_before"],
                   "after": r["quality_after"], "status": r["repair_status"]} for r in recent],
                 width="stretch", hide_index=True)
