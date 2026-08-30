"""Unit tests for recovery strategies and their distinct mutation targets."""

from __future__ import annotations

from backend.ai_agent.working_memory import FailureMode, Goal, SubtaskStatus, WorkingMemory
from backend.recovery.strategies import (
    MUTATION_TARGETS,
    STRATEGY_MAP,
    strategy_budget_exceeded,
    strategy_goal_drift,
    strategy_insufficient_information,
    strategy_result_inconsistency,
    strategy_tool_failure,
)


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="T", spec="test"), ["task1", "task2"], 3)


def test_tool_failure_reinvokes_with_hardened_args() -> None:
    mem = _mem()
    result = strategy_tool_failure(
        mem,
        {"tool": "flaky_net", "args": {"timeout": 10, "package": "foo"}},
        {"ok": False, "error_type": "tool_exception"},
        step_ix=1,
    )
    assert result["object_mutated"] == "call"
    assert result["new_action"]["args"]["timeout"] >= 10
    assert mem.corrections[0].mutated_object == "call"


def test_result_inconsistency_emits_probe() -> None:
    mem = _mem()
    result = strategy_result_inconsistency(
        mem,
        {"tool": "run_python", "args": {"path": "parse.py"}},
        {"ok": True, "result": {"count": 7}},
        step_ix=2,
    )
    assert result["object_mutated"] == "facts"
    assert result["probe_action"]["tool"] == "run_python"


def test_goal_drift_discards_plan_tail() -> None:
    mem = _mem()
    mem.advance_subtask()
    result = strategy_goal_drift(
        mem,
        {"tool": "write_file", "args": {}},
        {"ok": True, "result": {}},
        step_ix=3,
    )
    assert result["object_mutated"] == "plan"
    assert any(s.id.startswith("R3") for s in mem.plan)


def test_insufficient_info_spawns_gather_subtask() -> None:
    mem = _mem()
    result = strategy_insufficient_information(
        mem,
        {"tool": "run_python", "args": {"path": "mod.py"}},
        {"ok": True, "result": {}},
        step_ix=4,
    )
    assert result["object_mutated"] == "plan+scope"
    assert any(s.id == "G4" for s in mem.plan)


def test_budget_exceeded_writes_unresolvable_record() -> None:
    mem = _mem()
    result = strategy_budget_exceeded(
        mem,
        {"tool": "write_file", "args": {}},
        {"ok": True, "result": {}},
        step_ix=5,
    )
    assert result["object_mutated"] == "stop"
    assert mem.unresolvable[0].subtask_id == "S1"
    assert mem.plan[0].status == SubtaskStatus.UNRESOLVABLE


def test_each_strategy_mutates_distinct_object() -> None:
    targets = set(MUTATION_TARGETS.values())
    assert targets == {"call", "facts", "plan", "plan+scope", "stop"}


def test_no_strategy_mutates_two_objects_at_once() -> None:
    test_actions = [
        strategy_tool_failure,
        strategy_result_inconsistency,
        strategy_goal_drift,
        strategy_insufficient_information,
        strategy_budget_exceeded,
    ]
    mem = _mem()
    for strat_fn in test_actions:
        result = strat_fn(
            mem,
            {"tool": "run_python", "args": {"path": "x.py"}},
            {"ok": False, "error_type": "test"},
            step_ix=1,
        )
        mutated = result["object_mutated"]
        assert mutated in MUTATION_TARGETS.values(), f"{strat_fn}: mutated={mutated}"


def test_strategy_map_has_all_five_modes() -> None:
    assert set(STRATEGY_MAP) == set(FailureMode)

