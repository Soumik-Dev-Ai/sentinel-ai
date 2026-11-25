# System Architecture — Self-Correcting Multi-Step Agent

## 1. High-Level Diagram

```
+--------------------------------------------------------------+
|                         AgentRunner                          |
|  (orchestration loop, budget enforcement, persistence)       |
+--------------------------------------------------------------+
        |
        v
+-----------------+    +------------------+    +------------------+
|  ReAct Step     | -> |  Tool Executor   | -> |  Self-Evaluator  |
|  (reason+act)   |    | (typed/validated)|    | (score + detect) |
+-----------------+    +------------------+    +------------------+
        |                     |                        |
        +----------+----------+-----------+------------+
                   v                      v
        +--------------------+  +--------------------------+
        |  Working Memory    |  |   Recovery Controller    |
        |  - Goal            |  |  - Failure taxonomy      |
        |  - Plan (steps)    |  |  - Strategy per mode     |
        |  - Executed[]      |  |  - Replan budget         |
        |  - Findings{}      |  |  - Escalation (unresolv.)|
        |  - Pending[]       |  +--------------------------+
        |  - BudgetState     |
        |  - WorldModel      |
        +--------------------+
                   |
                   v
        +--------------------+  +--------------------------+
        |  LLM Router        | -> |  Providers (fallback)  |
        |  - pick model      |  | Claude -> GPT-4o -> local|
        |  - retry / degrade |  +--------------------------+
        +--------------------+
                   |
                   v
        +--------------------+  +--------------------+
        |  Structured Logger | -> |  Log Viewer      |
        |  (JSON per run)    |  |  (CLI + HTML)      |
        +--------------------+  +--------------------+
```

## 2. Folder Layout (proposed)
```
self-correcting-agent/
|-- src/
|   |-- agent/
|   |   |-- runner.py            # AgentRunner: main loop, budget, persistence
|   |   |-- react.py             # ReAct step: produce reasoning trace + action
|   |   |-- working_memory.py    # WorkingMemory dataclass
|   |   `-- self_evaluator.py    # post-action evaluation
|   |-- recovery/
|   |   |-- taxonomy.py          # FailureMode enum + classification rules
|   |   |-- controller.py        # pick strategy by FailureMode, budget, escalate
|   |   `-- strategies.py        # one function per mode (different mutated object)
|   |-- tools/
|   |   |-- base.py              # ToolProtocol, typed schemas, schema validation
|   |   |-- file_io.py           # write_file / read_file
|   |   |-- code_exec.py         # run_python (subprocess sandbox)
|   |   |-- test_run.py          # run_tests (pytest subprocess)
|   |   |-- spec_check.py        # validate_output_against_spec
|   |   `-- flaky_net.py         # INTENTIONALLY flaky tool
|   |-- llm/
|   |   |-- router.py            # routing + fallback chain + circuit breaker
|   |   |-- anthropic_provider.py
|   |   |-- openai_provider.py
|   |   |-- local_provider.py    # Ollama via http (last-resort)
|   |   `-- contracts.py         # common interface: chat(...) -> Reply
|   |-- io/
|   |   |-- logger.py            # structured JSON run log
|   |   |-- viewer_cli.py        # rich-based CLI table
|   |   `-- viewer_html.py       # static HTML render
|   `-- config.py                # env, keys, budgets, model map
|-- tests/
|   |-- unit/ integration/ e2e/ fixtures/ conftest.py
|-- eval/
|   |-- goals.yaml               # 10+ evaluation goals (canonical)
|   |-- run_eval.py              # runs agent + baseline variant
|   |-- metrics.py               # completion/avg-steps/corrections/unrecoverable
|   `-- reports/                 # generated logs + metrics + comparison table
|-- demos/demo_script.md
|-- examples/baseline_no_self_corr.py
|-- .env.example  .gitignore  pyproject.toml  README.md
`-- docs/PRD.md ARCHITECTURE.md TECH_STACK.md TESTING_PLAN.md IMPLEMENTATION_ORDER.md
```

## 3. ReAct Loop (per step)
1. **Reason**: LLM receives (goal, plan, working-memory snapshot, last N executed steps + findings, current pending subtask) -> must emit a `Thought` block before an `Action`.
2. **Act**: parse `Action` -> `Tool` + typed `args` -> validate against tool's pydantic schema -> if invalid, synthesize a synthetic `ToolFailure(shape_violation)` result and continue (no LLM round-trip needed).
3. **Observe**: run tool with timeout + sandbox -> capture `result/exit_code/stderr` -> validate return shape; on schema mismatch -> wrap as `ToolFailure(shape_violation)`.
4. **Self-Evaluate**: pass (goal, action, observation, plan, world_model) -> outputs `{success: bool, coherence: float in [0,1], plan_valid: bool, detected_mode: FailureMode | None, evidence}`.
5. **Decide**: if `success && plan_valid` -> advance plan; else route to RecoveryController with `detected_mode`.

