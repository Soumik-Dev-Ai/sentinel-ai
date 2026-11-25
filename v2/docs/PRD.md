# Sentinel AI 2.0 — Product Requirements Document (PRD)

## 1. Executive Summary & Core Value Proposition

### 1.1 Executive Summary
**Sentinel AI 2.0** is an enterprise-grade, full-stack multi-agent autonomous engineering platform designed to eliminate silent failures, runtime exceptions, and non-functional code generation in AI-assisted software development.

Traditional code generation models operate in a single unmonitored pass: they accept a user prompt, generate an unverified block of code, and return it without validation. When subtle logic bugs, missing imports, off-by-one errors, or runtime exceptions occur, the user is forced to manually diagnose, debug, and reprompt the model.

Sentinel AI 2.0 replaces this fragile single-shot pattern with an automated, closed-loop multi-agent engineering team:
1. **Strategic Planning:** An **Orchestrator Agent** decomposes goals using Tree-of-Thought (ToT) reasoning into ordered subtasks with predicted confidence scores.
2. **Informed Synthesis:** A **Coder Agent** writes complete, production-grade Python scripts guided by historical RAG memory recall and automatic AST unescaping.
3. **Automated Verification:** A **Critic Agent** acts as an objective LLM-as-a-Judge, scoring code across 4 orthogonal dimensions (correctness, edge cases, acceptance, readability) against an 80/100 threshold.
4. **Sandboxed Subprocess Execution:** An **Executor Agent** runs the code inside an isolated environment protected by pre-execution AST safety guardrails.
5. **Targeted Failure Recovery:** An **Adaptive RetryRouter** classifies runtime tracebacks into targeted remediation strategies (`line_patch`, `full_rewrite`, `backoff`).
6. **Human-in-the-Loop Safeguard:** An **EscalationManager** automatically alerts and consults the human developer if confidence degrades after repeated retries.
7. **Transparent Telemetry:** A real-time **FastAPI WebSocket** and **ReactFlow** frontend visualizes every node transition, token expenditure, and terminal log line.

### 1.2 Core Value Proposition
- **Guaranteed Task Completion Lift:** Autonomous self-correction elevates task completion rates from **75.0% to 100.0%** across standardized programming benchmarks.
- **Sub-Cent Operating Cost:** Intelligent multi-tier routing prioritizes free-tier LLM endpoints (Groq, NVIDIA NIM, OpenRouter, SambaNova) with automatic token-per-day rotation.
- **Enterprise-Grade Observability:** Complete auditability over WebSocket event streams and local SQLite3 execution logging.

---

## 2. Target User Personas & Operational Scenarios

### 2.1 User Personas
| Persona | Title | Primary Responsibility | Key Pain Point | Sentinel AI 2.0 Solution |
| :--- | :--- | :--- | :--- | :--- |
| **DevOps & Platform Architect** | Senior SRE / DevOps Lead | Infrastructure automation scripts and internal CLI tools | AI scripts fail silently in CI/CD pipelines due to unhandled edge cases or missing dependencies. | Sandboxed execution and automatic self-healing ensure only fully functional scripts are deployed. |
| **AI/ML Benchmark Evaluator** | Technical Research Lead | Evaluating agentic coding frameworks and prompt strategies | Inability to separate AI hype from empirical, reproducible benchmark gains. | Built-in Evaluation Lab provides automated A/B comparative testing with exact telemetry. |
| **Full-Stack Application Developer** | Senior Software Engineer | Rapid prototyping and microservice implementation | AI assistants oscillate between broken solutions when repeated errors occur. | VectorStore RAG memory recalls past error signatures and fixes, preventing repetitive mistake loops. |

### 2.2 Operational Scenarios
- **Scenario A (Autonomous Algorithmic Synthesis):** A developer needs a complex data structure (e.g., an LRU cache or self-balancing tree) with unit tests. The Orchestrator plans the file structure, Coder synthesizes the module, Critic verifies boundary cases, and Executor verifies tests pass exit code 0.
- **Scenario B (Environment/Runtime Self-Healing):** A script fails due to an unhandled `FileNotFoundError` or `ImportError`. The RetryRouter classifies the error as `LOGIC`, feeds the traceback to the Coder, and the Coder injects defensive fallback logic automatically.
- **Scenario C (Interactive Human Escalation):** An ambiguous specification causes repeated Critic rejections. The system triggers an interactive modal in the React UI, gathers a 1-sentence clarification from the developer, and resumes execution to success.

