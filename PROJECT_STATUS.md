# PROJECT STATUS – CodeMind AI

_Last updated: 2026-11-26_

## Summary
All phases (1–11) are implemented. The app runs end to end, 86 automated tests pass, the Docker sandbox was
verified with real containers, and the static-analysis baseline was benchmarked on the eval split.
**The LLM-based methods have not been evaluated yet**: they need a real Ollama model, which is not available in the
development environment. Everything needed for that run is ready (`check_setup.py`, `run_benchmark.py`).

## Phase checklist

| Phase | Status | Verification performed |
|---|---|---|
| 1. Structure & configuration | ✅ Done | Imports checked; settings overrides unit-tested |
| 2. Syntax, static, complexity analysis | ✅ Done | 22 unit tests |
| 3. Ollama integration & AI debugger | ✅ Done | 24 unit tests with mocked HTTP / scripted LLM; UI tested with mock server |
| 4. Optimizer & code comparison | ✅ Done | 8 unit tests; UI clicked through |
| 5. Test generation & isolated validation | ✅ Done | 12 unit tests + 4 real Docker tests (network blocked, non-root, read-only, timeout) |
| 6. SQLite history | ✅ Done | 4 unit tests (search, filters, delete); history page renders saved sessions |
| 7. Streamlit frontend (9 pages) | ✅ Done | Playwright run: all pages, debug → verified with sandbox tests, PDF download |
| 8. Analytics & reports | ✅ Done | PDF/JSON unit test; analytics page renders |
| 9. Dataset & evaluation | ✅ Done (partial results) | 122 examples verified by the builder; static baseline measured; LLM methods **not run** |
| 10. Tests, docs, delivery | ✅ Done | See docs/testing_report.md |
| 11. Laptop readiness & remaining features (2026-11-26) | ✅ Done | See below |

### Phase 11 (2026-11-26) – what was added
- **Fix for `ModuleNotFoundError: No module named 'evaluation'`:** scripts now add the project folder to the import
  path themselves; new root-level `run_benchmark.py` (benchmark + charts) and `check_setup.py` work from any folder.
  `.env` is always read from the project folder. Docs explain the nested `CodeMind-AI\CodeMind-AI` folder issue.
- **`check_setup.py`:** checks Python/venv, packages, SQLite, static analysis, Ollama (server, model, one real
  debugging call), Docker and the sandbox (fixed code passes, buggy code fails, full hybrid pipeline → verified).
  Verified here against the mock server and real Docker; **not yet run against a real model**.
- **Benchmark runner:** per-example checkpoint (`progress_*.jsonl`), `--resume`, ETA, methods run separately are
  merged, and only a full eval-split run updates `summary.json` (trial runs go to `summary_trial.json`; the
  Analytics page can show them, clearly labelled).
- **Optimizer:** memory-efficiency rules (list passed to `sum/any/all/min/max`, `len([...])`, `for x in list(...)`,
  `readlines()`, `+= [x]` in loops) and a heuristic auxiliary-space estimate shown next to the time estimate.
  Fixed a bug where loops inside functions were ignored by the heuristic time estimate (always O(1)).
- **`datasets/README.md`:** sources, licences, build/verification steps, split and test policy, QuixBugs/BugsInPy.

## Test results (actually executed)
- Python 3.13.18 (Linux, Docker running): `pytest` → **86 passed** (2026-11-26).
- Python 3.11.18 (`python:3.11-slim`, fresh `pip install -r requirements.txt`): **82 passed, 4 skipped** (the 4
  Docker tests skip because there is no Docker inside that container).
- `check_setup.py` with the mock Ollama server and real Docker: 0 failures (2026-11-26).
- Playwright smoke test of the Optimizer and Analytics pages after the changes: no exceptions.
- Pylint on project code (errors/warnings): clean.

## Measured benchmark results
Static baseline, eval split (92 buggy + 92 clean programs), 2026-11-25, Python 3.13, Pylint on:
accuracy 0.690 · precision 1.000 · recall 0.380 · F1 0.551 · FPR 0.000 · localisation 0.359 · 0.29 s/program.
Files: `evaluation/results/summary.json`, `summary.csv`, `details_20261125_183350.csv`, `*.html` charts.

| Method | Status |
|---|---|
| Static (Baseline 1) | Measured |
| LLM only (Baseline 2) | **Not yet performed** – needs Ollama |
| Hybrid (proposed) | **Not yet performed** – needs Ollama (+ Docker for repair scoring) |

## Known limitations / open items
1. On the laptop with Ollama (and Docker Desktop running): `python check_setup.py`, then
   `python run_benchmark.py --limit 10` (trial, to estimate time), then the main run `python run_benchmark.py`
   (use `--resume` if interrupted). Fill the results into `docs/research_paper.md` §V, `docs/project_report.md`
   ch. 27, README and `docs/resume_description.md`.
2. Test the installation on Windows and macOS and record the outcome in `docs/testing_report.md`.
3. QuixBugs conversion script exists (`datasets/prepare_quixbugs.py`) but the download was blocked in the
   development environment, so it has not been run. BugsInPy is documented only.
4. Replace the mock-LLM screenshots in `screenshots/` with screenshots taken with a real model.
5. Fill in your name, college, guide and roll number in `docs/synopsis.md`, `docs/project_report.md` and
   `docs/research_paper.md` (placeholders in square brackets).
6. Verify every reference in the literature review against the original source before submission.

## Next file to work on
No code is pending. Next step is the main benchmark run on the laptop (open item 1), then updating the
paper/report tables with the measured numbers.
