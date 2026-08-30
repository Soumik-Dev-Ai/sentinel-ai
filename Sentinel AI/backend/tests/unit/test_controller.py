"""Unit tests for the recovery controller â€” budget enforcement and routing."""

from __future__ import annotations

from backend.ai_agent.working_memory import (
    FailureMode,
    Goal,
    WorkingMemory,
)
from backend.recovery.controller import RecoveryController


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="T", spec="test"), ["s1", "s2"], 3)


def test_budget_decrements_on_correction() -> None:
    mem = _mem()
    ctrl = RecoveryController(budget_per_subtask=3)
    before = mem.get_budget("S1")
    ctrl.recover(
        mode=FailureMode.TOOL_FAILURE,
        memory=mem,
        action={"tool": "flaky_net", "args": {}},
        observation={"ok": False, "error_type": "tool_exception"},
        step_ix=1,
    )
    after = mem.get_budget("S1")
    assert after == before - 1


def test_escalation_after_n_corrections() -> None:
    mem = _mem()
    ctrl = RecoveryController(budget_per_subtask=2)
    for i in range(2):
        ctrl.recover(
            mode=FailureMode.TOOL_FAILURE,
            memory=mem,
            action={"tool": "flaky_net", "args": {}},
            observation={"ok": False, "error_type": "tool_exception"},
            step_ix=i + 1,
        )
    # budget now 0 -> next recover should escalate to BUDGET_EXCEEDED
    result = ctrl.recover(
        mode=FailureMode.TOOL_FAILURE,
        memory=mem,
        action={"tool": "flaky_net", "args": {}},
        observation={"ok": False, "error_type": "tool_exception"},
        step_ix=3,
    )
    assert result["mode"] == FailureMode.BUDGET_EXCEEDED.value
    assert result["unresolvable"] is True
    assert len(mem.unresolvable) == 1


def test_controller_routes_mode_to_correct_strategy() -> None:
    from backend.recovery.strategies import MUTATION_TARGETS

    for mode in FailureMode:
        expected = MUTATION_TARGETS[mode]
        actual = RecoveryController.get_mutation_target(mode)
        assert actual == expected, f"{mode}: expected {expected}, got {actual}"


def test_controller_never_loops_infinitely() -> None:
    """Even with repeated recovery calls, eventually terminates via F5."""
    mem = _mem()
    ctrl = RecoveryController(budget_per_subtask=2)
    max_iter = 20
    for i in range(max_iter):
        result = ctrl.recover(
            mode=FailureMode.TOOL_FAILURE,
            memory=mem,
            action={"tool": "flaky_net", "args": {}},
            observation={"ok": False, "error_type": "tool_exception"},
            step_ix=i + 1,
        )
        if result.get("unresolvable"):
            return  # successfully escalated
    raise AssertionError("Controller looped without escalating")


def test_recover_returns_mode_and_strategy() -> None:
    mem = _mem()
    ctrl = RecoveryController(budget_per_subtask=3)
    result = ctrl.recover(
        mode=FailureMode.GOAL_DRIFT,
        memory=mem,
        action={"tool": "write_file", "args": {}},
        observation={"ok": True, "result": {}},
        step_ix=1,
    )
    assert result["mode"] == FailureMode.GOAL_DRIFT.value
    assert "strategy" in result
    assert result["object_mutated"] == "plan"

