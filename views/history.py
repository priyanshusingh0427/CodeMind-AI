"""Debugging History page: search, filter, view, reload and delete sessions."""

from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from core.ai_debugger import REPAIR_STATUS_LABELS
from core.code_comparator import compare_code, render_side_by_side_html
from database.operations import delete_all_sessions, delete_session, get_session, list_sessions
from utils.report_generator import generate_json_report, generate_pdf_report
from views.components import current_settings, page_header, set_code


def _as_report_payload(record: dict) -> dict:
    return {"session_id": record["session_id"], "mode": record["mode"], "model_name": record["model_name"],
            "original_code": record["original_code"], "corrected_code": record["corrected_code"],
            "expected_behavior": record["expected_behavior"], "static_issues": record["issues"] or [],
            "ai_issues": record["ai_issues"] or [], "metrics_before": record["metrics_before"],
            "metrics_after": record["metrics_after"], "quality_before": record["quality_before"],
            "quality_after": record["quality_after"], "explanation": record["explanation"],
            "changes": record["changes"] or [], "test_report": record["test_results"],
            "repair_status": record["repair_status"], "attempts": record["attempts"],
            "duration": record["duration"], "notes": []}


def _detail(record: dict) -> None:
    st.markdown(f"#### {record['title']}")
    st.caption(f"Session `{record['session_id']}` · {record['created_at']:%Y-%m-%d %H:%M} · mode `{record['mode']}` · "
               f"model `{record['model_name'] or 'n/a'}` · {record['duration']:.1f}s")
    st.markdown(f"**Status:** {REPAIR_STATUS_LABELS.get(record['repair_status'], record['repair_status'])} · "
                f"**Quality:** {record['quality_before']} → {record['quality_after'] if record['quality_after'] is not None else '–'}")
    issues = (record["issues"] or []) + (record["ai_issues"] or [])
    if issues:
        st.dataframe([{"line": i.get("line"), "severity": i.get("severity"), "category": i.get("category"),
                       "confidence": i.get("confidence"), "source": i.get("source"), "message": i.get("message")}
                      for i in issues], width="stretch", hide_index=True)
    if record["corrected_code"] and record["corrected_code"] != record["original_code"]:
        st.markdown(render_side_by_side_html(compare_code(record["original_code"], record["corrected_code"])),
                    unsafe_allow_html=True)
    else:
        st.code(record["original_code"], language="python", line_numbers=True)
    if record["explanation"]:
        with st.expander("AI explanation"):
            st.markdown(record["explanation"])
    if record["test_results"]:
        with st.expander("Test results"):
            st.json(record["test_results"])
    payload = _as_report_payload(record)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Load into editor", icon=":material/edit:", width="stretch"):
            set_code(record["original_code"], record["expected_behavior"])
            st.success("Loaded. Open the AI Code Debugger page.")
    with col2:
        st.download_button("JSON report", generate_json_report(payload), file_name=f"report_{record['session_id']}.json",
                           mime="application/json", width="stretch")
    with col3:
        st.download_button("PDF report", generate_pdf_report(payload), file_name=f"report_{record['session_id']}.pdf",
                           mime="application/pdf", width="stretch")
    with col4:
        if st.button("Delete session", icon=":material/delete:", width="stretch"):
            delete_session(current_settings().database_url, record["session_id"])
            st.session_state.pop("history_selected", None)
            st.rerun()


def render() -> None:
    page_header("Debugging History", "Every analysis is stored locally in SQLite (can be disabled in Settings).", "🕘")
    settings = current_settings()
    if not settings.history_enabled:
        st.warning("History storage is currently **disabled**. New sessions are not saved. "
                   "Existing records are still shown below.", icon=":material/history_toggle_off:")

    col1, col2, col3, col4 = st.columns([3, 2, 1.5, 1.5])
    search = col1.text_input("Search", placeholder="function name, code, explanation or session id")
    statuses = ["All"] + list(REPAIR_STATUS_LABELS)
    status = col2.selectbox("Repair status", statuses)
    date_from = col3.date_input("From", value=None)
    date_to = col4.date_input("To", value=None)

    rows = list_sessions(settings.database_url, search=search, status=None if status == "All" else status,
                         date_from=datetime.combine(date_from, time.min) if date_from else None,
                         date_to=datetime.combine(date_to, time.max) if date_to else None)
    st.caption(f"{len(rows)} session(s)")
    if not rows:
        st.info("No sessions match.")
    else:
        table = [{"session_id": r["session_id"], "date": r["created_at"].strftime("%Y-%m-%d %H:%M"),
                  "title": r["title"], "issues": r["total_issues"], "critical/errors": r["critical_issues"],
                  "quality": r["quality_before"], "after": r["quality_after"], "status": r["repair_status"],
                  "model": r["model_name"], "seconds": round(r["duration"], 2)} for r in rows]
        event = st.dataframe(table, width="stretch", hide_index=True, on_select="rerun",
                             selection_mode="single-row", key="history_table")
        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            st.session_state.history_selected = table[selected_rows[0]]["session_id"]
        selected = st.session_state.get("history_selected")
        if selected:
            record = get_session(settings.database_url, selected)
            if record:
                with st.container(border=True):
                    _detail(record)
        else:
            st.caption("Select a row to view details.")

    with st.expander("Danger zone"):
        confirm = st.checkbox("I understand this permanently deletes all stored sessions.")
        if st.button("Delete all history", disabled=not confirm, type="primary", icon=":material/delete_forever:"):
            removed = delete_all_sessions(settings.database_url)
            st.session_state.pop("history_selected", None)
            st.success(f"Deleted {removed} session(s).")
            st.rerun()