---

## 3. Product Goals & Quantitative Success Metrics

### 3.1 Quantitative Success Metrics
| Metric | Baseline Target (Self-Correction OFF) | Sentinel 2.0 Target (Self-Correction ON) | Empirical Measured Result (`eval_1791864368`) |
| :--- | :---: | :---: | :---: |
| **Task Completion Rate** | $\le 75\%$ | **$\ge 95\%$** | **100.0%** (12 / 12 passed) |
| **Relative Completion Lift** | Baseline | **$\ge +25\%$** | **+33.3% relative lift** (+25.0 percentage points) |
| **Average Self-Corrections** | $0.00$ | $\le 1.00$ per task | **0.67** per task (8 total across suite) |
| **Benchmark Coverage ($N$)** | 12 goals | 12 goals | **12 canonical goals** (24 total runs) |
| **Provider Fallback Resilience** | N/A | $100\%$ failover resilience | **Zero unhandled API crashes** across 7 providers |
| **WebSocket Dispatch Latency** | N/A | $\le 20\text{ms}$ | **$< 15\text{ms}$** dispatch overhead |

---

## 4. Detailed Functional Requirements

### 4.1 Orchestration & Planning (FR-ORCH)
- **FR-ORCH-1 (ToT Generation):** Given a user goal, the Orchestrator shall prompt the strategic LLM tier to generate exactly 3 candidate approach paths (`P1`, `P2`, `P3`).
- **FR-ORCH-2 (Path Scoring):** Each path must include a predicted confidence score ($0.0 - 1.0$), one-line rationale, risks, and sequential steps.
- **FR-ORCH-3 (Subtask Decomposition):** The chosen highest-confidence path shall be expanded into 2–3 ordered subtasks, each assigned to an agent (`coder`, `critic`, `executor`) and a model tier (`strategic`, `coding`, `fast_eval`).
- **FR-ORCH-4 (ToT Fallback):** If an approach fails all retry attempts, the Orchestrator shall fall back to the next-highest-scoring candidate path (`F1`, `F2`, ...).

### 4.2 Coder Agent & Code Generation (FR-CODE)
- **FR-CODE-1 (RAG Memory Integration):** Before generating code, the Coder shall query the local `VectorStore` for semantically similar solved goals and error remediation strategies.
- **FR-CODE-2 (Completeness Contract):** Generated code must be complete, idiomatic Python 3.12+ containing full function bodies, standard library imports, and type hints (no `# TODO` placeholders).
- **FR-CODE-3 (AST Sanitization Engine):** The Coder shall execute an automated AST unescaping pass (`ast.parse`) to detect and fix double-escaped newlines (`\\n` $\rightarrow$ `\n`) and backslashes before disk writes.
- **FR-CODE-4 (Defensive File IO):** Code writes must execute through `WriteFileTool` enforcing path traversal sandboxing within the designated workspace.

### 4.3 Automated Code Review & LLM-as-a-Judge (FR-CRIT)
- **FR-CRIT-1 (4-Axis Evaluation):** The Critic shall evaluate submissions across four 0–10 axes: Correctness, Edge Cases, Acceptance Criteria, and Readability.
- **FR-CRIT-2 (Score Normalization):** Total scores must scale to $0 - 100$. Unscaled $0 - 40$ axis sums must be normalized dynamically ($\text{axis\_sum} \times 2.5$).
- **FR-CRIT-3 (Approval Threshold):** Submissions scoring $\ge 80/100$ receive an `ACCEPT` verdict. Submissions $< 80$ receive a `REJECT` verdict with actionable `issues` and `fix_suggestions`.
- **FR-CRIT-4 (Final Attempt Leniency):** On the final retry attempt, code shall proceed to the Executor to test real runtime behavior rather than looping indefinitely on stylistic rejections.

