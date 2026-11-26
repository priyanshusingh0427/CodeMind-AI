"""CodeMind AI – Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from config import APP_NAME, APP_TAGLINE, APP_VERSION
from utils.logger import configure_logging
from views import about, ai_assistant, analytics, dashboard, debugger, history, optimizer, settings, test_generator
from views.components import current_settings, init_state, llm_status, load_css, sandbox_status, status_pill

st.set_page_config(page_title=APP_NAME, page_icon="🧠", layout="wide", initial_sidebar_state="expanded")


def main() -> None:
    init_state()
    cfg = current_settings()
    configure_logging(cfg.log_level)
    load_css()

    pages = {
        "dashboard": st.Page(dashboard.render, title="Home Dashboard", icon=":material/space_dashboard:",
                             url_path="dashboard", default=True),
        "debugger": st.Page(debugger.render, title="AI Code Debugger", icon=":material/bug_report:",
                            url_path="debugger"),
        "optimizer": st.Page(optimizer.render, title="Code Optimizer", icon=":material/speed:", url_path="optimizer"),
        "tests": st.Page(test_generator.render, title="Test Case Generator", icon=":material/science:",
                         url_path="tests"),
        "assistant": st.Page(ai_assistant.render, title="AI Code Assistant", icon=":material/forum:",
                             url_path="assistant"),
        "analytics": st.Page(analytics.render, title="Analytics Dashboard", icon=":material/monitoring:",
                             url_path="analytics"),
        "history": st.Page(history.render, title="Debugging History", icon=":material/history:", url_path="history"),
        "settings": st.Page(settings.render, title="Settings", icon=":material/settings:", url_path="settings"),
        "about": st.Page(about.render, title="About Project", icon=":material/school:", url_path="about"),
    }
    st.session_state["_pages"] = pages

    navigation = st.navigation({
        "Workspace": [pages["dashboard"], pages["debugger"], pages["optimizer"], pages["tests"], pages["assistant"]],
        "Insights": [pages["analytics"], pages["history"]],
        "System": [pages["settings"], pages["about"]],
    })

    with st.sidebar:
        st.markdown(f"### 🧠 {APP_NAME}")
        st.caption(f"{APP_TAGLINE} · v{APP_VERSION}")
        llm = llm_status(cfg)
        sandbox = sandbox_status(cfg)
        st.markdown(
            status_pill(llm.available, f"LLM: {cfg.model_name}" if llm.available else "LLM offline")
            + status_pill(sandbox.available, "Sandbox ready" if sandbox.available else "Static-only mode")
            + status_pill(cfg.history_enabled, "History on" if cfg.history_enabled else "History off"),
            unsafe_allow_html=True)

    navigation.run()


main()
