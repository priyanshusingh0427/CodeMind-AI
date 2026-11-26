# User Manual

Start the app with `streamlit run app.py`. The **sidebar** lists the pages and shows three status pills:
LLM (online/offline), Sandbox (ready / static-only) and History (on/off).

## 1. Home Dashboard
Overview cards (AI engine, sandbox, sessions, issues, verified repairs, average time), quick-start links, the
pipeline at a glance and your five most recent sessions.

## 2. AI Code Debugger
1. **Add code** – type/paste in the editor, **Upload a .py file**, or **Load sample**. **Clear / reset** empties everything.
2. **Intended behaviour** (optional) – one sentence such as "Return the sum of 1..n inclusive". It greatly
   improves detection of logical errors.
3. **Choose a mode**
   - *Hybrid* (recommended): static analysis + AI correction + verification + repair loop.
   - *Static analysis only*: fast, deterministic, no AI.
   - *AI only*: one AI call without static context or verification (used as a research baseline).
4. Optional: tick **Validate with my tests (sandbox)** – available after you created tests on the Test Case
   Generator page and Docker is ready.
5. Click **Analyse code**. A status box shows progress.

**Results**
- Summary cards: total issues (confirmed vs AI-inferred), critical/errors, quality score before → after, repair
  status, time.
- **Issues** – left: confirmed (AST/Pylint); right: AI-inferred. Each shows line, severity, category, source and
  a suggestion. Issues also appear as markers in the editor gutter.
- **Correction & diff** – side-by-side diff (green = added, red = removed, ~ = modified, character-level
  highlights), counts, the corrected code with a copy button, and **Download corrected .py**.
- **Explanation** – AI root-cause explanation, changes, assumptions and AI optimisation ideas.
- **Metrics** – before/after bar chart (quality, MI, complexity, LOC), per-function complexity and the score formula.
- **Tests** – sandbox results when tests were used.
- **Report** – download PDF or JSON.

**Repair status meanings**: *verified* (passed your tests), *unverified* (valid Python, no tests run),
*no changes*, *failed validation*, *invalid syntax*, *AI unavailable*, *static analysis only*.

## 3. Code Optimizer
Uses the same code. Toggle AI suggestions, click **Analyse optimisations**. You get measured metrics (Radon),
a per-function complexity chart with the threshold of 10, rule-based suggestions with line numbers, the heuristic
Big-O, AI estimates (if Ollama runs) and, when the AI proposes an optimised version, a diff and download.

## 4. Test Case Generator
1. Choose the number of tests and click **Generate with AI** (or **Manual template** without Ollama).
2. Review/edit the table: `call` is a Python expression (e.g. `add(2, 3)`), `expected` a Python literal
   (e.g. `5`), or `expects_exception` (e.g. `ValueError`) for invalid-input tests. Add or delete rows.
3. Click **Build pytest file from table**. You can edit the generated file directly and download it.
4. With Docker ready, choose *Original code* or *AI-corrected code* and click **Run tests**.

AI tests are *candidates*; check expected values yourself. Unsafe expressions (`open`, `eval`, dunder access…) are rejected.

## 5. AI Code Assistant
Ask about the current code, or click a quick question ("Why is my code not working?", "What is the estimated time
complexity?" …). The assistant sees the code with line numbers and the static findings. **Clear conversation**
resets the chat.

## 6. Analytics Dashboard
- *Current session*: severity donut, issues by category and confidence, before/after radar, time per stage.
- *History trends*: quality over time, repair outcomes, duration histogram.
- *Benchmark results*: table and chart from `evaluation/results/summary.json` (only measured results).

## 7. Debugging History
Search by text or session id, filter by status and date. Click a row to see issues, diff, explanation and tests;
**Load into editor**, download **JSON/PDF report** or **Delete session**. *Danger zone* deletes everything.

## 8. Settings
AI engine (enable, host, model, temperature, timeout, retries, context length, **Test connection**), maximum
repair attempts, sandbox (enable, timeout, memory, CPU, **Build sandbox image**, view the exact `docker run`
command), history storage toggle. Click **Save settings**; **Reset to defaults** restores `.env` values.

## 9. About Project
Architecture diagram, research question, compared approaches, stack and limitations.

## Tips
- Keep code to one module with functions; the test generator targets top-level functions.
- Prefer small models for speed; switch to 3b/7b for harder bugs.
- Always read AI explanations critically – they are suggestions, not facts.
