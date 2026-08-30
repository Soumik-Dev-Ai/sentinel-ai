from __future__ import annotations

from typing import Any

from backend.ai_agent.working_memory import (
    FailureMode,
    WorkingMemory,
)


def classify(
    action: dict[str, Any],
    observation: dict[str, Any],
    memory: WorkingMemory,
    goal_alignment_score: float,
    prev_alignment_score: float | None,
    alignment_threshold: float = 0.5,
) -> FailureMode | None:
    if not isinstance(observation, dict):
        return FailureMode.TOOL_FAILURE

    if observation.get("ok") is False:
        return FailureMode.TOOL_FAILURE

    active = memory.active_subtask
    if active is not None and memory.get_budget(active.id) <= 0:
        return FailureMode.BUDGET_EXCEEDED

    if prev_alignment_score is not None and (
        goal_alignment_score < alignment_threshold and prev_alignment_score < alignment_threshold
    ):
        return FailureMode.GOAL_DRIFT

    result = observation.get("result", {}) if observation.get("ok") else {}
    if isinstance(result, dict):
        for _key, finding in memory.findings.items():
            fval = finding.value
            if isinstance(fval, dict) and isinstance(result, dict):
                for fk, fv in fval.items():
                    if fk in result and result[fk] != fv:
                        return FailureMode.RESULT_INCONSISTENCY

    tool_name = action.get("tool", "")
    args = action.get("args", {})
    if tool_name in ("write_file", "run_python"):
        target_path = args.get("path", "")
        if target_path and not memory.world_model.has_file(target_path):
            return FailureMode.INSUFFICIENT_INFORMATION

    return None


def classify_for_eval(
    action: dict[str, Any],
    observation: dict[str, Any],
    plan_valid: bool,
    success: bool,
    goal_alignment: float,
    prev_alignment: float | None,
    memory: WorkingMemory,
) -> FailureMode | None:
    if not success:
        return classify(action, observation, memory, goal_alignment, prev_alignment)
    if not plan_valid:
        return FailureMode.GOAL_DRIFT
    return None

