# CodeMind AI – Implementation Plan

This is the plan agreed before implementation, kept as a record of the design decisions.

## 1. Dependencies and compatibility

| Need | Choice | Why |
|---|---|---|
| Language | Python 3.11+ (tested on 3.11 and 3.13) | Required by the brief; `ast`/`symtable` are stable here |
| UI | Streamlit ≥ 1.50 with `st.navigation` | Multi-page app without any JavaScript |
| Code editor | `streamlit-ace` | Syntax highlighting, line numbers, gutter annotations; falls back to `st.text_area` |
| LLM | Ollama + `qwen2.5-coder:1.5b` (default), 3b/7b optional | Free, local, CPU-friendly |
| LLM client | `requests` against the Ollama REST API | No extra SDK; easy to mock in tests |
| Static analysis | `ast` + `symtable` (own checks) + Pylint (subprocess) | Deterministic, confirmed findings |
| Metrics | Radon (CC, MI, Halstead, raw) | Measured, not estimated |
| Validation | Pydantic v2 | Validates and coerces LLM JSON |
| Execution | Docker sandbox running pytest | Never runs untrusted code on the host |
| Storage | SQLite via SQLAlchemy 2.0 | Zero setup, local only |
| Charts | Plotly | Interactive, dark theme |
| Reports | ReportLab (PDF) + JSON | Free, pure Python |
| Metrics for evaluation | scikit-learn | Precision / recall / F1 / confusion matrix |

**Substitutions / clarifications**
- *Docker* is used for the isolated validation module only. The app also has an optional `Dockerfile`, but
  inside it the sandbox is disabled (no Docker-in-Docker).
- *QuixBugs* is supported through a conversion script; *BugsInPy* is documented but not integrated, because its
  bugs live inside full real-world projects that need per-project environments (too heavy for 8–16 GB laptops).
- The sandbox image is built from `python:3.11-slim` + pytest (`sandbox/Dockerfile`).

## 2. Architectural assumptions

1. The submitted code is **untrusted**: it is parsed, never imported or executed on the host, and it is wrapped
   in delimiters in every prompt with an instruction to ignore embedded instructions.
2. Small local models make mistakes, so every AI output is labelled *AI-inferred* and validated: schema check →
   syntax check → static re-analysis → (optional) sandboxed tests → bounded repair loop.
3. If Ollama is offline → static-analysis-only mode. If Docker is unavailable → no code execution at all.
4. One code path serves both the app and the evaluation (`mode = static | llm_only | hybrid`), so the
   baselines are measured with exactly the same components as the proposed method.

## 3. Folder structure

```
CodeMind-AI/
├── app.py                     Streamlit entry point (st.navigation, sidebar status)
├── config.py                  Settings dataclass (env / .env / Settings page overrides)
├── requirements.txt, .env.example, .gitignore, .dockerignore, LICENSE, Dockerfile, pytest.ini
├── PROJECT_STATUS.md          Phase-by-phase status, test results, next steps
├── .streamlit/config.toml     Dark theme
├── views/                     UI only (one module per page + components.py)
├── core/                      Business logic: analyzers, LLM engine, debugger pipeline, optimizer,
│                              test generation/validation, Docker sandbox, diff
├── database/                  SQLAlchemy models, engine/session, CRUD
├── utils/                     Pydantic schemas, prompts, logging, helpers, report generator
├── assets/style.css           Custom CSS
├── sandbox/                   Dockerfile + in-container pytest runner
├── datasets/                  sample_bugs.json (demo), benchmark.json (122 examples), builders
├── evaluation/                benchmark_runner.py, metrics.py, visualization.py, results/
├── tests/                     Unit tests + mock Ollama server for demos
├── docs/                      Academic and technical documentation
├── data/ logs/ reports/ screenshots/
```

Improvements over the suggested structure: `views/components.py` (shared UI), `sandbox/` (image + runner kept
apart from app code), `datasets/build_dataset.py` (reproducible, verified dataset), `tests/mock_ollama_server.py`
(UI demos without a model), `tests/conftest.py` (scripted LLM double).

## 4. Phases

| Phase | Content | Status |
|---|---|---|
| 1 | Structure, config, logging, schemas | Done |
| 2 | AST/symtable checker, Pylint wrapper, Radon metrics, quality score | Done |
| 3 | Ollama client, prompts, hybrid pipeline with repair loop | Done |
| 4 | Optimizer (measured / rule / AI), difflib comparison | Done |
| 5 | Test generation, Docker sandbox, validator | Done |
| 6 | SQLite history | Done |
| 7 | Streamlit UI (9 pages) | Done |
| 8 | Analytics, PDF/JSON reports | Done |
| 9 | Dataset (122 examples), benchmark runner, charts | Done; LLM methods await a run with Ollama |
| 10 | Tests, docs, status | Done (see PROJECT_STATUS.md) |
