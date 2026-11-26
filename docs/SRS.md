# Software Requirements Specification (SRS) – CodeMind AI

Version 1.0 · Structure follows IEEE 830 / ISO/IEC/IEEE 29148 in simplified form.

## 1. Introduction
### 1.1 Purpose
Specifies the requirements of CodeMind AI, an offline tool that detects, explains and repairs bugs in small Python
programs by combining static analysis with a local large language model and sandboxed test validation.

### 1.2 Scope
Single-user desktop web application (Streamlit) for students and developers. It analyses one Python file/snippet at
a time (default limit 800 lines / 30 000 characters). It does not modify the user's files, does not require
internet access after installation and does not use paid APIs.

### 1.3 Definitions
| Term | Meaning |
|---|---|
| Confirmed issue | Finding from a deterministic tool (AST, symtable, Pylint) |
| AI-inferred issue | Finding reported by the LLM; may be wrong |
| Sandbox | Docker container with network, privilege and resource restrictions |
| Repair attempt | One LLM call producing a candidate correction |
| Verified | Candidate passed all provided tests in the sandbox |

### 1.4 References
Project brief; [architecture.md](architecture.md); [methodology.md](methodology.md).

## 2. Overall description
### 2.1 Product perspective
Standalone application: Streamlit UI → Python core → Ollama (local HTTP) and Docker (local CLI) → SQLite file.

### 2.2 User classes
- **Student** – pastes code, reads explanations, learns from diffs.
- **Developer/evaluator** – runs benchmarks, inspects metrics, exports reports.

### 2.3 Operating environment
Windows 10/11, macOS 12+, Linux; Python 3.11+; 8–16 GB RAM; no GPU required. Optional: Ollama, Docker.

### 2.4 Constraints
Free and open-source only; no JavaScript front-end development; no execution of untrusted code on the host.

### 2.5 Assumptions and dependencies
Ollama and a coding model are installed for AI features; Docker is installed for dynamic validation.

## 3. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall accept code by typing/pasting in a syntax-highlighted editor with line numbers. | High |
| FR-02 | The system shall accept `.py` uploads (UTF-8, ≤ 2 MB) and reject binary/oversized input with a message. | High |
| FR-03 | The system shall provide sample buggy programs and a clear/reset action. | Medium |
| FR-04 | The system shall accept an optional description of intended behaviour. | High |
| FR-05 | The system shall detect syntax and indentation errors with line numbers without executing code. | High |
| FR-06 | The system shall detect undefined names, missing imports, unreachable code, unused variables, type hazards, potential runtime errors and bad practices. | High |
| FR-07 | Each issue shall have line, category, severity, source, confidence and, where possible, a suggestion. | High |
| FR-08 | The system shall distinguish confirmed findings from AI-inferred findings in UI and reports. | High |
| FR-09 | The system shall request a structured JSON correction from a local LLM including findings, corrected code, change list, explanation and assumptions. | High |
| FR-10 | The system shall validate LLM output against a schema, retry a bounded number of times, and fall back to static results on failure. | High |
| FR-11 | The system shall re-check corrected code for syntax errors and new static errors. | High |
| FR-12 | When tests and a sandbox are available, the system shall run tests and perform at most N repair attempts (configurable, default 3). | High |
| FR-13 | The system shall show original and corrected code side by side with added/removed/modified highlighting, and allow copy and download. | High |
| FR-14 | The system shall compute LOC, cyclomatic complexity, maintainability index and a documented quality score before and after correction. | High |
| FR-15 | The system shall provide optimisation suggestions, separating measured, rule-based and AI-estimated items. | Medium |
| FR-16 | The system shall generate candidate tests (normal, edge, boundary, invalid) and let users edit them before running. | Medium |
| FR-17 | The system shall offer a chat assistant that answers questions about the current code. | Medium |
| FR-18 | The system shall store sessions in SQLite and support search, filters, viewing and deletion; storage can be disabled. | Medium |
| FR-19 | The system shall export PDF and JSON reports including limitations and recommendations. | Medium |
| FR-20 | The system shall display analytics charts for the current session, history and benchmark results. | Medium |
| FR-21 | The system shall allow configuration of model, temperature, timeout, retries, context length, repair limit, sandbox limits and history. | Medium |
| FR-22 | The system shall provide a benchmark script comparing static, LLM-only and hybrid methods and saving measured results to CSV/JSON. | High |

## 4. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Security | Submitted and AI-generated code shall never be executed on the host; execution only in the sandbox. |
| NFR-02 | Security | Sandbox: no network, non-root, CPU/memory/PID limits, read-only FS, timeout, output limit, no sensitive mounts. |
| NFR-03 | Security | Code and user text shall be treated as untrusted data in prompts (prompt-injection mitigation). |
| NFR-04 | Privacy | All data stays local; no telemetry (`gatherUsageStats=false`); history can be disabled and deleted. |
| NFR-05 | Performance | Static analysis of a 100-line file in < 5 s on a typical laptop (measured mean 0.29 s on benchmark programs). |
| NFR-06 | Performance | LLM calls time out after a configurable limit (default 180 s). |
| NFR-07 | Reliability | Missing Ollama or Docker shall degrade features gracefully, never crash the app. |
| NFR-08 | Usability | Dark, accessible theme; status pills; loading indicators; clear labels for AI content. |
| NFR-09 | Portability | Runs on Windows, macOS and Linux with Python 3.11+. |
| NFR-10 | Maintainability | Modular layers, type hints, docstrings, PEP 8, ≥ 70 automated tests. |
| NFR-11 | Honesty | The system shall not claim that passing tests proves correctness and shall label estimates. |

## 5. Hardware and software requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores x86-64 / Apple Silicon | 8 cores |
| RAM | 8 GB (1.5b model) | 16 GB (7b model) |
| Disk | 5 GB free | 10 GB |
| GPU | Not required | Optional (faster LLM) |
| OS | Windows 10, macOS 12, Ubuntu 22.04 | Latest |
| Software | Python 3.11+, pip, a browser | + Ollama, Docker Desktop/Engine, VS Code |

## 6. External interfaces
- **UI:** browser at `http://localhost:8501`.
- **Ollama:** HTTP `GET /api/tags`, `POST /api/chat` on `OLLAMA_HOST`.
- **Docker:** `docker info`, `docker image inspect`, `docker build`, `docker run`, `docker kill`.
- **Database:** SQLite file `data/codemind.db` via SQLAlchemy.
- **Files:** `.py` upload; `.py`, `.json`, `.pdf` downloads.