```python
# pseudo
while memory.pending and not memory.is_finished():
    thought, action = react.step(memory, router)
    obs = tool_executor.invoke(action)            # typed + validated
    eval_ = self_evaluator.evaluate(memory.goal, action, obs, memory.plan, memory.world_model)
    memory.record_step(thought, action, obs, eval_)
    if eval_.success and eval_.plan_valid:
        memory.advance_subtask()
    else:
        cmd = recovery.controller.recover(eval_.mode, memory)
        memory.apply(cmd)                          # may mutate call/facts/plan/scope or stop
    io.logger.persist(memory)
```

## 4. Working Memory (explicit data structure)
```python
@dataclass
class WorkingMemory:
    goal: Goal                      # original spec + acceptance criteria
    plan: list[Subtask]             # ordered, status in {pending, active, done, blocked, unresolvable}
    executed: list[StepRecord]      # thought, action, tool, args, result, eval, ts
    findings: dict[SubtaskId, Finding]   # distilled facts/code/outputs discovered
    pending: list[SubtaskId]        # frontier
    budget: dict[SubtaskId, int]    # remaining recovery attempts per subtask
    world_model: WorldModel         # files, deps, content-hashes, prior runs
    corrections: list[CorrectionRecord]   # mode, trigger, strategy, new plan, ts
    final_output: Any | None
```
Persisted to disk per step -> runs are resumable and logs are reconstructable from memory alone.

## 5. Failure Mode Taxonomy (>=3, each with a *distinct* recovery)

| # | FailureMode | Detection signal | Recovery strategy (distinct mutation object) |
|---|---|---|---|
| F1 | **ToolFailure** — tool errored, timed out, returned wrong schema | exit!=0, exception, schema-validation fail | **call**: re-invoke with hardened args once (different timeout, sanitized args); if persists, **substitute tool** (e.g. fallback install method). Never re-plans the goal. |
| F2 | **ResultInconsistency** — tool succeeded but result contradicts another finding or acceptance invariant | evaluator cross-checks result vs `findings` & spec predicates | **facts**: issue a targeted contradict/confirm probe (re-run stricter test, ask verification query); keep the richer of the two; flag contradiction in `world_model`. |
| F3 | **GoalDrift** — current active subtask no longer advances the goal (alignment score < tau across 2 consecutive steps) | goal-alignment score from evaluator | **plan**: re-plan from spec — discard tail of plan, regenerate new subtask set constrained by findings so far + "what went wrong" summary. |
| F4 | **InsufficientInformation** | evaluator: required input missing in `world_model` | **plan+scope**: spawn a new gather-subtask (read another file, run a probe), insert ahead of current. |
| F5 | **BudgetExceeded** | `budget[subtask] == 0` | **stop** (this subtask): mark `unresolvable`, write `UnresolvableRecord` (mode history, attempts, evidence, hypothesis), continue plan with degraded output. Never loop. |

> **Distinctness proof** (interview-ready): F1 mutates the **call**, F2 the **facts**, F3 the **plan**, F4 the **plan+scope**, F5 the **stop bit**. The audit test `tests/unit/recovery/test_strategies.py::test_each_strategy_mutates_distinct_object` enforces this invariant mechanically.

### 5.1 Sequence diagrams (textual)

**F1 ToolFailure** (flaky_net returns malformed schema)
```
react.step -> flaky_net.install_package -> schema validate FAIL
   -> evaluator: mode=F1, evidence="missing 'version' field"
   -> controller.recover(F1): budget[subtask]-- (3->2)
   -> strategies.tool_failure: re-invoke w/ hardened args (timeout=60, sanitize pkg name)
   -> tool succeeds with conforming schema
   -> evaluator: success=True -> advance plan
```

**F2 ResultInconsistency** (CSV parse yields wrong row count)
```
react.step -> run_python(parse.py) -> exit 0, but row count != expected
   -> evaluator: mode=F2, evidence="row count 7 != expected 12 (per spec)"
   -> controller.recover(F2): budget-- (3->2)
   -> strategies.result_inconsistency: issue probe run_python(parse.py --strict-quotes)
   -> probe returns 12 rows -> keep probe finding, flag bug in original parse in world_model
   -> evaluator: success=True -> advance
```

**F3 GoalDrift** (recursive fib when spec demands iterative)
```
react.step (write code: recursive fib) -> run_tests pass
   -> evaluator: success=True BUT plan_valid=False
     evidence="acceptance: O(1) memory; current impl is O(n) stack"
   -> controller.recover(F3): budget-- (3->2)
   -> strategies.goal_drift: re-plan from spec — discard tail (write tests for recursive)
     generate new subtasks [impl iterative O(1), re-run tests with complexity gate]
   -> next step writes iterative impl -> tests green -> advance
```

