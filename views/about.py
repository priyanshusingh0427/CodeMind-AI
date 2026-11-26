"""About Project page."""

from __future__ import annotations

import streamlit as st

from config import APP_NAME, APP_TAGLINE, APP_VERSION
from views.components import page_header

ARCHITECTURE_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#1C2440", color="#7C6CFF", fontcolor="#E6E9F5",
        fontname="Helvetica", fontsize=10];
  edge [color="#4C8DFF"];
  UI [label="Streamlit UI"]; AST [label="AST analysis"]; PL [label="Pylint"]; RD [label="Radon metrics"];
  PR [label="Prompt builder"]; LLM [label="Ollama LLM"]; VAL [label="Pydantic validation"];
  SYN [label="Syntax revalidation"]; SBX [label="Docker sandbox tests"]; REP [label="Repair loop (≤ N)"];
  DIFF [label="difflib comparison"]; DB [label="SQLite (SQLAlchemy)"]; RPT [label="Dashboard / PDF / JSON"];
  UI -> AST -> PL -> RD -> PR -> LLM -> VAL -> SYN -> SBX -> REP; REP -> LLM [style=dashed, label="fail"];
  REP -> DIFF -> DB -> RPT;
}
"""


def render() -> None:
    page_header("About Project", f"{APP_NAME} v{APP_VERSION} — B.Tech AI & ML final-year major project.", "🎓")
    st.markdown(f"""
**{APP_NAME}** — *{APP_TAGLINE}* — is a hybrid, self-verifying debugging framework. It combines deterministic
static analysis (AST, Pylint, Radon) with a locally hosted coding LLM (via Ollama) and validates AI corrections
against independent tests inside an isolated Docker sandbox, with a bounded iterative repair loop.
""")
    st.graphviz_chart(ARCHITECTURE_DOT, width="stretch")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
#### Research question
Does combining static analysis, LLM correction and independent test validation with limited iterative repair
improve debugging outcomes compared with (1) static analysis alone and (2) a standalone LLM?

#### Compared approaches
- **Baseline 1** – static analysis only (detection, no repair)
- **Baseline 2** – standalone LLM correction (single call, no static context, no validation)
- **Proposed** – static analysis + LLM + validation + up to *N* repair attempts

Run `python -m evaluation.benchmark_runner` to measure them. No results are shown until they are measured.
""")
    with col2:
        st.markdown("""
#### Technology stack
Python 3.11+ · Streamlit · Ollama + Qwen2.5-Coder · ast/symtable · Pylint · Radon · Pytest · SQLite + SQLAlchemy ·
Plotly · difflib · Pandas/NumPy · scikit-learn · Pydantic · ReportLab · Docker

#### Design principles
- Runs offline on 8–16 GB RAM, no GPU, no paid API keys
- Confirmed findings are separated from AI-inferred ones
- Submitted code is untrusted: never executed on the host, never treated as instructions to the LLM
- Graceful degradation: no Ollama → static analysis; no Docker → no execution
""")
    st.markdown("#### Limitations")
    st.markdown("""
- Small local models can miss bugs or propose wrong fixes; every AI output is labelled as such.
- Static analysis cannot find most logical errors without a description of intended behaviour.
- Tests demonstrate behaviour on specific inputs only; passing tests do not prove correctness.
- The heuristic Big-O estimate is based on loop nesting and recursion shape and is not a measurement.
""")
