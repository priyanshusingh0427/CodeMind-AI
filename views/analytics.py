"""Analytics Dashboard page: current session, history trends and evaluation results."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import EVAL_RESULTS_DIR
from core.ai_debugger import DebugResult
from database.operations import list_sessions
from views.components import (SEVERITY_COLORS, current_settings, metric_card, metric_row, page_header,
                              plotly_layout, severity_counts)


def _current_session(result: DebugResult) -> None:
    issues = result.all_issues
    counts = severity_counts(issues)
    test = result.test_report
    metric_row([
        metric_card("Total issues", len(issues), "", "purple"),
        metric_card("Critical", counts["critical"], "", "red"),
        metric_card("Errors", counts["error"], "", "red"),
        metric_card("Warnings", counts["warning"], "", "yellow"),
        metric_card("Lines of code", result.metrics_before.loc, "", "blue"),
        metric_card("Tests passed", f"{test.passed}/{test.total}" if test else "–", test.status if test else "not run",
                    "green"),
    ])
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(go.Pie(labels=list(counts), values=list(counts.values()), hole=0.55,
                               marker_colors=[SEVERITY_COLORS[k] for k in counts]))
        fig.update_layout(title="Issues by severity")
        st.plotly_chart(plotly_layout(fig), width="stretch")
    with col2:
        if issues:
            df = pd.DataFrame([{"category": i.category.value.replace("_", " "),
                                "confidence": i.confidence.value} for i in issues])
            grouped = df.groupby(["category", "confidence"]).size().reset_index(name="count")
            fig = px.bar(grouped, x="count", y="category", color="confidence", orientation="h",
                         title="Issues by category", color_discrete_map={"confirmed": "#4C8DFF",
                                                                          "ai_inferred": "#7C6CFF",
                                                                          "heuristic": "#F5C451"})
            st.plotly_chart(plotly_layout(fig), width="stretch")
        else:
            st.success("No issues in the current session.")
    if result.metrics_after is not None and result.code_changed:
        b, a = result.metrics_before, result.metrics_after
        categories = ["Quality", "Maintainability", "Simplicity", "Issue-free"]

        def norm(q: float, mi: float, cc: float, n: int) -> list[float]:
            return [q, mi, max(0.0, 100 - (cc - 1) * 10), max(0.0, 100 - n * 10)]

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=norm(result.quality_before, b.maintainability_index, b.average_complexity,
                                             len(result.static_issues)), theta=categories, fill="toself",
                                      name="Before", line_color="#4C8DFF"))
        fig.add_trace(go.Scatterpolar(r=norm(result.quality_after or 0, a.maintainability_index, a.average_complexity,
                                             len(result.after_issues)), theta=categories, fill="toself",
                                      name="After", line_color="#7C6CFF"))
        fig.update_layout(title="Before vs after (normalised 0–100, measured)", polar=dict(radialaxis=dict(
            range=[0, 100])))
        st.plotly_chart(plotly_layout(fig, 380), width="stretch")
    timings = result.stage_timings
    if timings:
        fig = px.bar(x=list(timings.values()), y=list(timings), orientation="h", title="Time per pipeline stage (s)",
                     labels={"x": "seconds", "y": "stage"})
        st.plotly_chart(plotly_layout(fig, 260), width="stretch")


def _history_trends(settings) -> None:
    if not settings.history_enabled:
        st.caption("History storage is disabled.")
        return
    rows = list_sessions(settings.database_url, limit=500)
    if not rows:
        st.caption("No stored sessions yet.")
        return
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"])
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_scatter(x=df["created_at"], y=df["quality_before"], mode="lines+markers", name="Before")
        fig.add_scatter(x=df["created_at"], y=df["quality_after"], mode="lines+markers", name="After")
        fig.update_layout(title="Quality score over time", yaxis_range=[0, 100])
        st.plotly_chart(plotly_layout(fig), width="stretch")
    with col2:
        counts = df["repair_status"].value_counts().reset_index()
        counts.columns = ["status", "count"]
        fig = px.pie(counts, names="status", values="count", hole=0.5, title="Repair outcomes")
        st.plotly_chart(plotly_layout(fig), width="stretch")
    fig = px.histogram(df, x="duration", nbins=20, title="Analysis duration distribution (s)")
    st.plotly_chart(plotly_layout(fig, 260), width="stretch")


def _evaluation_results() -> None:
    summary_path = EVAL_RESULTS_DIR / "summary.json"
    trial_path = EVAL_RESULTS_DIR / "summary_trial.json"
    if trial_path.exists():
        choice = st.radio("Results", ["Main results (full eval split)", "Latest trial run (--limit / other split)"],
                          horizontal=True, label_visibility="collapsed")
        if choice.startswith("Latest"):
            summary_path = trial_path
            st.caption("Trial runs use a subset of the data; do not report them as final results.")
    if not summary_path.exists():
        st.info("No benchmark results yet. Run `python -m evaluation.benchmark_runner` to measure the three "
                "approaches. Results are only shown after they have actually been computed.",
                icon=":material/lab_research:")
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        st.error(f"Could not read {summary_path}: {exc}")
        return
    meta = summary.get("meta", {})
    st.caption(f"Run at {meta.get('timestamp', '?')} · split `{meta.get('split', '?')}` · "
               f"{meta.get('n_examples', '?')} examples · model `{meta.get('model', 'n/a')}`")
    methods = summary.get("methods", {})
    if not methods:
        st.warning("Summary file contains no method results.")
        return
    table = pd.DataFrame(methods).T.astype(str).replace({"None": "–", "nan": "–"})
    numeric_table = pd.DataFrame(methods).T
    st.dataframe(table, width="stretch")
    numeric = [c for c in ("precision", "recall", "f1", "repair_rate", "test_pass_rate") if c in table.columns]
    if numeric:
        values = numeric_table[numeric].apply(pd.to_numeric, errors="coerce").reset_index()
        long = values.melt(id_vars="index", var_name="metric", value_name="value")
        long = long.dropna()
        fig = px.bar(long, x="metric", y="value", color="index", barmode="group",
                     title="Measured benchmark metrics by method", labels={"index": "method"})
        st.plotly_chart(plotly_layout(fig, 360), width="stretch")
    for note in summary.get("notes", []):
        st.caption(f"• {note}")


def render() -> None:
    page_header("Analytics Dashboard", "Interactive charts for the current session, history and benchmarks.", "📊")
    settings = current_settings()
    tab1, tab2, tab3 = st.tabs(["Current session", "History trends", "Benchmark results"])
    with tab1:
        result = st.session_state.debug_result
        if result is None:
            st.info("Run an analysis in the AI Code Debugger to see session analytics.")
        else:
            _current_session(result)
    with tab2:
        _history_trends(settings)
    with tab3:
        _evaluation_results()
