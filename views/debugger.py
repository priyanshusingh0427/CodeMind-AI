"""AI Code Debugger page: editor, analysis pipeline and results."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core.ai_debugger import REPAIR_STATUS_LABELS, AIDebugger, DebugResult
from core.code_comparator import compare_code, render_side_by_side_html
from core.complexity_analyzer import quality_grade
from database.operations import save_session
from utils.helpers import safe_filename
from utils.logger import get_logger
from utils.report_generator import generate_json_report, generate_pdf_report
from utils.validators import Confidence, InputValidationError, decode_uploaded_file
from views.components import (code_editor, current_settings, get_llm, get_validator, load_samples, metric_card,
                              metric_row, page_header, plotly_layout, render_issue_table, set_code, severity_counts)

logger = get_logger("ui.debugger")

MODE_LABELS = {
    "hybrid": "Hybrid (static + AI + verification) — recommended",
    "static": "Static analysis only",
    "llm_only": "AI only (no static context, no verification)",
}


def _input_panel() -> None:
    settings = current_settings()
    samples = load_samples()
    top = st.columns([2, 2, 1])
    with top[0]:
        uploaded = st.file_uploader("Upload a .py file", type=["py"], key=f"upload_{st.session_state.editor_version}")
        if uploaded is not None:
            try:
                set_code(decode_uploaded_file(uploaded.getvalue(), settings.max_code_chars))
                st.rerun()
            except InputValidationError as exc:
                st.error(str(exc))
    with top[1]:
        options = ["— choose a sample buggy program —"] + [f"{s['id']} · {s['title']}" for s in samples]
        choice = st.selectbox("Load sample", options, key=f"sample_{st.session_state.editor_version}")
        if choice != options[0]:
            sample = samples[options.index(choice) - 1]
            set_code(sample["code"], sample.get("expected_behavior", ""))
            st.rerun()
    with top[2]:
        st.write("")
        st.write("")
        if st.button("Clear / reset", icon=":material/restart_alt:", width="stretch"):
            set_code("", "")
            st.session_state.test_code = ""
            st.rerun()

    result: DebugResult | None = st.session_state.debug_result
    code_editor("debugger", issues=result.all_issues if result else None)
    st.session_state.expected_behavior = st.text_area(
        "Intended behaviour (optional, improves logical-error detection)", value=st.session_state.expected_behavior,
        placeholder="e.g. Return the sum of integers from 1 to n inclusive.", height=80)


def _run_analysis(mode: str, use_tests: bool) -> None:
    settings = current_settings()
    llm = get_llm(settings) if mode != "static" else None
    validator = get_validator(settings) if use_tests else None
    debugger = AIDebugger(settings, llm=llm, validator=validator)
    with st.status("Analysing code…", expanded=True) as status:
        st.write("Parsing AST, running Pylint and Radon…")
        if llm is not None:
            st.write(f"Asking {settings.model_name} for a correction (this can take a minute on CPU)…")
        if validator is not None:
            st.write("Validating the correction in the isolated sandbox…")
        try:
            result = debugger.debug(st.session_state.code, st.session_state.expected_behavior,
                                    st.session_state.test_code if use_tests else "", mode=mode)
        except InputValidationError as exc:
            status.update(label=str(exc), state="error")
            return
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
            logger.exception("analysis failed")
            status.update(label=f"Analysis failed: {exc}", state="error")
            return
        status.update(label=f"Done in {result.duration:.1f}s — {REPAIR_STATUS_LABELS[result.repair_status]}",
                      state="complete", expanded=False)
    st.session_state.debug_result = result
    st.session_state.chat_messages = []
    if settings.history_enabled:
        try:
            save_session(settings.database_url, result.to_dict())
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
            st.warning(f"Could not save to history: {exc}")


def _summary(result: DebugResult) -> None:
    counts = severity_counts(result.all_issues)
    tone = {"verified": "green", "unverified": "blue", "no_changes": "green", "failed_validation": "red",
            "invalid_syntax": "red", "llm_failed": "yellow", "not_attempted": "default"}[result.repair_status]
    after = f"→ {result.quality_after:.0f}" if result.quality_after is not None and result.code_changed else ""
    metric_row([
        metric_card("Total issues", len(result.all_issues), f"{len(result.static_issues)} confirmed · "
                                                            f"{len(result.ai_issues)} AI-inferred", "purple"),
        metric_card("Critical / errors", counts["critical"] + counts["error"], f"{counts['warning']} warnings",
                    "red" if counts["critical"] + counts["error"] else "green"),
        metric_card("Quality score", f"{result.quality_before:.0f} {after}", f"grade {quality_grade(result.quality_before)}",
                    "blue"),
        metric_card("Repair status", result.repair_status.replace("_", " "), f"{result.attempts} attempt(s)", tone),
        metric_card("Analysis time", f"{result.duration:.1f}s", result.model_name or "no LLM", "default"),
    ])
    if result.llm_message:
        st.caption(result.llm_message)
    if result.pylint_error:
        st.caption(f"Pylint: {result.pylint_error}")


def _issues_tab(result: DebugResult) -> None:
    confirmed = [i for i in result.static_issues if i.confidence != Confidence.AI_INFERRED]
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="cm-section-title">Confirmed by static analysis</div>', unsafe_allow_html=True)
        st.caption("Deterministic findings from AST and Pylint.")
        render_issue_table(confirmed, "Static analysis found no issues.")
    with right:
        st.markdown('<div class="cm-section-title">AI-inferred potential issues</div>', unsafe_allow_html=True)
        st.caption("Suggested by the language model. Review before trusting.")
        if result.llm_used:
            render_issue_table(result.ai_issues, "The AI reported no additional issues.")
        else:
            st.info("AI analysis was not run. " + result.llm_message, icon=":material/smart_toy:")


def _correction_tab(result: DebugResult) -> None:
    if not result.llm_used:
        st.info("No AI correction available. Start Ollama (see Settings) and run the hybrid mode.",
                icon=":material/smart_toy:")
        return
    st.markdown(f"**Status:** {REPAIR_STATUS_LABELS[result.repair_status]}")
    if not result.code_changed:
        st.success("The AI did not change the code.", icon=":material/check:")
    diff = compare_code(result.original_code, result.corrected_code)
    metric_row([metric_card("Added lines", diff.added, "", "green"),
                metric_card("Removed lines", diff.removed, "", "red"),
                metric_card("Modified lines", diff.modified, "", "yellow"),
                metric_card("Similarity", f"{diff.similarity:.0%}", "difflib ratio", "blue")])
    st.markdown(render_side_by_side_html(diff), unsafe_allow_html=True)
    st.markdown('<div class="cm-section-title">Corrected code</div>', unsafe_allow_html=True)
    st.caption("Use the copy icon in the top-right corner of the block to copy the code.")
    st.code(result.corrected_code, language="python", line_numbers=True)
    st.download_button("Download corrected .py", result.corrected_code, file_name="corrected_code.py",
                       mime="text/x-python", icon=":material/download:")
    if result.notes:
        with st.expander("Pipeline notes"):
            for note in result.notes:
                st.write(f"- {note}")


def _explanation_tab(result: DebugResult) -> None:
    if not result.llm_used:
        st.info("Explanations come from the AI engine, which was not used for this run.")
        return
    st.caption("AI-generated explanation. It may contain mistakes.")
    st.markdown(result.explanation or "_No explanation returned._")
    if result.changes:
        st.markdown("**Changes made**")
        for change in result.changes:
            st.markdown(f"- {change}")
    if result.assumptions:
        st.markdown("**Assumptions**")
        for item in result.assumptions:
            st.markdown(f"- {item}")
    if result.optimization_suggestions:
        st.markdown("**Optimisation ideas (AI estimate)**")
        for item in result.optimization_suggestions:
            st.markdown(f"- {item}")


def _metrics_tab(result: DebugResult) -> None:
    before, after = result.metrics_before, result.metrics_after
    if not before.available:
        st.warning(before.error or "Metrics unavailable because the code does not parse.")
    labels = ["Quality score", "Maintainability index", "Avg. complexity", "Max complexity", "LOC"]
    b_values = [result.quality_before, before.maintainability_index, before.average_complexity,
                before.max_complexity, before.loc]
    fig = go.Figure()
    fig.add_bar(name="Before", x=labels, y=b_values, marker_color="#4C8DFF")
    if after is not None and result.code_changed:
        a_values = [result.quality_after or 0, after.maintainability_index, after.average_complexity,
                    after.max_complexity, after.loc]
        fig.add_bar(name="After", x=labels, y=a_values, marker_color="#7C6CFF")
    fig.update_layout(barmode="group", title="Measured metrics (Radon) before vs after")
    st.plotly_chart(plotly_layout(fig, 360), width="stretch")
    if before.functions:
        st.markdown("**Cyclomatic complexity per function (before)**")
        st.dataframe([{"function": f.name, "line": f.lineno, "complexity": f.complexity, "rank": f.rank}
                      for f in before.functions], width="stretch", hide_index=True)
    with st.expander("How is the quality score calculated?"):
        st.markdown("""
