# Viva Questions and Answers (60)

## A. Project overview
1. **What is CodeMind AI?** An offline Python debugging system that combines static analysis with a local LLM and
   verifies AI corrections using syntax checks, static re-analysis and sandboxed tests.
2. **What problem does it solve?** Linters can't fix logic errors; AI chatbots can be wrong, need internet, and are
   unverified. CodeMind AI gives verified AI help offline for free.
3. **What is "hybrid" here?** Deterministic analysis (AST, Pylint, Radon) + generative AI (LLM) in one pipeline,
   where the analysis results are given to the LLM as context.
4. **What does "self-verifying" mean?** Every AI correction is checked automatically before it is trusted, and if a
   check fails the failure is fed back to the LLM for another attempt, at most N times.
5. **Why Python?** Most common language for students and AI/ML; rich tooling (`ast`, `symtable`, Pylint, Radon).
6. **Who are the users?** Students learning Python and developers who want quick, private debugging help.
7. **What is your main research contribution?** A resource-light, offline integration of static analysis, a local
   LLM and isolated test validation with bounded repair, plus a leakage-aware benchmark and honest comparison. I don't
   claim the repair loop idea is new – self-debugging with execution feedback exists in the literature.

## B. Static analysis
8. **What is an AST?** Abstract Syntax Tree – a tree representation of the program's syntactic structure produced by
   `ast.parse`, without executing it.
9. **How do you detect undefined variables?** With `symtable`: a symbol referenced in a function that resolves to
   global scope but is never assigned at module level, declared global elsewhere, or a builtin is undefined.
10. **Why `symtable` instead of walking Name nodes?** It applies Python's real scoping rules (locals, enclosing,
    globals, comprehensions), avoiding false positives for closures and comprehensions.
11. **How do you detect missing imports?** If an undefined name is a standard-library module used as `name.attr`
    or a known alias like `np`/`Counter`, the suggestion is the exact import line.
12. **How is unreachable code detected?** In any statement list, a statement following `return`, `raise`,
    `break` or `continue` is reported.
13. **What does Pylint add?** Hundreds of mature checks (e.g. used-before-assignment, no-member, unused-import),
    mapped to our categories and merged with the AST findings.
14. **How do you avoid duplicate issues?** Merge by (line, category); keep both sources and the higher severity.
15. **Is the user's code executed during static analysis?** No. Pylint runs in a subprocess on stdin in an empty
    temp directory; it parses code but does not run it.

## C. Metrics
16. **What is cyclomatic complexity?** McCabe's metric: number of linearly independent paths ≈ decision points + 1.
    Above 10 is usually considered complex.
17. **What is the maintainability index?** A composite of Halstead volume, cyclomatic complexity and lines of code,
    scaled 0–100 by Radon; higher is more maintainable.
18. **What are Halstead metrics?** Measures from counts of operators and operands: volume, difficulty, effort.
19. **How is your quality score calculated?** 0.7 × (100 − penalties for issues and complex functions) + 0.3 × MI,
    capped at 20 if there is a syntax error. Weights are documented design choices, not learned.
20. **Why distinguish measured metrics from AI estimates?** Radon values are computed; the LLM's Big-O is a guess.
    Mixing them would mislead users.

## D. LLM and prompting
21. **Which model and why?** Qwen2.5-Coder 1.5B by default via Ollama: free, code-specialised, runs on CPU with 8 GB
    RAM. 3B/7B can be selected for better quality.
22. **What is Ollama?** A local runtime that downloads and serves open LLMs through a REST API on localhost:11434.
23. **How do you get structured output?** Ollama JSON mode + a schema in the prompt + Pydantic validation and
    coercion; malformed replies trigger a bounded re-ask.
24. **What if the model returns invalid JSON?** We extract JSON from fences/prose, remove trailing commas, and if
    that fails ask again; after the retry limit the app falls back to static results.
25. **Why temperature 0.1?** Debugging needs deterministic, conservative answers rather than creativity.
26. **What is `num_ctx`?** The context window in tokens; default 8192 to fit code, findings and schema.
27. **How do you prevent hallucinated bugs?** The prompt forbids inventing bugs; findings for non-existent lines are
    dropped; AI findings are labelled; corrections must pass verification.
28. **What is prompt injection and how do you mitigate it?** Text inside processed content that tries to give the
    model instructions. Code is wrapped in unique delimiters, embedded delimiters are neutralised, and the system
    prompt says content inside is data only. It reduces but cannot fully eliminate the risk – that's why output is
    verified and never auto-executed on the host.
29. **What happens without Ollama?** The status shows offline; debugging runs in static-analysis mode; AI pages show
    a clear message.

