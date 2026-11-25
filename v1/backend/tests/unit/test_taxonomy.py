"""Unit tests for failure-mode taxonomy classification."""

from __future__ import annotations

from backend.ai_agent.working_memory import FailureMode, Goal, WorkingMemory
from backend.recovery.taxonomy import classify, classify_for_eval


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="T", spec="test"), ["s1", "s2"], 3)


def test_classify_tool_failure_exit_nonzero() -> None:
    mem = _mem()
    obs = {"ok": False, "error_type": "tool_exception", "tool": "run_python"}
    mode = classify(
        action={"tool": "run_python", "args": {}},
        observation=obs,
        memory=mem,
        goal_alignment_score=0.3,
        prev_alignment_score=None,
    )
    assert mode == FailureMode.TOOL_FAILURE


def test_classify_schema_violation() -> None:
    mem = _mem()
    obs = {"ok": False, "error_type": "shape_violation", "tool": "flaky_net"}
    mode = classify(
        action={"tool": "flaky_net", "args": {}},
        observation=obs,
        memory=mem,
        goal_alignment_score=0.3,
        prev_alignment_score=None,
    )
    assert mode == FailureMode.TOOL_FAILURE


def test_classify_goal_drift_two_low_steps() -> None:
    mode = classify(
        action={"tool": "write_file", "args": {}},
        observation={"ok": True, "result": {}},
        memory=_mem(),
        goal_alignment_score=0.3,
        prev_alignment_score=0.2,
        alignment_threshold=0.5,
    )
    assert mode == FailureMode.GOAL_DRIFT


def test_classify_budget_zero() -> None:
    mem = _mem()
    for _ in range(3):
        mem.decrement_budget("S1")
    mode = classify(
        action={"tool": "write_file", "args": {}},
        observation={"ok": True, "result": {}},
        memory=mem,
        goal_alignment_score=0.8,
        prev_alignment_score=None,
    )
    assert mode == FailureMode.BUDGET_EXCEEDED


def test_classify_insufficient_information() -> None:
    mode = classify(
        action={"tool": "run_python", "args": {"path": "unknown.py"}},
        observation={"ok": True, "result": {}},
        memory=_mem(),
        goal_alignment_score=0.8,
        prev_alignment_score=None,
    )
    assert mode == FailureMode.INSUFFICIENT_INFORMATION


def test_classify_result_inconsistency() -> None:
    mem = _mem()
    mem.add_finding("S1", "count", {"row_count": 10})
    mode = classify(
        action={"tool": "run_python", "args": {"path": "parse.py"}},
        observation={"ok": True, "result": {"row_count": 7}},
        memory=mem,
        goal_alignment_score=0.7,
        prev_alignment_score=None,
    )
    assert mode == FailureMode.RESULT_INCONSISTENCY


def test_classify_happy_path_returns_none() -> None:
    mem = _mem()
    mem.world_model.record_file("fib.py", "print('hi')")
    mode = classify(
        action={"tool": "run_python", "args": {"path": "fib.py"}},
        observation={"ok": True, "result": {"exit_code": 0, "stdout": "hi"}},
        memory=mem,
        goal_alignment_score=0.9,
        prev_alignment_score=0.9,
    )
    assert mode is None


def test_classify_for_eval_plan_invalid_returns_goal_drift() -> None:
    assert (
        classify_for_eval(
            action={"tool": "write_file", "args": {}},
            observation={"ok": True, "result": {}},
            plan_valid=False,
            success=True,
            goal_alignment=0.7,
            prev_alignment=None,
            memory=_mem(),
        )
        == FailureMode.GOAL_DRIFT
    )

