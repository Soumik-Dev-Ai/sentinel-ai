# Implementation Order — 48h Build Plan

> Goal: an *honest demonstrable agent* by Hour 16, leaving the bulk of time for
> self-correction nuance, eval honesty, the demo, and the README.

## 1. Phase 0 — Setup (Hours 0–2)
- [ ] `pyproject.toml` with deps from `docs/TECH_STACK.md`
- [ ] `.gitignore`, `.env.example`, `pre-commit` (ruff+mypy+pytest-gate)
- [ ] `src/` skeleton with empty modules per ARCHITECTURE section 2
- [ ] `tests/` skeleton + `conftest.py` with `MockProvider` fixture
- [ ] **Gate**: `pytest` (empty) green; `ruff check .` green; `mypy --strict src` green (vacuous)
- **Commit**: `chore: project scaffold + tooling`

## 2. Phase 1 — Minimal loop, NO recovery (Hours 2–8)
- [ ] `WorkingMemory` dataclass + `test_working_memory.py`
- [ ] `llm/contracts.py`: `Reply`, `Provider` protocol + `MockProvider`
- [ ] `llm/router.py` with **single** provider (anthropic) + `test_router.py` (single)
- [ ] `tools/base.py` `ToolProtocol` + pydantic schemas + `test_tools_base.py`
- [ ] `tools/file_io.py`, `tools/code_exec.py` (sandboxed subprocess)
- [ ] `agent/react.py`: emit `Thought`+`Action`; `agent/runner.py`: 5-step happy loop
- [ ] `io/logger.py` + `test_logger.py`; persist `WorkingMemory` per step
- [ ] **Gate**: integration `test_happy_path_5step_goal_completes_no_corrections` green
- **Commits**: `feat(memory): WorkingMemory`, `feat(llm): router+contracts+mock`,
  `feat(tools): base + file_io + code_exec`, `feat(agent): react+runner happy path`,
  `feat(io): structured logger`

## 3. Phase 2 — Self-evaluation + 2 failure modes (Hours 8–16)
- [ ] `agent/self_evaluator.py` (success/coherence/plan_valid/mode/classify)
- [ ] `recovery/taxonomy.py` + `test_taxonomy.py` (golden triples)
- [ ] `recovery/strategies.py` — **F1 ToolFailure** (call) + **F2 ResultInconsistency** (facts)
- [ ] `recovery/controller.py` (budget enforcement) + `test_controller.py`
- [ ] `test_strategies.py::test_each_strategy_mutates_distinct_object` for F1, F2
- [ ] **Intentionally flaky `tools/flaky_net.py`** + `test_flaky_net.py`
- [ ] Integration: `test_F1_recover_via_reinvoke_then_success`, `test_F2_inconsistency_probe_resolves`
- [ ] **Decisive**: `test_correction_changes_call_or_facts_or_plan_or_scope_or_stop` for F1/F2
- [ ] **Gate**: 3 of 11 goals (G1, G5, G6) pass e2e end-to-end with visible corrections in logs
- **Commits**: `feat(eval): self_evaluator`, `feat(recovery): F1 tool_failure`,
  `feat(recovery): F2 result_inconsistency`, `feat(tools): flaky_net`,
  `feat(recovery): controller + budget`, `test(integration): F1 F2 recover`

## 4. Phase 3 — Remaining failure modes + multi-LLM fallback (Hours 16–26)
- [ ] `recovery/strategies.py` — **F3 GoalDrift** (plan), **F4 InsufficientInformation** (plan+scope), **F5 BudgetExceeded** (stop)
- [ ] Extend `test_strategies.py` distinctness to all 5 modes
- [ ] `llm/openai_provider.py` + circuit breaker in `router.py` + `test_router.py` failover tests
- [ ] (Optional) `llm/local_provider.py` (Ollama)
- [ ] Integration: `test_F3_goal_drift`, `test_F4_insufficient_info`, `test_F5_escalation`, `test_router_failover`
- [ ] Tools: `test_run.py` (pytest subprocess), `spec_check.py`
- [ ] **Gate**: 6 of 11 goals pass e2e
- **Commits**: `feat(recovery): F3 goal_drift`, `feat(recovery): F4 insufficient_info`,
  `feat(recovery): F5 budget_exceeded`, `feat(llm): openai provider + circuit breaker`,
  `feat(tools): run_tests + spec_check`, `test(integration): F3 F4 F5 + router failover`