## E. Verification, testing and sandbox
30. **What are the verification steps?** Schema → parses? → no new serious static issues? → tests pass in sandbox?
31. **Why limit repair attempts?** To bound time and cost and avoid endless loops; default 3, configurable 1–5.
32. **Why Docker?** It gives OS-level isolation that can be locked down: no network, non-root, resource limits,
    read-only filesystem.
33. **Which restrictions are used?** `--network none`, `--user 65534`, `--cpus`, `--memory`, `--pids-limit 64`,
    `--read-only`, small `noexec` tmpfs, `--cap-drop ALL`, `no-new-privileges`, read-only temp mount, timeout,
    output truncation.
34. **How did you verify the sandbox?** Integration tests: network connection fails, uid ≠ 0, writing to `/work`
    fails, infinite loop is stopped – all four pass.
35. **What if Docker isn't available?** The app never executes code; it stays in static-analysis mode.
36. **Do passing tests prove correctness?** No – they show correct behaviour only for the tested inputs. The app
    says this explicitly.
37. **How are tests generated?** The LLM proposes call/expected pairs in four categories; the user reviews them in a
    table; they are rendered into pytest; unsafe expressions are rejected.
38. **Why keep benchmark tests separate from LLM tests?** LLM tests may encode the model's own misunderstanding;
    using them to judge the model would be circular.

## F. Dataset and evaluation
39. **Describe your dataset.** 122 original single-function programs with one bug each across 10 categories, each
    with a reference fix, intended behaviour, explanation and tests.
40. **How do you know the dataset is correct?** The builder computes expected values from the reference fix and
    checks that the reference passes all tests and the buggy version fails at least one.
41. **What is benchmark leakage and how do you avoid it?** Tuning on the data you report on. We use a dev split (30)
    for tuning and an eval split (92) for reporting, and split each example's tests into validation (seen by the
    repair loop) and held-out (scoring only).
42. **What are the three compared methods?** Static only; LLM only (single call, no static context, no
    verification); hybrid (proposed).
43. **How do you compute precision and recall?** Each method analyses buggy programs (positives) and their fixes
    (negatives); predicted-buggy is any serious finding or an LLM code change; scikit-learn computes the metrics.
44. **What is the false-positive rate?** FP / (FP + TN): how often correct programs are flagged as buggy.
45. **What did you measure so far?** Static: precision 1.000, recall 0.380, F1 0.551, FPR 0.000; it found all
    syntax errors and missing imports but no logical or type errors.
46. **Why is static precision 1.0?** The clean references are short idiomatic functions; real code would trigger
    false positives. I don't generalise it.
47. **Where are the LLM results?** Not yet run – they require a machine with Ollama. I will not report numbers I
    haven't measured. The script and protocol are ready.
48. **What is localisation accuracy?** Whether a serious issue was reported within ±1 line of the true bug line.
49. **What is repair rate?** Share of buggy programs whose corrected version passes all held-out tests in the sandbox.

## G. Implementation and design
50. **Explain your architecture layers.** `views` (UI) → `core` (logic, AI, validation) → `database` → `utils`;
    the core has no Streamlit code so the benchmark reuses it.
51. **Why Streamlit?** Full UI in Python, fast to build, no JavaScript – as required.
52. **Why SQLite and SQLAlchemy?** Zero-configuration local database; the ORM keeps the code portable and safe from
    SQL injection.
53. **Why Pydantic?** Declarative validation and coercion of untrusted LLM JSON into typed objects.
54. **How is the diff produced?** `difflib.SequenceMatcher` opcodes → rows labelled equal/added/removed/modified;
    character-level highlights for modified lines; HTML escaped.
55. **How do you test code that calls an LLM?** Protocol-based dependency injection: a scripted fake LLM in unit
    tests, mocked HTTP for the client, and a mock Ollama server for UI tests.
56. **How many tests do you have?** 86 automated tests; all pass on Python 3.13, and 82 non-Docker tests pass on
    Python 3.11.
57. **How is user privacy handled?** Everything runs locally; usage statistics are disabled; history can be turned
    off and deleted.
58. **How is configuration managed?** A frozen `Settings` dataclass from environment/.env, with runtime overrides
    saved by the Settings page.

## H. Limitations and future work
59. **Main limitations?** Small models can be wrong and slow; static analysis misses logic bugs; the dataset is
    synthetic and small; single-file analysis only.
60. **Future scope?** Complete LLM experiments with several model sizes, evaluate on QuixBugs/BugsInPy, multi-file
    support, VS Code extension, Hypothesis-based tests, and fine-tuning on the dev split.
