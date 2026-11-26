"""AI Code Assistant page: chat about the current code."""

from __future__ import annotations

import streamlit as st

from core.complexity_analyzer import analyze_complexity
from core.llm_engine import LLMError
from core.static_analyzer import analyze_static
from utils.prompts import ASSISTANT_SYSTEM_PROMPT, build_assistant_context
from views.components import current_settings, get_llm, page_header, require_code

QUICK_QUESTIONS = [
    "Why is my code not working?",
    "Explain this function step by step.",
    "How can I improve this algorithm?",
    "What is the estimated time complexity?",
    "Explain the detected errors.",
    "Generate test cases for this function.",
]
MAX_HISTORY_MESSAGES = 12


@st.cache_data(show_spinner=False, max_entries=20)
def _context_for(code: str) -> str:
    static = analyze_static(code, use_pylint=False)
    metrics = analyze_complexity(code)
    summary = (f"LOC={metrics.loc}, avg complexity={metrics.average_complexity}, "
               f"maintainability={metrics.maintainability_index}") if metrics.available else "unavailable"
    return build_assistant_context(code, static.issues, summary)


def render() -> None:
    page_header("AI Code Assistant", "Ask questions about the code currently loaded in the debugger.", "💬")
    if not require_code():
        return
    settings = current_settings()
    llm = get_llm(settings)
    if llm is None:
        st.warning("The assistant needs a running Ollama model. Open **Settings** to check the connection.",
                   icon=":material/cloud_off:")
    with st.expander("Code in context", expanded=False):
        st.code(st.session_state.code, language="python", line_numbers=True)

    cols = st.columns(3)
    clicked = None
    for index, question in enumerate(QUICK_QUESTIONS):
        if cols[index % 3].button(question, key=f"quick_{index}", width="stretch", disabled=llm is None):
            clicked = question
    if st.button("Clear conversation", icon=":material/delete_sweep:"):
        st.session_state.chat_messages = []
        st.rerun()

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🧠"):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask about your code…", disabled=llm is None) or clicked
    if not prompt or llm is None:
        return
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    messages = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
                {"role": "user", "content": _context_for(st.session_state.code)},
                {"role": "assistant", "content": "I have read the code and the analysis. What would you like to know?"}]
    messages += st.session_state.chat_messages[-MAX_HISTORY_MESSAGES:]
    with st.chat_message("assistant", avatar="🧠"):
        with st.spinner("Thinking…"):
            try:
                answer = llm.chat(messages)
            except LLMError as exc:
                answer = f"⚠️ The model could not answer: {exc}"
        st.markdown(answer or "_The model returned an empty answer._")
    st.session_state.chat_messages.append({"role": "assistant", "content": answer})
