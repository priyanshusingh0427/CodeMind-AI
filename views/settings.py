"""Settings page: LLM, sandbox, history and limits."""

from __future__ import annotations

import streamlit as st

from config import RECOMMENDED_MODELS, get_settings
from core.llm_engine import OllamaClient
from core.sandbox import DockerSandbox
from database.operations import delete_all_sessions
from views.components import clear_status_caches, current_settings, page_header, save_user_settings


def render() -> None:
    page_header("Settings", "Configure the local LLM, isolated validation and data storage.", "⚙️")
    settings = current_settings()
    overrides = dict(st.session_state.settings_overrides)

    st.subheader("AI engine (Ollama)")
    col1, col2 = st.columns(2)
    with col1:
        llm_enabled = st.toggle("Enable AI engine", value=settings.llm_enabled)
        host = st.text_input("Ollama host", value=settings.ollama_host)
        installed: list[str] = []
        try:
            installed = OllamaClient(host=host).list_models()
        except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
            installed = []
        choices = sorted(set(installed) | {m["name"] for m in RECOMMENDED_MODELS} | {settings.model_name})
        model = st.selectbox("Model", choices, index=choices.index(settings.model_name),
                             help="Models marked installed are available locally.",
                             format_func=lambda m: f"{m}  ✓ installed" if m in installed else m)
    with col2:
        temperature = st.slider("Temperature", 0.0, 1.0, float(settings.temperature), 0.05,
                                help="Low values give more deterministic corrections.")
        timeout = st.number_input("Request timeout (s)", 10, 900, int(settings.request_timeout), 10)
        retries = st.number_input("Max retries", 0, 5, int(settings.max_retries))
        context = st.select_slider("Context length (tokens)", [2048, 4096, 8192, 16384, 32768],
                                   value=settings.context_length if settings.context_length in
                                   [2048, 4096, 8192, 16384, 32768] else 8192)
    if st.button("Test connection", icon=":material/wifi_tethering:"):
        status = OllamaClient(host=host, model=model).check_status()
        (st.success if status.available else st.error)(status.message)
        if status.models:
            st.caption("Installed models: " + ", ".join(status.models))
    with st.expander("Recommended lightweight coding models"):
        st.dataframe(RECOMMENDED_MODELS, width="stretch", hide_index=True)
        st.code(f"ollama pull {model}", language="bash")

    st.subheader("Repair loop")
    attempts = st.slider("Maximum automated repair attempts", 1, 5, int(settings.max_repair_attempts))

    st.subheader("Isolated validation (Docker sandbox)")
    sandbox_enabled = st.toggle("Enable sandboxed test execution", value=settings.sandbox_enabled,
                                help="Without Docker, CodeMind AI never executes code and stays static-only.")
    c1, c2, c3 = st.columns(3)
    sb_timeout = c1.number_input("Execution timeout (s)", 2, 120, int(settings.sandbox_timeout))
    sb_memory = c2.number_input("Memory limit (MB)", 64, 2048, int(settings.sandbox_memory_mb), 64)
    sb_cpus = c3.number_input("CPU limit (cores)", 0.1, 4.0, float(settings.sandbox_cpus), 0.1)
    sandbox = DockerSandbox(settings)
    status = sandbox.status()
    (st.success if status.available else st.warning)(status.message)
    if status.daemon_running and not status.image_present:
        if st.button("Build sandbox image", icon=":material/build:"):
            with st.spinner("Building codemind-sandbox image (first build downloads python:3.11-slim)…"):
                ok, output = sandbox.build_image()
            (st.success if ok else st.error)("Image built." if ok else "Build failed.")
            st.code(output[-3000:] or "(no output)")
            clear_status_caches()
    with st.expander("Security controls applied to every run"):
        st.code(" ".join(sandbox.build_command("<temp-dir>", "codemind-<id>")), language="bash")

    st.subheader("Data and privacy")
    history_enabled = st.toggle("Store debugging history locally (SQLite)", value=settings.history_enabled)
    st.caption(f"Database: `{settings.database_url}` — all data stays on this computer.")

    if st.button("Save settings", type="primary", icon=":material/save:"):
        overrides.update({"llm_enabled": llm_enabled, "ollama_host": host.strip(), "model_name": model,
                          "temperature": float(temperature), "request_timeout": int(timeout),
                          "max_retries": int(retries), "context_length": int(context),
                          "max_repair_attempts": int(attempts), "sandbox_enabled": sandbox_enabled,
                          "sandbox_timeout": int(sb_timeout), "sandbox_memory_mb": int(sb_memory),
                          "sandbox_cpus": float(sb_cpus), "history_enabled": history_enabled})
        st.session_state.settings_overrides = overrides
        save_user_settings(overrides)
        clear_status_caches()
        st.success("Settings saved.")
        st.rerun()
    if st.button("Reset to defaults (.env)", icon=":material/settings_backup_restore:"):
        st.session_state.settings_overrides = {}
        save_user_settings({})
        clear_status_caches()
        st.rerun()

    with st.expander("Clear stored history"):
        if st.checkbox("Confirm deletion of all sessions"):
            if st.button("Delete all sessions", icon=":material/delete_forever:"):
                st.success(f"Deleted {delete_all_sessions(get_settings().with_overrides(**overrides).database_url)} "
                           "session(s).")
