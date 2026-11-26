# Developer Guide

## Setup
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
streamlit run app.py
```

## Code layout and rules
- `views/` contains **only** Streamlit code. Each page exposes `render()`; shared widgets live in
  `views/components.py`. Pages never call Ollama/Docker directly except through `core/` objects.
- `core/` contains logic with no Streamlit imports, so it is unit-testable and reusable by the benchmark.
- `utils/validators.py` holds all Pydantic schemas and enums (`Issue`, `Severity`, `Category`, `Confidence`,
  `AIDebugResponse`, `TestCaseSpec`…).
- Configuration: `config.Settings` (frozen dataclass). Never read env vars elsewhere; use `settings.with_overrides()`.
- Logging: `utils.logger.get_logger(name)` → JSON lines in `logs/codemind.log`. Pass context via `extra={...}`.
- Style: PEP 8, 120-char lines, type hints, docstrings on public functions.

## Extending
**New static check** – add a `visit_*` method in `_PatternVisitor` (`core/syntax_checker.py`) that appends an
`Issue` (choose category/severity/confidence), then add a test in `tests/test_syntax_checker.py`.

**Map more Pylint messages** – extend `SYMBOL_CATEGORY` in `core/static_analyzer.py`.

**Another LLM backend** – implement the `LLMClient` protocol (`model`, `check_status`, `chat`, `generate_json`)
and return it from `views/components.get_llm`. The rest of the pipeline is unchanged.

**Change prompts** – edit `utils/prompts.py`. Keep the untrusted-code delimiters and the JSON schema hint. Tune
only on the **dev** split, then evaluate on **eval**.

**New optimiser rule** – add a check in `_LoopPatternVisitor` (`core/optimizer.py`) returning a `Suggestion`.

**New page** – create `views/<page>.py` with `render()`, register it in `app.py` (`st.Page(...)`).

**Dataset** – add examples with `ex(...)` in `datasets/build_dataset.py` and run `python -m datasets.build_dataset`;
the builder refuses examples whose bug is not observable by its tests.

## Testing
- `tests/conftest.py` provides `ScriptedLLM` (deterministic replies) and a temporary-database `settings` fixture.
- HTTP is mocked with `unittest.mock`; Docker is replaced with fake sandboxes; `tests/test_sandbox_docker.py`
  runs only when the real image exists.
- `tests/mock_ollama_server.py` lets you click through the UI without a model (canned answers only).

## Database
`database/models.DebugSessionRecord` (one table). `database/connection.get_engine()` creates tables on first use.
For schema changes during development delete `data/codemind.db` or add a migration tool such as Alembic.

## Release checklist
1. `pytest` green; 2. `python -m pylint core utils database evaluation --disable=C,R` clean of errors;
3. update `PROJECT_STATUS.md`; 4. re-run benchmarks if analyzers or prompts changed; 5. update screenshots.
