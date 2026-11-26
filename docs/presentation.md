# Presentation Content (18 slides)

**Slide 1 – Title**
CodeMind AI: AI-Powered Python Code Debugger and Optimization System · [Name], [Roll No.] · Guide: [Name] · [College]

**Slide 2 – The problem**
- Debugging takes a big share of programming time; beginners struggle most.
- Linters are precise but don't know intent. AI chatbots know intent but can be wrong, need internet, cost money.
- Goal: combine both, and *check* the AI.

**Slide 3 – Objectives**
Detect · Explain · Correct · Optimise · Validate · Measure – offline, free, on an 8–16 GB laptop.

**Slide 4 – Existing systems vs proposed**
| Existing | CodeMind AI |
|---|---|
| Linters: no fixes for logic | AI correction with explanations |
| Chatbots: unverified, online | Verified (syntax, static, tests), offline |
| Separate tools | One pipeline + dashboard + reports |

**Slide 5 – Architecture** (show the pipeline diagram from README)

**Slide 6 – Static analysis**
AST + symtable (undefined names, missing imports, unreachable code, unused vars, bad practices) + Pylint, merged.
Confirmed findings, never executes code.

**Slide 7 – LLM integration**
Ollama + Qwen2.5-Coder 1.5B; JSON schema; temperature 0.1; retries; tolerant parsing; untrusted-code delimiters
against prompt injection.

**Slide 8 – Self-verifying repair loop**
Schema → syntax → static re-analysis → sandboxed tests → repair with feedback, max 3 attempts.
Status: verified / unverified / failed.

**Slide 9 – Secure sandbox**
Docker: no network, non-root, CPU/memory/PID limits, read-only FS, timeout, output limit. No Docker → no execution.
(Show the 4 passing security tests.)

**Slide 10 – Optimiser and metrics**
Measured (Radon CC, MI, Halstead) · rule-based (range(len), string += in loop, membership in list…) · AI estimates.
Quality score formula on one line.

**Slide 11 – UI tour** (screenshots: dashboard, debugger diff, analytics, history)

**Slide 12 – Test generation**
AI proposes normal/edge/boundary/invalid tests → user edits → pytest file → sandbox run. Benchmark tests separate.

**Slide 13 – Dataset**
122 original programs, 10 categories, verified automatically; 30 dev / 92 eval; validation vs held-out tests.

**Slide 14 – Evaluation design**
Static vs LLM-only vs Hybrid; precision, recall, F1, FPR, repair rate, pass rate, time.

**Slide 15 – Results (measured)**
Static: precision 1.00, recall 0.38, F1 0.55, FPR 0.00; 0 of 32 logical bugs found. LLM-only and hybrid: [fill after
running]. Chart from `evaluation/results/comparison_metrics.html`.

**Slide 16 – Testing**
86 automated tests pass (Python 3.13), 82 on Python 3.11 (Docker tests skipped there); Playwright end-to-end flow; pylint-clean core.

**Slide 17 – Limitations and future scope**
Small models can be wrong; synthetic dataset; tests ≠ proof. Future: QuixBugs/BugsInPy, VS Code extension,
multi-file projects, Hypothesis-based tests.

**Slide 18 – Conclusion & demo**
Hybrid + verification + isolation = trustworthy AI help, offline. Live demo → Q&A.
