# Methodology

## 1. Overview
CodeMind AI follows a **hybrid, self-verifying** approach: deterministic analysis first, generative repair
second, and independent verification last. The language model is treated as an untrusted, fallible component.

## 2. Static analysis

### 2.1 AST + symtable checks (`core/syntax_checker.py`)
1. `ast.parse` + `compile` → `SyntaxError`, `IndentationError`, `TabError` (severity *critical*); `SyntaxWarning`s are
   captured (e.g. `is` with a literal).
2. `symtable` resolves scopes. A referenced symbol that is *global* in a function scope (or unassigned at module
   level), is not assigned anywhere at module level, is not declared `global` and assigned elsewhere, and is not a
   builtin, is reported as **undefined** (*error*). Star imports disable this check.
3. If the undefined name is a known module alias (`np`, `pd`, `Counter`, …) or a standard-library module used as an
   attribute base (`math.sqrt`), it is reported as a **missing import** with the exact import line.
4. Function-scope symbols that are assigned but never referenced → **unused variable** (*info*).
5. A single AST walk flags: statements after `return/raise/break/continue` (**unreachable**), mutable default
   arguments, bare/silent `except`, `== None`, `== True`, division by literal zero, `str + number` literals,
   shadowed builtins, `while True` without exit (*heuristic*), `eval/exec`.

### 2.2 Pylint (`core/static_analyzer.py`)
Run as `python -m pylint --from-stdin --output-format=json` in an empty temporary directory with a timeout.
Messages are mapped to categories (e.g. `E0602 undefined-variable` → *undefined_variable*) and severities
(fatal→critical, error→error, warning→warning, refactor/convention→info).

### 2.3 Merging
Issues from AST and Pylint with the same `(line, category)` are merged; the merged issue lists both sources and
keeps the **more severe** rating.

## 3. Measured metrics and quality score
Radon provides LOC/SLOC, cyclomatic complexity per block (McCabe), maintainability index (MI, 0–100) and Halstead
metrics. The **quality score** is a documented, deterministic formula:

```
issue_penalty      = 25·critical + 10·error + 3·warning + min(10, 0.5·info)
complexity_penalty = 3 · (#functions with cyclomatic complexity > 10)
issue_score        = max(0, 100 − issue_penalty − complexity_penalty)
quality            = 0.7 · issue_score + 0.3 · MI          (clipped to 0–100)
if any critical issue: quality = min(quality, 20)
```
Grades: A ≥ 90, B ≥ 80, C ≥ 65, D ≥ 50, else F. The weights are design choices (not empirically fitted) and are
stated as such in the report.

## 4. LLM correction

### 4.1 Prompt design (`utils/prompts.py`)
- System prompt: role, *do not invent bugs*, *preserve interface*, *minimal change*, *JSON only*, and an explicit
  rule that text between `<<<UNTRUSTED_CODE_START>>>` / `<<<UNTRUSTED_CODE_END>>>` is data, not instructions.
- User prompt: line-numbered code, confirmed static findings, intended behaviour (quoted), and the JSON schema.
- Embedded delimiter tokens inside the submitted code are neutralised before wrapping.

### 4.2 Inference (`core/llm_engine.py`)
Ollama `/api/chat` with `format: "json"`, `temperature` (default 0.1), `num_ctx` (default 8192), request timeout,
and up to `max_retries` retries with exponential backoff. Replies are parsed tolerantly (code fences, prose
around JSON, trailing commas) and validated with Pydantic (`AIDebugResponse`), which also coerces severities
(`high`→`error`) and list fields. On malformed output the model is asked again for JSON only (bounded).

### 4.3 Guarding against hallucinations
- AI findings pointing to non-existent lines or without a description are discarded and counted.
- All AI findings are labelled `ai_inferred`.
- If the correction removes/renames top-level functions or classes, a note is added.
- A correction must not introduce new serious static errors (see verification).

## 5. Verification and bounded repair (Algorithm 1)

```
Algorithm 1: Hybrid self-verifying repair
Input : code C, intended behaviour B, tests T (optional), max attempts N
Output: candidate C*, status

S  ← StaticAnalysis(C)                       // AST + Pylint
R  ← LLM(Prompt(C, S, B))                     // JSON → schema
C* ← Clean(R.corrected_code) or C
k  ← 1
loop
    if not Parses(C*):                      f ← syntax error message
    else if SeriousIssues(C*) \ SeriousIssues(C) ≠ ∅:   f ← new static errors
    else if T given and Sandbox available:
         rep ← Sandbox.Run(C*, T)
         f ← (rep.failed or rep.errors) ? rep.failure_details : ∅
    else f ← ∅
    if f = ∅ or k = N: break
    k ← k + 1
    R  ← LLM(RepairPrompt(C, C*, f, B))
    C* ← Clean(R.corrected_code) or C*
end loop
status ← invalid_syntax | verified | failed_validation | no_changes | unverified
```

