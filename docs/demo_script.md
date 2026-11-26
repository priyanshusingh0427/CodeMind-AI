# Project Demonstration Script (~10 minutes)

**Before the demo:** start Ollama (`ollama list` shows the model), start Docker Desktop, build the sandbox image,
run `streamlit run app.py`, and check that the sidebar shows *LLM: qwen2.5-coder* and *Sandbox ready*.
Have `python run_benchmark.py` results already generated. Backup plan if the model is slow: run the
mock server (`python tests/mock_ollama_server.py`) and say clearly that it returns canned answers.

| Time | Action | What to say |
|---|---|---|
| 0:00 | Home Dashboard | "CodeMind AI debugs Python offline: static analysis, a local LLM, and verification. Status pills show the model and sandbox are ready." |
| 0:45 | Debugger → Load sample **S01 Undefined variable** → Static mode → Analyse | "Static analysis alone finds `totl` with the exact line – confirmed, deterministic, in milliseconds." |
| 1:45 | Load **S04 Off-by-one** → Static mode | "No issue found – static tools can't know I wanted 1..n inclusive. This is the gap." |
| 2:15 | Same sample, **Hybrid** mode | "Now the intended behaviour and static findings go to the local model." Show Issues tab: confirmed left, AI-inferred right. |
| 3:15 | Correction & diff tab | "Green/red side-by-side diff, character-level highlight, copy and download. Status *unverified* – valid Python but no tests yet." |
| 4:00 | Test Case Generator → Generate with AI → edit one row → Build → Run tests (original code) | "AI proposes tests; I review them. They run only inside the Docker sandbox – no network, non-root, limits. The original fails." |
| 5:15 | Back to Debugger → tick *Validate with my tests* → Analyse | "The correction is now tested; if it failed, the failure would be sent back for another attempt, up to three. Status *verified* – with the honest note that tests don't prove correctness." |
| 6:15 | Metrics + Report tabs → download PDF | "Measured before/after metrics and the documented score formula; PDF and JSON reports with limitations." |
| 7:00 | Code Optimizer on **S10** | "Measured metrics, rule-based findings like `range(len())` and string `+=` in a loop, heuristic Big-O, and AI suggestions labelled as estimates." |
| 8:00 | AI Assistant → "What is the estimated time complexity?" | "Chat with the code in context." |
| 8:30 | Analytics → Benchmark results | "On 92 evaluation programs, static analysis has perfect precision but recall 0.38 and finds no logical bugs." (Add LLM numbers once measured.) |
| 9:15 | History → search → open a session | "Everything is stored locally and can be disabled or deleted." |
| 9:40 | Settings | "Model, temperature, retries, repair limit, sandbox limits, privacy – all configurable." |
| 10:00 | Close | "Hybrid analysis, verified AI, isolated execution, offline and free." |