**F4 InsufficientInformation** (need to read `mod.py` before fixing it)
```
react.step (action: edit mod.py) -> evaluator: mode=F4
   evidence="world_model has no content hash for mod.py"
   -> controller.recover(F4): budget-- (3->2)
   -> strategies.insufficient_info: spawn new subtask "read mod.py" inserted before current
   -> next step reads mod.py -> findings updated -> re-evaluate edit action with content known
```

**F5 BudgetExceeded** (unreachable timing acceptance)
```
... after 3 failed F3/F4 attempts to meet `<1ms on n=10^9` ...
   -> controller.recover(F5): budget[subtask]==0
   -> strategies.budget_exceeded:
       mark subtask 'unresolvable'
       write UnresolvableRecord{modes:[F3,F3,F4], attempts:3,
         evidence: "<1ms_infeasible: O(n) lower bound", hypothesis: "spec is unreachable"}
   -> plan continues to deliver best-effort impl + honest report -> terminate
```

## 6. LLM Router — Multi-Provider Fallback
- Chain: `Anthropic Claude Sonnet` -> `OpenAI GPT-4o` -> `Ollama local` (if configured).
- Selection: prefer Claude for planning/reasoning (long ctx, strong tool-use), GPT-4o as failover, local as last-resort degradation.
- **Circuit breaker** per provider: trip after K failures in window -> skip for cooldown.
- **Contract**: `chat(messages, tools, response_schema) -> Reply{thought, action, finish_reason, usage}`; router transparent to agent loop.
- **Telemetry**: per-call cost/latency/provider logged; viewer surfaces provider switches.

## 7. Intentionally Flaky Tool
`flaky_net.install_package(pkg)`:
- Succeeds deterministically if `pkg` is in a vendored local cache.
- **Fails intermittently (~40%)** if real install is required.
- Occasionally returns a **malformed success schema** (missing `version` field) -> exercises schema-validation path.

Seeded (`random.Random(seed)` injected) for deterministic test runs.

## 8. Structured Log Schema (one JSON per run)
```json
{
  "run_id": "...",
  "goal": {"id": "G2", "spec": "...", "acceptance": ["..."]},
  "plan_initial": [{"id": "S1", "desc": "...", "status": "..."}],
  "steps": [
    {"ts":"...", "step_ix":1, "thought":"...", "tool":"...", "args":{},
     "result":{}, "eval":{"success":true,"coherence":0.9,"plan_valid":true,
                             "mode":null,"evidence":"..."},
     "correction_trigger": null}
  ],
  "corrections": [
    {"ts":"...", "step_ix":3, "mode":"F1", "strategy":"tool_failure",
     "new_plan": [], "budget_after": 2}
  ],
  "provider_events": [{"ts":"...", "from":"anthropic","to":"openai","reason":"429"}],
  "unresolvable": [
    {"subtask_id":"S4","modes":["F3","F3","F4"],"attempts":3,
     "evidence":"...","hypothesis":"..."}
  ],
  "final_output": "...",
  "metrics": {"steps":7, "self_corrections":2, "provider_switches":0,
              "wall_s":12.4, "tokens": {"in": 0, "out": 0}}
}
```
Viewer: `rich` CLI table (filter by mode/correction) + static HTML render (collapsible traces). Both read the same JSON -> zero divergence.

## 9. Sandbox & Safety
- All `run_python`/`run_tests` invocations use `subprocess.run(timeout=..., cwd=tempdir, env=blocked_net)`.
- POSIX: optional `resource.setrlimit` (cpu, fsize). **Windows**: timeout + cwd + env-blocking only — documented limitation.
- No tool ever writes outside its per-run tempdir except `write_file` to an explicit, validated workspace path.

## 10. Determinism & Reproducibility
- Unit + integration tests use `MockProvider` (canned Replies) — fully offline, deterministic.
- `flaky_net` uses an injected seedable `random.Random`.
- E2E: real LLM (non-deterministic); we log every request payload hash for post-hoc analysis and pin provider+model in `config.py` for reproducible *selection* (not output).

## 11. Extension Points
- Add a tool: subclass `ToolProtocol`; register in `tools/__init__.py`; declare arg+return schemas.
- Add a provider: implement `chat(...) -> Reply`; append to `router.CHAIN`.
- Add a failure mode: extend `FailureMode` enum; add a classifier rule in `taxonomy.classify`; add a strategy in `strategies.py` that mutates a **new** object (or document why an existing object is reused).
- Swap domain (web research): replace `tools/code_exec*` with `tools/http_fetch*`; agent loop, recovery, and memory unchanged.
