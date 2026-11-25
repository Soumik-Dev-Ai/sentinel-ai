# Testing Plan — Self-Correcting Multi-Step Agent

## 1. Strategy (three layers)
| Layer | Goal | LLM | Network | Determinism |
|-------|------|-----|---------|-------------|
| **Unit** | pure logic correctness | `MockProvider` (or none) | no | deterministic (<2s) |
| **Integration** | full AgentRunner + real tools on tempdir | `MockProvider` | no | deterministic |
| **E2E / Eval** | produce the assignment deliverables | real LLM chain | yes (API) | non-deterministic (logged) |

## 2. Unit Tests (autonomous, pytest) — `tests/unit/`

### 2.1 `test_working_memory.py`
- `test_advance_subtask_moves_pending_to_done`
- `test_budget_decrement_per_correction`
- `test_escalation_fires_at_zero_budget`
- `test_pending_frontier_respects_order`
- `test_persist_roundtrip_creates_equal_memory` (serialize -> reload -> ==)
- `test_world_model_content_hash_is_added_on_read`

### 2.2 `test_taxonomy.py`
- `test_classify_tool_failure_exit_nonzero` -> `F1`
- `test_classify_schema_violation` -> `F1`
- `test_classify_inconsistency_with_prior_finding` -> `F2`
- `test_classify_low_alignment_two_steps` -> `F3`
- `test_classify_missing_world_model_entry` -> `F4`
- `test_classify_budget_zero` -> `F5`
- `test_classify_happy_path_returns_none`
- (5+ golden `<action, obs, plan, world_model> -> mode` triples)

### 2.3 `test_strategies.py` — **the distinctness test**
- `test_tool_failure_reinvokes_with_hardened_args_then_substitutes`
- `test_result_inconsistency_emits_probe_and_keeps_richer_finding`
- `test_goal_drift_discards_plan_tail_and_regenerates`
- `test_insufficient_info_spawns_gather_subtask_ahead_of_current`
- `test_budget_exceeded_writes_unresolvable_record_and_marks_subtask`
- `test_each_strategy_mutates_distinct_object` (parametrized assertion over mutation target: call/facts/plan/plan+scope/stop) — **the assignment's central criterion**
- `test_no_strategy_mutates_two_objects_at_once` (property)

### 2.4 `test_controller.py`
- `test_budget_decrements_on_correction`
- `test_escalation_after_N_corrections` (any N)
- `test_controller_never_loops_infinitely` (forced replanning storm)
- `test_controller_routes_mode_to_correct_strategy` (table-driven)

### 2.5 `test_tools_base.py`
- `test_accepts_conforming_return_shape`
- `test_rejects_missing_field_emits_ToolFailure_shape_violation` (5+ malformed cases)
- `test_args_validation_emits_ToolFailure_args_invalid`

### 2.6 `test_flaky_net.py`
- `test_seeded_40pct_failure_rate_within_tolerance` (seeded, statistical)
- `test_malformed_success_missing_version_field_is_rejected`
- `test_cached_package_succeeds_deterministically`

### 2.7 `test_router.py`
- `test_fallback_chain_order_anthropic_openai_local`
- `test_circuit_breaker_trips_after_K_failures`
- `test_circuit_breaker_recovers_after_cooldown`
- `test_provider_switches_logged_in_provider_events`

### 2.8 `test_contracts.py`
- `test_each_provider_returns_conforming_Reply`
- `test_router_contract_transparent_to_agent` (router & agent call same interface)

### 2.9 `test_logger.py`
- `test_roundtrip_record_serialize_reload_equals`
- `test_log_contains_required_top_level_keys`
- `test_corrections_section_includes_new_plan`

### 2.10 `test_viewer.py`
- `test_cli_viewer_renders_frozen_log_no_exception`
- `test_html_viewer_emits_selfcontained_file`
- `test_both_viewers_present_same_step_count` (no divergence)

## 3. Integration Tests (autonomous, MockProvider) — `tests/integration/`
Drive the full loop offline:
- `test_happy_path_5step_goal_completes_no_corrections`
- `test_F1_recover_via_reinvoke_then_success`
- `test_F1_persistent_then_substitute_tool`
- `test_F2_inconsistency_probe_resolves_keeps_richer`
- `test_F3_goal_drift_plan_regenerated_tail_discarded`
- `test_F4_insufficient_info_gather_subtask_inserted`
- `test_F5_escalation_unresolvable_record_written_continues`
- `test_schema_violation_path_emits_ToolFailure`
- `test_router_failover_on_429_to_secondary_logged`
- **`test_correction_changes_call_or_facts_or_plan_or_scope_or_stop`** — not just `(tool, args)` re-issued. This is the **retry-vs-recovery invariant**; failing this fails the assignment.

## 4. E2E / Evaluation (autonomous runner + manual review)

### 4.1 Runner — `eval/run_eval.py`
```python
for goal in load_goals("eval/goals.yaml"):
    for variant in ("self_correcting", "baseline"):
        run = Runner(variant=variant).run(goal)
        persist_json(run, f"eval/reports/{variant}/{goal.id}_{run.run_id}.json")
aggregate_metrics()       # metrics.csv + metrics.md
compare_variants()        # comparison.md
```

### 4.2 Metrics emitted
- `completion_rate` — fraction of goals where `final_output` satisfies acceptance
- `avg_steps` — mean `metrics.steps`
- `self_corrections` — total `len(corrections)`
- `unrecoverable` — count of `UnresolvableRecord`
- `provider_switches` — count of `provider_events`
- per-goal: `{goal_id, variants: {self:..., base:...}}`

