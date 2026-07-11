"""Unit tests for the self-evaluator."""

from __future__ import annotations

from backend.ai_agent.self_evaluator import SelfEvaluator
from backend.ai_agent.working_memory import Goal, WorkingMemory


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="E1", spec="test"), ["task1"], 3)


def test_evaluate_success_returns_no_mode() -> None:
    result = SelfEvaluator().evaluate(
        goal_spec="test",
        acceptance=[],
        action={"tool": "write_file", "args": {}},
        observation={"ok": True, "result": {}},
        memory=_mem(),
    )
    assert result["success"] is True
    assert result["mode"] is None


def test_evaluate_tool_failure_returns_mode() -> None:
    result = SelfEvaluator().evaluate(
        goal_spec="test",
        acceptance=[],
        action={"tool": "flaky_net", "args": {}},
        observation={"ok": False, "error_type": "tool_exception"},
        memory=_mem(),
    )
    assert result["success"] is False
    assert result["mode"] is not None

