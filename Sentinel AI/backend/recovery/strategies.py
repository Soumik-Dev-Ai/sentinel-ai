from __future__ import annotations

from collections.abc import Callable
try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from typing import Any

from backend import config
from backend.ai_agent.working_memory import (
    CorrectionRecord,
    FailureMode,
    Subtask,
    WorkingMemory,
)


def strategy_tool_failure(
    memory: WorkingMemory, action: dict[str, Any], observation: dict[str, Any], step_ix: int
) -> dict[str, Any]:
    active = memory.active_subtask
    if active is None:
        return {"object_mutated": "call", "new_action": None}
    budget = memory.decrement_budget(active.id)
    error_type = observation.get("error_type", "unknown")
    evidence = f"Tool {action.get('tool', '?')} failed: {error_type}"
    new_args = dict(action.get("args", {}))
    if "timeout" in new_args:
        new_args["timeout"] = min(int(new_args["timeout"]) * 2, 60)
    else:
        new_args["timeout"] = 60
    new_action = {"tool": action.get("tool", ""), "args": new_args}
    if error_type == "shape_violation" or budget <= 0:
        new_action = {"tool": "std_fallback", "args": new_args}
        evidence += " -- substituting fallback tool"
    rec = CorrectionRecord(
        ts=datetime.now(UTC).isoformat(),
        step_ix=step_ix,
        mode=FailureMode.TOOL_FAILURE.value,
        strategy="tool_failure",
        mutated_object="call",
        budget_after=budget,
        evidence=evidence,
    )
    memory.add_correction(rec)
    return {"object_mutated": "call", "new_action": new_action}


def strategy_result_inconsistency(
    memory: WorkingMemory, action: dict[str, Any], observation: dict[str, Any], step_ix: int
) -> dict[str, Any]:
    active = memory.active_subtask
    if active is None:
        return {"object_mutated": "facts"}
    budget = memory.decrement_budget(active.id)
    evidence = "Result inconsistent with prior findings or spec"
    probe_action = {
        "tool": "run_python",
        "args": {
            "path": action.get("args", {}).get("path", ""),
            "timeout": 30,
        },
    }
    rec = CorrectionRecord(
        ts=datetime.now(UTC).isoformat(),
        step_ix=step_ix,
        mode=FailureMode.RESULT_INCONSISTENCY.value,
        strategy="result_inconsistency",
        mutated_object="facts",
        budget_after=budget,
        evidence=evidence,
    )
    memory.add_correction(rec)
    memory.world_model.facts["inconsistency_flag"] = True
    return {"object_mutated": "facts", "probe_action": probe_action}


def strategy_goal_drift(
    memory: WorkingMemory, action: dict[str, Any], observation: dict[str, Any], step_ix: int
) -> dict[str, Any]:
    active = memory.active_subtask
    if active is None:
        return {"object_mutated": "plan"}
    budget = memory.decrement_budget(active.id)
    new_subtasks = [
        Subtask(id=f"R{step_ix}a", desc="Re-analyze goal and current findings"),
        Subtask(id=f"R{step_ix}b", desc="Generate revised implementation plan"),
    ]
    active_idx = next((i for i, s in enumerate(memory.plan) if s.id == active.id), 0)
    memory.replace_plan_from(active_idx, new_subtasks, config.RECOVERY_BUDGET_PER_SUBTASK)
    memory.activate_first()
    evidence = f"Goal drift detected at step {step_ix}; plan regenerated from step {active_idx}"
    rec = CorrectionRecord(
        ts=datetime.now(UTC).isoformat(),
        step_ix=step_ix,
        mode=FailureMode.GOAL_DRIFT.value,
        strategy="goal_drift",
        mutated_object="plan",
        new_plan=[{"id": s.id, "desc": s.desc} for s in new_subtasks],
        budget_after=budget,
        evidence=evidence,
    )
    memory.add_correction(rec)
    return {"object_mutated": "plan", "new_subtasks": [s.id for s in new_subtasks]}


def strategy_insufficient_information(
    memory: WorkingMemory, action: dict[str, Any], observation: dict[str, Any], step_ix: int
) -> dict[str, Any]:
    active = memory.active_subtask
    if active is None:
        return {"object_mutated": "plan+scope"}
    budget = memory.decrement_budget(active.id)
    gather = Subtask(
        id=f"G{step_ix}",
        desc=f"Gather missing info: read {action.get('args', {}).get('path', 'file')}",
    )
    memory.insert_subtask_before_active(gather, config.RECOVERY_BUDGET_PER_SUBTASK)
    memory.activate_first()
    rec = CorrectionRecord(
        ts=datetime.now(UTC).isoformat(),
        step_ix=step_ix,
        mode=FailureMode.INSUFFICIENT_INFORMATION.value,
        strategy="insufficient_info",
        mutated_object="plan+scope",
        new_plan=[{"id": gather.id, "desc": gather.desc}],
        budget_after=budget,
        evidence="Missing world_model entry for target file; inserted gather subtask",
    )
    memory.add_correction(rec)
    return {"object_mutated": "plan+scope", "gather_subtask": gather.id}


def strategy_budget_exceeded(
    memory: WorkingMemory, action: dict[str, Any], observation: dict[str, Any], step_ix: int
) -> dict[str, Any]:
    active = memory.active_subtask
    if active is None:
        return {"object_mutated": "stop"}
    modes = [c.mode for c in memory.corrections if c.step_ix <= step_ix][-3:]
    evidence = f"Budget exhausted for {active.id} after {len(modes)} attempts"
    memory.mark_unresolvable(
        subtask_id=active.id,
        modes=modes,
        attempts=len(modes),
        evidence=evidence,
        hypothesis=f"Subtask {active.id} may be unreachable with current tools/plan",
    )
    rec = CorrectionRecord(
        ts=datetime.now(UTC).isoformat(),
        step_ix=step_ix,
        mode=FailureMode.BUDGET_EXCEEDED.value,
        strategy="budget_exceeded",
        mutated_object="stop",
        budget_after=0,
        evidence=evidence,
    )
    memory.add_correction(rec)
    from backend.ai_agent.working_memory import SubtaskStatus

    next_pending = [s for s in memory.plan if s.status == SubtaskStatus.PENDING]
    if next_pending:
        next_pending[0].status = SubtaskStatus.ACTIVE
    return {"object_mutated": "stop", "unresolvable": True}


STRATEGY_MAP: dict[FailureMode, Callable[..., dict[str, Any]]] = {
    FailureMode.TOOL_FAILURE: strategy_tool_failure,
    FailureMode.RESULT_INCONSISTENCY: strategy_result_inconsistency,
    FailureMode.GOAL_DRIFT: strategy_goal_drift,
    FailureMode.INSUFFICIENT_INFORMATION: strategy_insufficient_information,
    FailureMode.BUDGET_EXCEEDED: strategy_budget_exceeded,
}

MUTATION_TARGETS: dict[FailureMode, str] = {
    FailureMode.TOOL_FAILURE: "call",
    FailureMode.RESULT_INCONSISTENCY: "facts",
    FailureMode.GOAL_DRIFT: "plan",
    FailureMode.INSUFFICIENT_INFORMATION: "plan+scope",
    FailureMode.BUDGET_EXCEEDED: "stop",
}