The loop is bounded by `N = max_repair_attempts` (default 3), so the worst-case number of LLM calls per program
is `N` (plus at most `max_retries` JSON re-asks per call).

## 6. Secure execution
Tests run only inside `codemind-sandbox` containers started with `--network none`, `--user 65534:65534`,
`--cpus`, `--memory`/`--memory-swap`, `--pids-limit 64`, `--read-only`, `--tmpfs /tmp:noexec,nosuid,size=16m`,
`--cap-drop ALL`, `--security-opt no-new-privileges`, `--ulimit fsize`, a read-only bind mount of a fresh temp
directory, an in-process `SIGALRM`, a host-side timeout followed by `docker kill`, and output truncation.
These properties are checked by `tests/test_sandbox_docker.py` (network blocked, non-root, read-only, timeout).

## 7. Optimisation analysis
Three clearly separated outputs: **measured** (Radon), **rule-based** (AST patterns such as `range(len(x))`,
append-only loops, string `+=` in loops, list membership in loops, manual sums, sorting inside loops, duplicate
blocks, un-memoised double recursion, missing docstrings), and **AI estimates**. A heuristic Big-O is derived
from maximum loop nesting depth, sorting and double recursion; it is labelled as a heuristic.

## 8. Evaluation protocol

### 8.1 Dataset
`datasets/benchmark.json`: 122 original single-function programs, each with exactly one bug, a reference fix,
intended behaviour, explanation, independent tests, and bug line numbers (derived with difflib). The builder
(`datasets/build_dataset.py`) computes expected values from the reference fix and **verifies** that the reference
passes all tests and the buggy version fails at least one.

| Category | Count |
|---|---|
| logical_error | 43 |
| potential_runtime_error | 13 |
| undefined_variable | 11 |
| type_issue | 11 |
| syntax_error | 10 |
| bad_practice | 9 |
| indentation_error | 8 |
| missing_import | 8 |
| unreachable_code | 5 |
| unused_variable | 4 |

**Leakage control.** Every 4th example is in the *dev* split (30) for prompt tuning; results are reported on the
*eval* split (92). Each example's tests are split into `validation_tests` (shown to the repair loop) and
`heldout_tests` (used only for scoring), so the proposed method is never scored on tests it saw.

### 8.2 Methods
- **Baseline 1 – static:** AST + Pylint, no repair.
- **Baseline 2 – LLM only:** one LLM call without static findings; no verification or repair.
- **Proposed – hybrid:** static findings in the prompt + verification on `validation_tests` + up to N repairs.

### 8.3 Metrics
Each method is run on the buggy program (label 1) and on its reference fix (label 0).
- *Predicted buggy* = a serious (critical/error/warning, non-style) static issue, a serious AI finding, or an
  LLM change to the code.
- Accuracy, precision, recall, F1, false-positive rate (scikit-learn, confusion matrix).
- Localisation accuracy: a serious issue within ±1 line of a true bug line.
- Repair rate: corrected program passes **all held-out tests** in the sandbox. Test pass rate: mean fraction.
- Average response time on the buggy program; mean change in average cyclomatic complexity and MI.

### 8.4 Results so far (measured)
Static baseline, eval split (92 buggy + 92 clean), Python 3.13, Pylint enabled, run 2026-11-25:
accuracy 0.690, precision 1.000, recall 0.380, F1 0.551, FPR 0.000, localisation 0.359, mean time 0.29 s.
Recall by category: syntax 1.00, missing import 1.00, unused variable 1.00, undefined variable 0.875,
unreachable 0.75, indentation 0.67, bad practice 0.29, runtime 0.20, type 0.00, logical 0.00.
LLM-only and hybrid: **not yet performed** (requires Ollama).

### 8.5 Threats to validity
- Programs are small and synthetic; results may not transfer to large real-world code (BugsInPy-style).
- Precision of 1.0 for the static baseline is partly by construction: the clean references are short, idiomatic
  functions. Real code would produce false positives.
- The definition of "predicted buggy" for LLM methods (any change) may overcount detection.
- The dataset author also wrote the tool; some bias in bug selection is possible.
- LLM results depend on model, quantisation, temperature and hardware; report them with the run metadata.
