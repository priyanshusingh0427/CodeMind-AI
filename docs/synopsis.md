# Project Synopsis

**Title:** CodeMind AI – AI-Powered Python Code Debugger and Optimization System
**Domain:** Artificial Intelligence, Machine Learning, Generative AI, Large Language Models
**Student:** [Your name] · **Roll No.:** [ ] · **Guide:** [Guide name] · **Department:** [AI & ML], [College], [Year]
**Type:** B.Tech final-year major project (individual)

## 1. Introduction
Debugging takes a large share of programming time, and beginners in particular struggle to connect error messages to
root causes. Static analysers (e.g. Pylint) are precise but cannot understand intent; large language models (LLMs)
can explain and fix code but may hallucinate. CodeMind AI combines both and verifies AI output before trusting it.

## 2. Problem statement
Build an offline, free tool that detects errors in Python programs, explains their causes, proposes corrected code,
analyses quality and complexity, suggests optimisations, and validates corrections with tests — without executing
untrusted code on the user's computer and without paid APIs, on an ordinary laptop.

## 3. Objectives
1. Detect syntax, indentation, name, import, type, runtime-risk, unreachable-code and style problems with line numbers.
2. Generate structured corrections and explanations with a local coding LLM (Ollama + Qwen2.5-Coder).
3. Verify corrections (syntax, static re-analysis, sandboxed tests) with a bounded iterative repair loop.
4. Measure quality (cyclomatic complexity, maintainability index, documented quality score) before and after.
5. Provide a professional dashboard, history, and PDF/JSON reports.
6. Evaluate static-only, LLM-only and hybrid approaches on a custom benchmark with honest, measured metrics.

## 4. Proposed system
A Streamlit application with a modular Python core: AST/symtable checks + Pylint + Radon → structured prompt →
local LLM (JSON) → Pydantic validation → syntax revalidation → static re-analysis → optional tests in a Docker
sandbox (no network, non-root, resource limits) → up to N repair attempts → diff, metrics, SQLite history, reports.

## 5. Methodology (summary)
Deterministic analysis first; LLM second; independent verification last. Dataset of 122 original buggy programs
with reference fixes and tests (30 dev / 92 eval), with validation tests separated from held-out scoring tests.
Metrics: precision, recall, F1, false-positive rate, repair rate, test pass rate, response time, complexity changes.

## 6. Tools and technologies
Python 3.11+, Streamlit, Ollama, Qwen2.5-Coder, ast/symtable, Pylint, Radon, Pytest, SQLite + SQLAlchemy, Plotly,
difflib, Pandas, NumPy, scikit-learn, Pydantic, ReportLab, Docker. All free and open source.

## 7. Hardware/software requirements
8–16 GB RAM, 4+ CPU cores, no GPU; Windows/macOS/Linux; VS Code; optional Docker Desktop.

## 8. Expected outcomes
A working application, a reproducible benchmark with measured results, and documentation (SRS, design, report,
research paper draft). Early measurement: static analysis alone reached recall 0.38 with no false positives on the
eval split and found none of the logical bugs, which motivates the hybrid approach. LLM results are pending.

## 9. Scope and limitations
Single-file Python programs up to ~800 lines; small local models may be wrong; tests do not prove correctness.

## 10. Timeline (indicative)
| Weeks | Work |
|---|---|
| 1–2 | Literature review, requirements, design |
| 3–5 | Static analysis, metrics, LLM integration |
| 6–7 | Repair loop, sandbox, test generation |
| 8–9 | UI, database, reports |
| 10–11 | Dataset, evaluation, results |
| 12 | Documentation, viva preparation |
