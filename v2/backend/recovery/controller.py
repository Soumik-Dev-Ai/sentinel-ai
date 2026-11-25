from __future__ import annotations

from typing import Any

from backend.ai_agent.working_memory import FailureMode, WorkingMemory
from backend.recovery.strategies import STRATEGY_MAP


class RecoveryController:
    def __init__(self, budget_per_subtask: int | None = None):
        from backend import config

        self._default_budget = budget_per_subtask or config.RECOVERY_BUDGET_PER_SUBTASK

    def recover(
        self,
        mode: FailureMode,
        memory: WorkingMemory,
        action: dict[str, Any],
        observation: dict[str, Any],
        step_ix: int,
    ) -> dict[str, Any]:
        active = memory.active_subtask
        if active is not None and memory.get_budget(active.id) <= 0:
            mode = FailureMode.BUDGET_EXCEEDED

        strategy_fn = STRATEGY_MAP.get(mode)
        if strategy_fn is None:
            return {"object_mutated": "none", "error": f"No strategy for {mode}"}

        result = strategy_fn(memory, action, observation, step_ix)

        active_after = memory.active_subtask
        if (
            mode != FailureMode.BUDGET_EXCEEDED
            and active_after is not None
            and memory.get_budget(active_after.id) <= 0
        ):
            result = STRATEGY_MAP[FailureMode.BUDGET_EXCEEDED](
                memory,
                action,
                observation,
                step_ix,
            )
            mode = FailureMode.BUDGET_EXCEEDED

        result["mode"] = mode.value
        result["strategy"] = strategy_fn.__name__.replace("strategy_", "")
        return result

    @staticmethod
    def get_mutation_target(mode: FailureMode) -> str:
        from backend.recovery.strategies import MUTATION_TARGETS

        return MUTATION_TARGETS.get(mode, "unknown")


