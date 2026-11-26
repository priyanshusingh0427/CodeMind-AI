# System Architecture and Design Diagrams

All diagrams use Mermaid (rendered by GitHub, VS Code "Markdown Preview Mermaid Support", or <https://mermaid.live>).

## 1. Layered architecture

```mermaid
flowchart TB
    subgraph Presentation["Presentation layer (views/)"]
        P1[Dashboard] & P2[Debugger] & P3[Optimizer] & P4[Test generator] & P5[Assistant]
        P6[Analytics] & P7[History] & P8[Settings] & P9[About]
    end
    subgraph Logic["Business logic (core/)"]
        C1[syntax_checker] --> C2[static_analyzer]
        C3[complexity_analyzer]
        C4[ai_debugger pipeline]
        C5[optimizer] & C6[code_comparator] & C7[test_generator] & C8[test_validator]
    end
    subgraph AI["AI inference"]
        L1[llm_engine.OllamaClient] --> L2[(Ollama server + Qwen2.5-Coder)]
    end
    subgraph Iso["Isolated validation"]
        S1[sandbox.DockerSandbox] --> S2[(Docker container: pytest runner)]
    end
    subgraph Data["Data (database/)"]
        D1[operations] --> D2[(SQLite)]
    end
    subgraph Util["utils/"]
        U1[validators - Pydantic] & U2[prompts] & U3[logger] & U4[report_generator]
    end
    Presentation --> Logic
    C4 --> C2 & C3 & L1 & C8
    C8 --> S1
    Presentation --> D1
    Presentation --> U4
```

**Key decisions**
- *Single pipeline, three modes.* `AIDebugger.debug(mode=...)` implements Baseline 1 (`static`), Baseline 2
  (`llm_only`) and the proposed method (`hybrid`), so the evaluation compares like with like.
- *Protocols for external systems.* The debugger depends on an `LLMClient` protocol and a `SandboxLike` protocol,
  so tests inject a scripted LLM and a fake sandbox; no network or Docker is needed for unit tests.
- *Confirmed vs AI-inferred.* Every `Issue` carries `source` (ast / pylint / llm) and `confidence`
  (confirmed / heuristic / ai_inferred). The UI and reports never mix them.
- *Fail safe.* Ollama offline → static mode; Docker missing → no execution; malformed JSON → re-ask, then fall back.

## 2. Pipeline (proposed hybrid method)

```mermaid
flowchart LR
    A[Code input] --> B{Valid input?}
    B -- no --> X[Show validation error]
    B -- yes --> C[AST + symtable] --> D[Pylint] --> E[Radon]
    E --> F[Prompt: numbered code + confirmed findings + intended behaviour]
    F --> G[Ollama JSON] --> H[Pydantic schema]
    H --> I{Syntax OK?}
    I -- no --> R
    I -- yes --> J{New static errors?}
    J -- yes --> R
    J -- no --> K{Tests + sandbox?}
    K -- no --> U[Status: unverified]
    K -- yes --> L{All tests pass?}
    L -- yes --> V[Status: verified]
    L -- no --> R{attempt < N?}
    R -- yes --> F2[Repair prompt with failure details] --> G
    R -- no --> W[Status: failed_validation / invalid_syntax]
    U & V & W --> M[difflib diff + metrics after] --> N[(SQLite)] --> O[Dashboard / reports]
```

## 3. Data Flow Diagram – Level 0 (context)

```mermaid
flowchart LR
    User((Student / Developer)) -- Python code, intended behaviour, tests, settings --> S[CodeMind AI]
    S -- issues, corrected code, diff, metrics, reports --> User
    S -- prompts --> O[(Ollama LLM)]
    O -- JSON responses --> S
    S -- code + tests --> D[(Docker sandbox)]
    D -- test results --> S
    S <-- sessions --> DB[(SQLite history)]
```

## 4. Data Flow Diagram – Level 1

```mermaid
flowchart TB
    U((User)) --> P1[1.0 Accept & validate input]
    P1 --> P2[2.0 Static analysis<br/>AST, Pylint]
    P1 --> P3[3.0 Complexity metrics<br/>Radon]
    P2 --> P4[4.0 Build prompt]
    P3 --> P4
    P4 --> P5[5.0 LLM correction]
    P5 <--> LLM[(Ollama)]
    P5 --> P6[6.0 Verify correction<br/>syntax, static, tests]
    P6 <--> SB[(Sandbox)]
    P6 -- failure --> P5
    P6 --> P7[7.0 Compare & score]
    P7 --> P8[8.0 Store session]
    P8 <--> DB[(D1: debug_sessions)]
    P7 --> P9[9.0 Present results & reports]
    P9 --> U
```

## 5. UML use case diagram

```mermaid
flowchart LR
    actor((User))
    subgraph SYS["CodeMind AI"]
        UC1([Enter / upload / load sample code])
        UC2([Analyse & debug code])
        UC3([View issues: confirmed vs AI])
        UC4([Review corrected code & diff])
        UC5([Optimise code])
        UC6([Generate & edit tests])
        UC7([Run tests in sandbox])
        UC8([Chat with AI assistant])
        UC9([View analytics])
        UC10([Search / view / delete history])
        UC11([Download PDF / JSON report])
        UC12([Configure LLM, sandbox, privacy])
    end
    actor --- UC1 & UC2 & UC5 & UC6 & UC8 & UC9 & UC10 & UC11 & UC12
    UC2 -. includes .-> UC3
    UC2 -. includes .-> UC4
    UC6 -. extends .-> UC7
    Ollama((Ollama)) --- UC2 & UC5 & UC6 & UC8
    Docker((Docker)) --- UC7
```

## 6. UML class diagram (core types)

```mermaid
classDiagram
    class Settings {
      +ollama_host: str
      +model_name: str
      +temperature: float
      +max_repair_attempts: int
      +sandbox_enabled: bool
      +history_enabled: bool
      +with_overrides(**kw) Settings
    }
    class Issue {
      +line: int
      +category: Category
      +severity: Severity
      +message: str
      +source: str
      +confidence: Confidence
      +suggestion: str
    }
    class AIDebugResponse {
      +findings: list~AIFinding~
      +corrected_code: str
      +changes: list~str~
      +explanation: str
      +assumptions: list~str~
      +no_bugs_found: bool
    }
    class OllamaClient {
      +check_status() LLMStatus
      +chat(messages, json_mode) str
      +generate_json(prompt, schema) BaseModel
    }
    class AIDebugger {
      +debug(code, expected, test_code, mode) DebugResult
      -_run_llm()
      -_verify()
    }
    class DebugResult {
      +static_issues: list~Issue~
      +ai_issues: list~Issue~
      +corrected_code: str
      +repair_status: str
      +attempts: int
      +test_report: TestReport
      +to_dict() dict
    }
    class TestValidator {
      +validate(code, tests) TestReport
    }
    class DockerSandbox {
      +status() SandboxStatus
      +run_tests(code, tests) SandboxResult
      +build_command(dir, name) list
    }
    class ComplexityReport {
      +maintainability_index: float
      +average_complexity: float
    }
    class DebugSessionRecord {
      +session_id: str
      +original_code: str
      +corrected_code: str
      +repair_status: str
    }
    AIDebugger --> OllamaClient : uses (LLMClient protocol)
    AIDebugger --> TestValidator : uses
    TestValidator --> DockerSandbox : uses (SandboxLike protocol)
    AIDebugger --> DebugResult : creates
    DebugResult *-- Issue
    DebugResult *-- ComplexityReport
    OllamaClient ..> AIDebugResponse : validates into
    DebugResult ..> DebugSessionRecord : persisted as
```

## 7. Sequence diagram – "Analyse code" (hybrid mode)

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Debugger page
    participant D as AIDebugger
    participant S as Static analyzers
    participant L as OllamaClient
    participant V as TestValidator/Sandbox
    participant DB as SQLite
    U->>UI: Click "Analyse code"
    UI->>D: debug(code, behaviour, tests, "hybrid")
    D->>S: AST + Pylint + Radon
    S-->>D: issues, metrics
    D->>L: generate_json(debug prompt)
    L-->>D: AIDebugResponse
    loop until verified or N attempts
        D->>D: syntax check + static re-analysis
        D->>V: validate(candidate, tests)
        V-->>D: TestReport
        alt failed and attempts < N
            D->>L: generate_json(repair prompt + failures)
            L-->>D: new candidate
        end
    end
    D-->>UI: DebugResult
    UI->>DB: save_session(result)
    UI-->>U: issues, diff, explanation, metrics, report buttons
```

## 8. Activity diagram – repair loop

```mermaid
flowchart TD
    s([Start]) --> a[Receive LLM candidate]
    a --> b{Parses?}
    b -- no --> f[Record failure: syntax]
    b -- yes --> c{New serious static issues?}
    c -- yes --> f2[Record failure: static]
    c -- no --> d{Tests available & sandbox ready?}
    d -- no --> e1([Unverified])
    d -- yes --> t{All tests pass?}
    t -- yes --> e2([Verified])
    t -- no --> f3[Record failure: tests]
    f & f2 & f3 --> g{attempts < N?}
    g -- yes --> h[Send repair prompt] --> a
    g -- no --> e3([Failed validation])
```

## 9. ER diagram and database schema

```mermaid
erDiagram
    DEBUG_SESSIONS {
        int id PK
        string session_id UK "12-char hex"
        datetime created_at
        string title
        string mode "static | llm_only | hybrid"
        text original_code
        text corrected_code
        text expected_behavior
        json issues "confirmed static issues"
        json ai_issues "AI-inferred issues"
        json metrics_before
        json metrics_after
        float quality_before
        float quality_after
        json test_results
        text explanation
        json changes
        string model_name
        string repair_status
        int attempts
        int total_issues
        int critical_issues
        float duration
    }
```

A single denormalised table is deliberate: each session is written once and read as a whole; JSON columns keep the
schema stable while issue/metric structures evolve. Indexes: `session_id` (unique), `created_at`, `repair_status`.

## 10. Module responsibilities

| Module | Responsibility |
|---|---|
| `core/syntax_checker.py` | Parse; syntax/indentation errors; symtable-based undefined names, missing imports, unused locals; unreachable code; bad-practice patterns |
| `core/static_analyzer.py` | Pylint subprocess (`--from-stdin`, temp dir, timeout), message mapping, de-duplicated merge |
| `core/complexity_analyzer.py` | Radon raw/CC/MI/Halstead; quality score formula; grade |
| `core/llm_engine.py` | Ollama health check, chat, JSON mode, retries/backoff, tolerant JSON extraction |
| `core/ai_debugger.py` | Pipeline orchestration, modes, repair loop, AI finding filtering, interface check |
| `core/optimizer.py` | Rule-based patterns, heuristic Big-O, measured warnings, optional AI suggestions |
| `core/code_comparator.py` | difflib side-by-side rows, counts, inline character highlights, unified diff |
| `core/test_generator.py` | LLM tests → `TestCaseSpec`, expression safety filter, pytest rendering |
| `core/test_validator.py` | Pre-checks, calls sandbox, normalises outcome, disclaimer |
| `core/sandbox.py` | Hardened `docker run`, status checks, image build, output parsing |
| `database/*` | Engine/session scope, ORM model, CRUD + statistics |
| `utils/report_generator.py` | JSON & PDF reports with limitations and recommendations |
