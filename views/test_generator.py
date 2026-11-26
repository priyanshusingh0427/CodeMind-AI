"""Test Case Generator page: AI-proposed, user-reviewed tests and sandbox runs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.test_generator import generate_tests_with_llm, render_pytest, template_specs, testable_functions
from utils.validators import TestCaseSpec
from views.components import (code_editor, current_settings, get_llm, get_validator, metric_card, metric_row,
                              page_header, sandbox_status)

COLUMNS = ["name", "category", "call", "expected", "expects_exception", "description"]


def _specs_to_df(specs: list[TestCaseSpec]) -> pd.DataFrame:
    return pd.DataFrame([s.model_dump() for s in specs], columns=COLUMNS)


def _df_to_specs(df: pd.DataFrame) -> list[TestCaseSpec]:
    specs = []
    for row in df.fillna("").to_dict("records"):
        if str(row.get("call", "")).strip():
            specs.append(TestCaseSpec(**{k: str(row.get(k, "")) for k in COLUMNS}))
    return specs


def render() -> None:
    page_header("Test Case Generator", "Generate candidate tests, review them, then run them in the sandbox.", "🧪")
    settings = current_settings()
    with st.expander("Code under test (shared with the debugger)", expanded=not st.session_state.code.strip()):
        code_editor("tests", height=280)

    functions = testable_functions(st.session_state.code) if st.session_state.code.strip() else []
    st.caption("Functions found: " + (", ".join(f"`{f.name}({', '.join(f.args)})`" for f in functions) or "none"))

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        count = st.slider("Number of tests", 3, 15, 8)
    with col2:
        if st.button("Generate with AI", type="primary", icon=":material/auto_awesome:", width="stretch"):
            llm = get_llm(settings)
            if llm is None:
                st.warning("Ollama is not available. Use the manual template instead, or start Ollama.")
            elif not functions:
                st.warning("No top-level functions to test.")
            else:
                with st.spinner(f"Asking {settings.model_name} for test cases…"):
                    specs, error = generate_tests_with_llm(llm, st.session_state.code,
                                                           st.session_state.expected_behavior, count)
                if error:
                    st.error(error)
                else:
                    st.session_state.test_specs = specs
                    st.session_state.spec_version += 1
                    st.session_state.test_code = render_pytest(specs)[0]
    with col3:
        if st.button("Manual template", icon=":material/edit_note:", width="stretch"):
            st.session_state.test_specs = template_specs(st.session_state.code)
            st.session_state.spec_version += 1

    st.info("AI-generated tests are **candidates**. They reflect the model's understanding of the intended "
            "behaviour and can be wrong. Independent benchmark tests are kept separately in "
            "`datasets/benchmark.json`.", icon=":material/info:")

    st.markdown('<div class="cm-section-title">Review and edit test cases</div>', unsafe_allow_html=True)
    edited = st.data_editor(
        _specs_to_df(st.session_state.test_specs), num_rows="dynamic", width="stretch", key=f"spec_editor_{st.session_state.spec_version}",
        column_config={
            "category": st.column_config.SelectboxColumn(options=["normal", "edge", "boundary", "invalid"]),
            "call": st.column_config.TextColumn(help="Python expression, e.g. add(2, 3)"),
            "expected": st.column_config.TextColumn(help="Python literal, e.g. 5 or [1, 2]"),
            "expects_exception": st.column_config.TextColumn(help="e.g. ValueError (leave expected empty)"),
        })
    if st.button("Build pytest file from table", icon=":material/build:"):
        specs = _df_to_specs(edited)
        st.session_state.test_specs = specs
        code, warnings = render_pytest(specs)
        st.session_state.test_code = code
        for warning in warnings:
            st.warning(warning)

    st.markdown('<div class="cm-section-title">pytest file (editable)</div>', unsafe_allow_html=True)
    st.session_state.test_code = st.text_area("pytest code", value=st.session_state.test_code, height=300,
                                              label_visibility="collapsed",
                                              help="The code under test is importable as `solution`.")
    if st.session_state.test_code.strip():
        st.download_button("Download test_solution.py", st.session_state.test_code, file_name="test_solution.py",
                           icon=":material/download:")

    st.markdown('<div class="cm-section-title">Run in isolated sandbox</div>', unsafe_allow_html=True)
    status = sandbox_status(settings)
    if not status.available:
        st.warning(f"{status.message} Tests will not be executed on your computer without isolation.",
                   icon=":material/shield:")
        return
    target_options = ["Original code"]
    result = st.session_state.debug_result
    if result is not None and result.code_changed:
        target_options.append("AI-corrected code")
    target = st.radio("Run tests against", target_options, horizontal=True)
    if st.button("Run tests", type="primary", icon=":material/play_arrow:"):
        validator = get_validator(settings)
        code = result.corrected_code if target == "AI-corrected code" and result else st.session_state.code
        with st.spinner("Running tests in Docker sandbox…"):
            st.session_state.test_report = validator.validate(code, st.session_state.test_code) if validator else None
    report = st.session_state.test_report
    if report is not None:
        metric_row([metric_card("Passed", report.passed, "", "green"), metric_card("Failed", report.failed, "", "red"),
                    metric_card("Errors", report.errors, "", "yellow"),
                    metric_card("Pass rate", f"{report.pass_rate:.0%}", report.status, "blue")])
        st.caption(report.message)
        if report.cases:
            st.dataframe(report.cases, width="stretch", hide_index=True)