`issue_penalty = 25×critical + 10×error + 3×warning + min(10, 0.5×info)`
`complexity_penalty = 3 × (functions with cyclomatic complexity > 10)`
`quality = 0.7 × max(0, 100 − issue_penalty − complexity_penalty) + 0.3 × maintainability_index`
Capped at 20 if there is a syntax error. All inputs are measured, not AI estimates.""")


def _tests_tab(result: DebugResult) -> None:
    report = result.test_report
    if report is None:
        st.info("No tests were run for this analysis. Create tests on the **Test Case Generator** page, then "
                "tick *Validate with my tests* before analysing. Tests run only inside the Docker sandbox.",
                icon=":material/science:")
        return
    metric_row([metric_card("Passed", report.passed, "", "green"), metric_card("Failed", report.failed, "", "red"),
                metric_card("Errors", report.errors, "", "yellow"),
                metric_card("Pass rate", f"{report.pass_rate:.0%}", report.status, "blue")])
    st.caption(report.message)
    if report.cases:
        st.dataframe(report.cases, width="stretch", hide_index=True)


def _report_tab(result: DebugResult) -> None:
    payload = result.to_dict()
    name = safe_filename(f"codemind_report_{result.session_id}")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("Download JSON report", generate_json_report(payload), file_name=f"{name}.json",
                           mime="application/json", icon=":material/data_object:", width="stretch")
    with col2:
        try:
            pdf = generate_pdf_report(payload)
            st.download_button("Download PDF report", pdf, file_name=f"{name}.pdf", mime="application/pdf",
                               icon=":material/picture_as_pdf:", width="stretch")
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
            st.error(f"PDF generation failed: {exc}")


def render() -> None:
    page_header("AI Code Debugger", "Detect, explain and fix bugs with static analysis and a local LLM.", "🐞")
    settings = current_settings()
    _input_panel()

    controls = st.columns([3, 2, 1.3])
    with controls[0]:
        mode = st.radio("Analysis mode", list(MODE_LABELS), format_func=MODE_LABELS.get, horizontal=False,
                        label_visibility="collapsed")
    with controls[1]:
        has_tests = bool(st.session_state.test_code.strip())
        use_tests = st.checkbox("Validate with my tests (sandbox)", value=has_tests, disabled=not has_tests,
                                help="Tests come from the Test Case Generator page.")
        st.caption(f"Max repair attempts: {settings.max_repair_attempts} · model: {settings.model_name}")
    with controls[2]:
        run = st.button("Analyse code", type="primary", icon=":material/play_arrow:", width="stretch")
    if run:
        _run_analysis(mode, use_tests and mode == "hybrid")

    result: DebugResult | None = st.session_state.debug_result
    if result is None:
        return
    st.divider()
    _summary(result)
    tabs = st.tabs(["Issues", "Correction & diff", "Explanation", "Metrics", "Tests", "Report"])
    with tabs[0]:
        _issues_tab(result)
    with tabs[1]:
        _correction_tab(result)
    with tabs[2]:
        _explanation_tab(result)
    with tabs[3]:
        _metrics_tab(result)
    with tabs[4]:
        _tests_tab(result)
    with tabs[5]:
        _report_tab(result)
