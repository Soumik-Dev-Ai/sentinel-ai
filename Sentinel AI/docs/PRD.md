# PRD — Self-Correcting Multi-Step Agent (Code Generation + Execution)

> Heva AI — AI/ML Engineer Assignment 2. Build a multi-step agent that plans,
> executes, monitors its own outputs, detects failure or goal drift, and
> self-corrects without a human in the loop. Domain: **code generation +
> execution**. Language: **Python 3.12**. Reasoning engine: **multi-LLM
> fallback chain**. No agent frameworks allowed.

## 1. Problem Statement
Production AI agents fail predictably: they execute a plan, hit a failure, and
either crash or emit a confidently-wrong answer. The hard part of agentic AI is
**not** getting an LLM to take actions — it is getting the agent to **detect**
when its actions went wrong and **recover intelligently** with no human in the
loop.

This project builds an agent that:
- Given a small coding goal (>=5 surface steps to complete),
- Plans -> executes -> self-evaluates after each action,
- Detects failure / result inconsistency / goal drift,
- Replans or escalates without infinite loops,
- Produces a real working artifact (code file, test results, or honest degraded output).

It is not a chatbot. It performs real actions in the filesystem and subprocess layer.

## 2. Goals (P0)
| # | Requirement | Acceptance |
|---|---|---|
| G1 | Explicit ReAct loop (reason + act) | Every step emits a `Thought` before its `Action`; trace logged + inspectable. |
| G2 | Explicit working memory | `WorkingMemory` dataclass (Goal/Plan/Executed/Findings/Pending/Budget/WorldModel/Corrections) — not chat history. Persisted per step. |
| G3 | Typed & validated tool calls | Each tool declares pydantic v2 schemas for args **and** return; violations synthesize `ToolFailure(shape_violation)` instead of crashing. |
| G4 | Post-action self-evaluation | After every tool call, evaluator scores: success, goal-coherence, plan-validity, classifies `FailureMode` (or `None`). |
| G5 | >=3 distinct failure modes with distinct recovery | F1 ToolFailure / F2 ResultInconsistency / F3 GoalDrift / F4 InsufficientInformation / F5 BudgetExceeded. Each mutates a **different object**: call, facts, plan, plan+scope, stop. Not "retry with a different prompt". |
| G6 | Replanning budget + escalation | Per-subtask budget N; on exhaustion mark `unresolvable` with a structured `UnresolvableRecord` (mode history, attempts, evidence, hypothesis). Continue, never loop. |
| G7 | Intentionally flaky tool | `flaky_net.install_package` fails ~40% and sometimes returns malformed-success schema; e2e shows detect + recover. |
| G8 | Eval on >=10 goals | `eval/run_eval.py` produces: completion rate, avg steps, self-corrections, unrecoverable, provider switches. |
| G9 | >=3 traced self-corrections | README contains 3 full reasoning-trace case studies (one F1, one F2, one F3). |
| G10 | Baseline comparison | A "no self-correction" variant (`examples/baseline_no_self_corr.py`) runs the same 10 goals; comparison table shows quality delta. |
| G11 | Structured logs + viewer | One JSON per run in `eval/reports/`. CLI viewer (`rich`) + HTML viewer (`jinja2`) read identical fields. |
| G12 | Constraints honored | No LangChain / LlamaIndex / AutoGen / CrewAI / pre-built agent scaffolding. Only LLM APIs + standard tool libs. |

## 3. Non-Goals
- Not a general-purpose chat assistant.
- Not a chat UI; only a log viewer.
- No multi-agent / agent-framework integration.
- No production deployment / serving infra.
- No GPU training, no fine-tuning.
- No browser automation tools (domain is local code/subprocess).

## 4. Users & Personas
Single user: the **engineer-reviewer** (Heva AI interviewer + author) who runs
`eval/run_eval.py`, reads `eval/reports/`, and joins an interview that probes
the design. The agent itself is the runtime.

## 5. Domain Choice & Why
**Code generation + execution.** Each goal produces concrete artifacts: source
files, test runs, stdout. Failure is *observable and machine-checkable*
(non-zero exit code, traceback, test failure, malformed output). Self-evaluation
is grounded rather than vibes-based.

**Assignment-relevant risk we explicitly mitigate.** A code agent that just
re-runs on failure is *exactly* the retry-loop anti-pattern. Our recovery
taxonomy is designed so each mode mutates a **different object** (call args /
facts / plan / scope / stop). The manual audit M3 in the testing plan audits
`CorrectionRecord` history to reject hidden retries.

## 6. Use Cases (10 evaluation goals)
See `eval/goals.yaml` and `docs/TESTING_PLAN.md` section 4.4.
| ID | Theme | Designed to trigger |
|----|-------|---------------------|
| G1 | `fib(n)` recursive + test | baseline happy path |
| G2 | `fib(n)` iterative O(1) memory | F3 goal drift (rewrite) |
| G3 | Filter CSV rows `price>100` (quoted comma mid-field) | F2 inconsistency (parse) |
| G4 | Read `mod.py`, fix an off-by-one | F4 insufficient info -> probe |
| G5 | Goal that needs an external package via flaky net | F1 tool failure + schema viol. |
| G6 | Sum a list of ints, `0` on empty — buggy `sum()` shadowing builtin | F2 inconsistency (test fail) |
| G7 | Multi-step: write tests -> impl -> run -> fix -> re-run until green | compound F1/F2/F3 |
| G8 | Multi-file: FizzBuzz in `lib/` + re-export via `__init__.py` | F4 insufficient info |
| G9 | Unreachable acceptance criterion (`<1ms` on `n=10^9`) | F5 escalation (honest failure) |
| G10 | Ambiguous spec ("make a nice CLI") with implicit expectations | F3 drift + documented degraded output |
| G11 (bonus) | Tiny CLI with >=3 subcommands + tests | budget fatigue, long horizon |

