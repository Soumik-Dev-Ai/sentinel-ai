from __future__ import annotations

from typing import Any

from backend.ai_agent.working_memory import FailureMode, WorkingMemory
from backend.recovery.taxonomy import classify
from backend.tools.base import is_tool_failure_result


class SelfEvaluator:
    def __init__(self, alignment_threshold: float = 0.5):
        self._threshold = alignment_threshold
        self._prev_alignment: float | None = None

    def evaluate(
        self,
        goal_spec: str,
        acceptance: list[str],
        action: dict[str, Any],
        observation: dict[str, Any],
        memory: WorkingMemory,
    ) -> dict[str, Any]:
        tool_ok = isinstance(observation, dict) and observation.get("ok") is True
        no_error = not is_tool_failure_result(observation)

        success = tool_ok and no_error
        coherence = 0.8 if success else 0.2

        plan_valid = True
        active = memory.active_subtask
        if active is not None:
            desc_lower = active.desc.lower()
            if "test" in desc_lower and isinstance(observation, dict):
                result = observation.get("result", {})
                if isinstance(result, dict) and "tests_passed" in result:
                    plan_valid = result.get("tests_passed", False)

        goal_alignment = coherence if plan_valid else coherence * 0.5

        mode = classify(
            action=action,
            observation=observation,
            memory=memory,
            goal_alignment_score=goal_alignment,
            prev_alignment_score=self._prev_alignment,
            alignment_threshold=self._threshold,
        )

        self._prev_alignment = goal_alignment

        return {
            "success": success and plan_valid,
            "coherence": round(coherence, 3),
            "plan_valid": plan_valid,
            "mode": mode.value if mode else None,
            "evidence": self._build_evidence(action, observation, mode),
            "goal_alignment": round(goal_alignment, 3),
        }

    @staticmethod
    def _build_evidence(
        action: dict[str, Any], obs: dict[str, Any], mode: FailureMode | None
    ) -> str:
        tool_name = action.get("tool", "?")
        if mode is None:
            return f"Step with {tool_name} succeeded; plan still valid"
        if mode == FailureMode.TOOL_FAILURE:
            err = obs.get("error_type", "unknown") if isinstance(obs, dict) else "unknown"
            return f"Tool {tool_name} failed ({err})"
        if mode == FailureMode.RESULT_INCONSISTENCY:
            return f"Tool {tool_name} succeeded but result inconsistent with findings/spec"
        if mode == FailureMode.GOAL_DRIFT:
            return "Goal alignment below threshold for 2+ consecutive steps"
        if mode == FailureMode.INSUFFICIENT_INFORMATION:
            return "Required file/data missing from world_model"
        if mode == FailureMode.BUDGET_EXCEEDED:
            return "Recovery budget for this subtask is exhausted"
        return f"Unknown mode {mode}"