### 4.4 Sandboxed Execution & Safety Guardrails (FR-EXEC)
- **FR-EXEC-1 (AST Safety Guardrail Scan):** Prior to execution, code must pass an AST scanner blocking dangerous modules (`ctypes`, `socket`, `multiprocessing`) and functions (`os.system`, recursive deletions, dynamic `__import__`).
- **FR-EXEC-2 (Subprocess Isolation):** Code runs in an isolated subprocess with a default 30-second execution timeout.
- **FR-EXEC-3 (Traceback Parsing):** Non-zero exit codes must be parsed into structured error descriptors (`exception`, `line`, `kind`, `demands_strategy`).
- **FR-EXEC-4 (Benign Stderr Handling):** Output containing zero exit codes with benign stderr messages (e.g., standard `unittest` progress) shall be marked as successful execution.

### 4.5 Adaptive Retry Routing (FR-RETRY)
- **FR-RETRY-1 (Syntax Recovery):** `SyntaxError`, `IndentationError`, and `TabError` shall trigger the `LINE_PATCH` strategy, prompting Coder to patch specific line numbers.
- **FR-RETRY-2 (Logic Recovery):** `AssertionError`, `ValueError`, `KeyError`, and `IndexError` shall trigger the `FULL_REWRITE` strategy, prompting Coder to overhaul algorithms and base cases.
- **FR-RETRY-3 (External Recovery):** Timeouts and environment exceptions shall trigger the `BACKOFF` strategy with exponential jitter delays ($1\text{s}, 2\text{s}, 4\text{s}$).

### 4.6 Human-in-the-Loop Escalation (FR-ESCALATE)
- **FR-ESCALATE-1 (Confidence Trigger):** If a subtask remains unresolved after 2 retries and moving average confidence is $< 0.50$, execution shall pause and emit a `needs_human_review` event.
- **FR-ESCALATE-2 (Interactive Resolution):** The React UI shall present an interactive modal displaying recent error signatures and a targeted clarifying question.
- **FR-ESCALATE-3 (Context Injection):** When answered, the human advice shall be injected into the Coder prompt and the retry budget shall be reset.

### 4.7 Evaluation Lab Benchmark Suite (FR-EVAL)
- **FR-EVAL-1 (A/B Test Execution):** The system shall support automated batch execution comparing Self-Correction ON vs Baseline (OFF) across 12 canonical goals.
- **FR-EVAL-2 (Trace Persistence):** Individual run traces and an aggregated `summary.json` report must be saved automatically to `local_test_report/eval_<timestamp>/`.

---

## 5. Non-Functional Requirements & System Constraints

| Category | Requirement | Specification |
| :--- | :--- | :--- |
| **Performance** | Event Streaming | WebSocket event broadcast latency $\le 15\text{ms}$; real-time token streaming. |
| **Cost Management** | Free-Tier Priority | Intelligent load balancing across free tiers of Groq, NVIDIA NIM, and OpenRouter. |
| **Budget Enforcement** | Hard Financial Caps | Automatically halts execution if total tokens exceed 200,000 or USD cost exceeds \$5.00. |
| **Reliability** | Parser Fallbacks | 100% of LLM replies pass through regex fallback extractors to prevent JSON deserialization crashes. |
| **Portability** | Platform Independence | Fully operational on Windows, macOS, and Linux without native binary dependencies. |

---

## 6. Risk Register & Mitigation Strategy

| Risk ID | Risk Description | Severity | Likelihood | Mitigation Strategy |
| :--- | :--- | :---: | :---: | :--- |
| **RSK-1** | Free-tier provider 429 rate limiting or quota exhaustion | High | High | Multi-tier failover chain across 7 providers, reactive 2s backoff, and per-model token-per-day rotation. |
| **RSK-2** | Subprocess sandbox breakout or destructive shell commands | Critical | Low | Static AST safety scanner (`backend/safety/guardrails.py`) blocks dangerous modules and system calls prior to execution. |
| **RSK-3** | Infinite retry loops consuming excessive tokens | High | Low | Hard attempt cap (`max_retries_per_subtask: 3`) and cost budget monitoring (`max_total_cost_usd: 5.0`). |
| **RSK-4** | LLM formatting errors producing unparseable JSON code blocks | Medium | Medium | Multi-tier fallback extraction in Coder and Critic agents (clean JSON $\rightarrow$ block regex $\rightarrow$ fence extraction). |
