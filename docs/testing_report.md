# Testing Report

Date of last run: 2026-11-26. Every result below was produced by actually running the commands listed.

## 1. Automated unit and integration tests

Command: `pytest` (configuration in `pytest.ini`, tests in `tests/`).

| Environment | Result |
|---|---|
| Linux, Python 3.13.18, Docker sandbox image built | **86 passed** (33.8 s) |
| `python:3.11-slim` container, Python 3.11.18, `pip install -r requirements.txt` (no Docker inside) | **82 passed, 4 skipped** (5.0 s) |
| Windows / macOS | Not tested by the author yet – please run `pytest` and record the result here |

| Test file | Tests | What is covered |
|---|---|---|
| `test_syntax_checker.py` | 15 | syntax/indentation errors, undefined names, scope edge cases (globals, comprehensions, lambdas, star imports), missing imports, unreachable code, unused locals, bad practices, heuristic infinite loop |
| `test_static_analyzer.py` | 7 | Pylint integration and mapping, AST/Pylint de-duplication with severity merge, Radon metrics, quality-score formula |
| `test_llm_engine.py` | 12 | JSON extraction (fences, prose, trailing commas), schema coercion, status checks, request payload (format/options), retries, connection errors, malformed-JSON recovery, prompt-injection delimiters |
| `test_ai_debugger.py` | 12 | modes (static / llm_only / hybrid), fallback without LLM, syntax repair loop, repair cap, verified-only-when-tests-pass, no-changes, unparseable output, hallucinated-line filtering, interface-change note |
| `test_validator.py` | 12 | input validation, upload decoding, expression safety filter, pytest rendering (and executing rendered tests on trusted code), sandbox command flags, output parsing, validator outcomes |
| `test_database.py` | 4 | save/get/list, idempotent save, search/status/date filters, delete, statistics |
| `test_optimizer_comparator.py` | 11 | optimisation rules incl. memory rules (and no false alarms on idiomatic code), heuristic time and space Big-O (incl. loops inside functions), invalid code, diff counts, HTML escaping, JSON and PDF reports |
| `test_evaluation.py` | 3 | dataset integrity and dev/eval separation, detection metrics, summarisation with unmeasured repairs |
| `test_benchmark_runner.py` | 6 | dataset path resolution, broken checkpoint lines, trial run leaves `summary.json` untouched, `--resume` reuses saved rows, unknown methods rejected, merging earlier results, scripts run from another folder (ModuleNotFoundError regression) |
| `test_sandbox_docker.py` | 4 | **real container**: tests run, network blocked, non-root + read-only FS, infinite loop stopped |

## 2. Static checks of the project's own code
`python -m pylint core utils database evaluation views datasets app.py config.py --disable=C,R`
→ no errors or warnings (5 unused-argument warnings remain in test doubles under `tests/`, by design).

## 3. Manual / end-to-end UI testing
Performed with Playwright (headless Chromium) against `streamlit run app.py`, using the **mock Ollama server**
(`tests/mock_ollama_server.py`, canned answers) and the real Docker sandbox:

| Scenario | Result |
|---|---|
| All 9 pages load without Streamlit exceptions or browser errors | Pass |
| Load sample S04 → Analyse (hybrid) → issues, diff, metrics tabs render | Pass |
| Test generator: Generate with AI → table → Run tests in sandbox | Pass |
| Debugger with *Validate with my tests* → status **verified**, Tests tab shows results and disclaimer | Pass |
| Report tab → PDF download | Pass |
| Optimizer analysis, assistant quick question, history view | Pass |
| Optimizer after phase 11: memory suggestions and heuristic space card render (2026-11-26) | Pass |
| Ollama offline → sidebar shows "LLM offline" (fallback logic itself is covered by unit tests) | Pass |
| Docker unavailable → sidebar shows "Static-only mode" (before the image was built) | Pass |

### Setup self-check
`python check_setup.py` (2026-11-26, Linux): with Ollama absent it reports `[FAIL] Ollama server` with a fix hint,
as intended; with the mock server and real Docker it reports 0 failures, including fixed code passing and buggy code
failing in the sandbox and the hybrid pipeline reaching **verified**. Against a real model: not run yet.

## 4. Not yet tested
- Real LLM inference with Ollama (no model available in the development environment). The LLM path was tested with
  mocked HTTP responses, a scripted LLM and the mock server only.
- Windows and macOS installations; Docker Desktop on Windows (path mounting).
- Accessibility audit with a screen reader.
- Load/performance tests with very large files (inputs are capped at 800 lines by default).

## 5. Bugs found and fixed during testing
1. `core/test_generator.py` was collected by pytest as a test module → added `pytest.ini` with `testpaths = tests`.
2. Merging AST and Pylint findings kept the lower severity (AST *info* over Pylint *warning* for unused variables)
   → merge now keeps the more severe rating (regression test added). The static benchmark was re-run after this fix.
3. A dataset test value exceeded Python's int-to-string limit (`len(str(2000!))`) → test call changed.
4. Pylint flagged an unnecessary `except ...: raise`, protected-member access and dataclass-field access → refactored.
5. Four dataset examples had a single test, so their held-out test equalled their validation test (leakage) →
   each now has at least two tests, the builder refuses examples with fewer than two, and a test asserts that
   validation and held-out calls never overlap. The static benchmark was re-run on the rebuilt dataset.
6. The heuristic time estimate ignored loops inside functions (it stopped at function boundaries), so most real
   code showed O(1) → every function body is now measured; regression test added (2026-11-26).
7. A trial benchmark run (`--split dev --limit 3`) overwrote the main `summary.json` → restored from the timestamped
   copy, and trial runs now write `summary_trial.json` instead; test added (2026-11-26).