## 7. Functional Requirements
### 7.1 Agent Loop (`src/agent/`)
- `AgentRunner` orchestrates the loop, enforces budget, persists working memory per step.
- `react.step()` produces `Thought` -> `Action` via the LLM router.
- `WorkingMemory` is the single source of truth; persisted to disk every step.
- `self_evaluator.evaluate(goal, action, observation, plan, world_model)` returns `{success, coherence, plan_valid, mode, evidence}`.

### 7.2 Tools (`src/tools/`)
- `ToolProtocol`: `name`, `args_schema`, `return_schema`, `invoke(args)`.
- Built-ins: `write_file`, `read_file`, `run_python` (subprocess sandbox: `cwd=tempdir`, `timeout`, network-blocked env), `run_tests` (pytest), `spec_check` (predicate vs expected), `flaky_net.install_package` (intermittent fail + malformed-success).
- All returns pydantic-validated; violations become synthetic `ToolFailure(shape_violation)`.

### 7.3 Recovery (`src/recovery/`)
- `taxonomy.classify(action, observation, plan, world_model) -> FailureMode | None`.
- `controller.recover(mode, ctx) -> NewPlan | Escalation` — enforces budget per subtask.
- `strategies.<mode>()` — one function per mode, each mutating a different object.

### 7.4 LLM Router (`src/llm/`)
- Chain: `Anthropic Claude Sonnet` -> `OpenAI GPT-4o` -> `Ollama local` (optional).
- Per-provider circuit breaker (K fails in window -> cooldown).
- Common `Reply` contract; router transparent to the agent loop.

### 7.5 Observability (`src/io/`)
- `logger` writes `eval/reports/<run_id>.json` per run (schema: ARCHITECTURE section 2.8).
- `viewer_cli` (`rich`) and `viewer_html` (`jinja2`) read the same JSON.

### 7.6 Eval (`eval/`)
- `run_eval.py` iterates `goals.yaml`, runs the agent + baseline, writes per-run JSON + aggregate `metrics.csv` / `metrics.md` / `comparison.md`.

## 8. Non-Functional Requirements
| Area | Target |
|------|--------|
| Type safety | `mypy --strict src` passes; pydantic v2 for runtime tool I/O |
| Lint/format | `ruff check . && ruff format --check .` passes |
| Test gates | Unit + integration suites pass with >=85% line coverage on `src/` |
| Determinism | Unit + integration deterministic via `MockProvider` + seeded `flaky_net` |
| Isolation | All subprocess tool calls run in test-isolated tempdirs; network-blocking env where supported |
| Secrets | `.env` for API keys, `.gitignore`-protected; no secrets in source/logs |
| Performance | Step budget <= ~25 steps/goal (configurable); per-tool timeout <= 30s |
| Reproducibility | `eval/` runnable from fresh clone with only `.env` set |
| File hygiene | Source files <= ~500 lines each |

## 9. Success Criteria
1. Rubric survives interview:
   - Self-correction is **principled**, not a renamed retry (audit M3).
   - Failure-mode taxonomy has **distinct recovery strategies** (audit M2).
   - Working memory reflects **stateful design**, not chat history.
   - ReAct traces show **reasoning**, not formatted echoes (M1).
   - Evaluation is **honest**: every unrecoverable case listed with the agent's own evidence (M9).
2. `eval/run_eval.py` runs the 11 goals and baseline variant; emits metrics.
3. README covers architecture, taxonomy, eval (incl. failures), >=3 traced cases.
4. Demo GIF/asciinema shows >=1 visible self-correction.
5. Structured logs render correctly in both viewers.

## 10. Constraints & Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Recovery collapses to retry | assignment-failing | M3 audit; distinct mutation-object per mode in design |
| LLM nondeterminism | flaky tests | `MockProvider` for unit/integration; real LLM only in e2e |
| Real API cost / rate limits | slow iteration | deterministic fixtures; e2e batched; circuit breaker |
| Windows sandbox limits (no `setrlimit`) | weaker isolation | documented; `timeout` + `cwd` + env-blocking still enforced |
| Ambiguous goals (G10) unbounded | budget exhaustion | per-subtask budget N + F5 escalation guarantees termination |
| Multi-LLM router complexity | fallback bugs | circuit-breaker unit tests; M5 manual failover drill |

## 11. Timeline
48h. Build order in `docs/IMPLEMENTATION_ORDER.md` is structured so a *minimum
demonstrable* agent (mock LLM, 2 of 5 failure modes, 3 of 11 goals) works by end
of Hour 16, leaving the bulk for self-correction nuance, eval honesty, demo.

## 12. Out of Scope for V1 (future-work list for README)
- Streaming LLM responses / token-level traces.
- Saving/replaying real LLM fixtures for full e2e determinism.
- Parallel tool calls within a single step.
- Browser-based interactive viewer (we ship static HTML only).
- Real sandboxing via containers (we use subprocess + tempdir + env).