## 5. Phase 4 — Eval, viewers, baseline, comparison (Hours 26–36)
- [ ] `eval/goals.yaml` (all 11 goals)
- [ ] `eval/metrics.py` + `eval/run_eval.py`
- [ ] `examples/baseline_no_self_corr.py` (self-eval stubbed to always-True)
- [ ] `eval/comparison.md` generator
- [ ] `io/viewer_cli.py` (`rich`) + `io/viewer_html.py` (`jinja2`) + `test_viewer.py`
- [ ] `eval/scripts/audit_retries.py` (the M3 audit)
- [ ] **Gate**: 10+ goals run; metrics emitted; comparison table generated; M3 audit clean (no hidden retries)
- **Commits**: `feat(eval): goals + metrics + runner`, `feat(baseline): no-self-correct variant`,
  `feat(io): cli + html viewers`, `feat(eval): comparison + retry-audit script`

## 6. Phase 5 — Demo, README, honesty pass (Hours 36–44)
- [ ] `demos/demo_script.md` — storyboard with >=1 visible correction
- [ ] Record GIF (asciinema -> gif)
- [ ] Manually run M1, M2, M4, M5, M6, M8, M9 checklists; record outputs
- [ ] README: architecture (link ARCHITECTURE), taxonomy (link TESTING_PLAN section 2.3), eval results (incl. failures), 3 traced cases, future-work list
- **Commits**: `docs: demo storyboard`, `docs: README`, `test(manual): M1-M9 records`

## 7. Phase 6 — Polish, clean-room run (Hours 44–48)
- [ ] `mypy --strict src` full green; ruff clean
- [ ] Coverage to >=85% on `src/` (close gaps from `pytest-cov` report)
- [ ] **M10 clean-room run**: fresh clone + `.env` -> `python -m eval.run_eval` runs to completion; metrics within stated variance
- [ ] Final commit-history audit (small, descriptive commits)
- **Commits**: `chore: strict types`, `chore: coverage to 85%`, `chore: cleanroom eval verified`

## 8. Build Order Cheatsheet (which file when)
| Hour band | Files touched |
|-----------|---------------|
| 0–2 | pyproject, .gitignore, .env.example, conftest, skeletons |
| 2–8 | working_memory, llm/contracts+router, tools/base+file_io+code_exec, react, runner, logger |
| 8–16 | self_evaluator, taxonomy, strategies (F1,F2), controller, flaky_net |
| 16–26 | strategies (F3,F4,F5), openai/local providers, circuit breaker, run_tests, spec_check |
| 26–36 | eval/goals.yaml, run_eval, metrics, baseline variant, viewers, audit_retries |
| 36–44 | demos, README, manual checklist records |
| 44–48 | mypy strict, coverage, clean-room run |

## 9. Stop Conditions
- **Stop and surface** if: real-LLM API key unavailable for e2e (cannot produce required metrics/logs) — request credentials.
- **Stop and surface** if: Windows sandbox limits materially affect e2e determinism in a way not covered by the documented limitation.
- **Continue past friction** for everything else (ambiguous goal: pick most reasonable, note assumption, continue).
- **Never claim "done"** without: `pytest -q` green, `ruff check .` green, `mypy --strict src` green, `python -m eval.run_eval` producing the required artifacts, and the demo GIF recorded.

## 10. Commit Message Style
- Conventional commits: `feat(scope): ...`, `test(scope): ...`, `docs: ...`, `chore: ...`, `fix(scope): ...`.
- Scoped: `agent`, `recovery`, `tools`, `llm`, `io`, `eval`, `docs`, `test`.