### 4.3 Baseline variant — `examples/baseline_no_self_corr.py`
Same ReAct loop, same tools, same budget, but:
- `self_evaluator` is replaced with a stub returning `success=True, plan_valid=True` **always**.
- Recovery controller is bypassed.
- This isolates the variable: the self-correction subsystem.

### 4.4 The 11 evaluation goals (`eval/goals.yaml`)
| ID | Goal | Designed to trigger | Min steps |
|----|------|---------------------|-----------|
| G1 | `fib(n)` recursive + test | happy baseline | 5 |
| G2 | `fib(n)` iterative O(1) memory | F3 drift | 6 |
| G3 | Filter CSV `price>100` (quoted comma mid-field) | F2 inconsistency | 6 |
| G4 | Read `mod.py`, fix off-by-one | F4 insufficient info | 6 |
| G5 | Goal needing flaky-Net package | F1 tool failure + schema viol. | 7 |
| G6 | Sum list, `0` on empty; `sum()` shadow bug | F2 test failure | 6 |
| G7 | tests -> impl -> run -> fix -> re-run until green | compound F1/F2/F3 | 8 |
| G8 | Multi-file FizzBuzz in `lib/` + `__init__.py` re-export | F4 insufficient info | 7 |
| G9 | Unreachable acceptance (`<1ms` on `n=10^9`) | F5 escalation | 6 |
| G10 | Ambiguous "nice CLI" with implicit expectations | F3 drift + degraded | 8 |
| G11 (bonus) | Tiny CLI >=3 subcommands + tests | budget fatigue | 10 |

### 4.5 Manual review deliverables (from e2e runs)
- >=3 full reasoning-trace case studies in README (one F1, one F2, one F3) — reprinted from JSON.
- "Where recovery failed" section listing every F5/unrecovered case with the agent's own evidence.
- Side-by-side baseline-vs-self-correcting on >=3 inputs where baseline confidently wrong, self-correcting right.

## 5. Manual Testing Plan — `tests/manual/` checklist

| ID | Procedure | Pass criterion |
|----|-----------|----------------|
| **M1** | Trace authenticity review | For 3 case studies, `Thought` blocks show *reasoning* (e.g. "prior timed out -> likely infinite loop -> add guard"), not echo of action. |
| **M2** | Taxonomy distinctness review | Each `CorrectionRecord` mutated object differs from other modes (call/facts/plan/plan+scope/stop). |
| **M3** | Retry-vs-recovery audit (`eval/scripts/audit_retries.py`) | Query `eval/reports/*.json`; list corrections where `(tool,args)` unchanged across the boundary. Any hidden retry -> fix or document the honest failure. |
| **M4** | Flaky-tool reproducibility | Re-run G5 five times (seeded); detection >=4/5; recovery terminates. |
| **M5** | Provider failover drill | Inject synthetic 429/5xx into primary; secondary handles the step; log records the switch with reasoning intact. |
| **M6** | World-model divergence scenario | Mutate file mid-run; evaluator detects via content-hash; triggers F3 or F4. (Answers the interview question.) |
| **M7** | Demo capture | GIF via `asciinema`/`rich` Live shows >=1 visible self-correction per storyboard. |
| **M8** | Budget exhaustion | Forced unresolvable subtask does not loop; yields `UnresolvableRecord` with hypothesis+evidence. |
| **M9** | Honest-failure disclosure | Every unrecoverable case listed in README with the agent's own explanation (not the author's). |
| **M10** | Clean-room run | Fresh clone + `.env` only -> `eval/` runs to completion; metrics within stated variance. |

## 6. Coverage & Gates
- Unit + integration: **>=85% line coverage on `src/`** before any real-LLM eval run.
- Commit gate: `ruff check . && ruff format --check . && mypy --strict src && pytest -q` — all green (enforced by `pre-commit`).
- E2E tagged `@pytest.mark.e2e`; excluded from default `pytest` run; invoked via `python -m eval.run_eval`.
- Flakiness policy: any non-determinism in unit/integration tests is a bug. Determinism via `MockProvider` + seeded `flaky_net`.

## 7. Deliverable Mapping (assignment requirement -> tests)
| Requirement | Tests |
|------------|-------|
| ReAct trace inspectable | M1; `test_logger` schema test |
| Working memory explicit | `test_working_memory`; integration happy path |
| Typed & validated tools | `test_tools_base`; integration `test_schema_violation_path` |
| >=3 failure modes + distinct recovery | `test_taxonomy`, `test_strategies` (distinctness), e2e traces |
| Replan budget + unresolvable | `test_controller::test_escalation_after_N`; integration `test_F5`; M8 |
| Flaky tool recovery | `test_flaky_net`; integration `test_F1_recover`; M4 |
| >=10 runs + metrics | `eval/run_eval.py` -> `metrics.*` |
| >=3 traced cases | README extracts from `reports/` |
| Baseline comparison | `eval/run_eval.py` runs both variants; `comparison.md` |
| Structured logs + viewer | `test_logger`; `test_viewer`; viewer renders |

## 8. Test Isolation & Hygiene
- Each integration test gets its own `tmp_path` workspace; no cross-test file leakage.
- `conftest.py` globally sets `ANSI_COLORS_DISABLE=1` for deterministic log captures.
- Scripted providers for HTTP in router tests; no real network in unit/integration.
- E2E uses real network; gated behind env var `HEVA_E2E=1` so default CI does not require keys.
