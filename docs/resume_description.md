# Resume Project Description

**Short (one line)**
CodeMind AI – offline AI Python debugger combining static analysis, a local LLM (Ollama/Qwen2.5-Coder) and
Docker-sandboxed test validation with a bounded self-repair loop (Python, Streamlit, Pylint, Radon, SQLite).

**Bullet version**
- Built an offline, hybrid Python debugging system that merges AST/symtable checks and Pylint with a local coding LLM;
  AI corrections are schema-validated, re-parsed, re-analysed and tested before being accepted.
- Implemented a hardened Docker sandbox (no network, non-root, read-only FS, CPU/memory/PID limits, timeouts) and
  verified its guarantees with integration tests.
- Created a 122-program bug benchmark with automatically verified reference fixes and leakage-free dev/eval and
  validation/held-out test splits; built a reproducible evaluation (precision, recall, F1, FPR, repair rate).
- Delivered a 9-page Streamlit dashboard (diff viewer, Plotly analytics, SQLite history, PDF/JSON reports) with
  86 automated tests.

*Add measured LLM/hybrid results here once the benchmark has been run with Ollama – e.g. "improved recall from
0.38 (static) to X on 92 programs".*
