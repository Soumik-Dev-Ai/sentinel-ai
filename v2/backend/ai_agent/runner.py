from __future__ import annotations

from pathlib import Path
from typing import Any

from backend import config
from backend.ai_agent.react import react_step
from backend.ai_agent.self_evaluator import SelfEvaluator
from backend.ai_agent.working_memory import Goal, WorkingMemory
from backend.llm.router import LLMRouter
from backend.recovery.controller import RecoveryController
from backend.tools.base import ToolProtocol, is_tool_failure_result


class AgentRunner:
    def __init__(
        self,
        router: LLMRouter,
        tools: list[ToolProtocol],
        budget_per_subtask: int | None = None,
        max_steps: int | None = None,
        self_correction_enabled: bool = True,
        callbacks: dict[str, Any] | None = None,
    ):
        self._router = router
        self._tools = {t.name: t for t in tools}
        self._evaluator = SelfEvaluator()
        self._controller = RecoveryController(budget_per_subtask)
        self._budget = budget_per_subtask or config.RECOVERY_BUDGET_PER_SUBTASK
        self._max_steps = max_steps or config.MAX_AGENT_STEPS
        self._self_correction_enabled = self_correction_enabled
        self._callbacks = callbacks or {}

    def run(self, goal: Goal, plan_descs: list[str]) -> WorkingMemory:
        memory = WorkingMemory.from_goal(goal, plan_descs, self._budget)
        memory.provider_events = list(self._router.provider_events)

        for _ in range(self._max_steps):
            if memory.is_finished():
                break

            try:
                if "step_started" in self._callbacks:
                    self._callbacks["step_started"](len(memory.executed) + 1)
                
                reply = react_step(
                    memory, 
                    self._router, 
                    list(self._tools.values()),
                    stream_callback=self._callbacks.get("stream_callback")
                )
            except Exception as exc:
                memory.final_output = (
                    f"Agent crashed during react step: {type(exc).__name__}: {exc}"
                )
                break
            if reply.action is None:
                memory.final_output = "No action produced by LLM"
                break

            tool_name = reply.action.get("tool", "")
            tool_args = reply.action.get("args", {})

            tool = self._tools.get(tool_name)
            if tool is None:
                observation = {
                    "ok": False,
                    "error_type": "tool_not_found",
                    "tool": tool_name,
                    "details": f"No tool named '{tool_name}'",
                }
            else:
                try:
                    observation = tool.invoke(tool_args)
                except Exception as exc:
                    observation = {
                        "ok": False,
                        "error_type": "tool_crash",
                        "tool": tool_name,
                        "details": f"{type(exc).__name__}: {exc}",
                    }

            if not self._self_correction_enabled:
                eval_result = {
                    "success": not is_tool_failure_result(observation),
                    "coherence": 0.8,
                    "plan_valid": True,
                    "mode": None,
                    "evidence": "Self-correction disabled (baseline)",
                    "goal_alignment": 0.8,
                }
            else:
                eval_result = self._evaluator.evaluate(
                    goal_spec=goal.spec,
                    acceptance=goal.acceptance,
                    action=reply.action,
                    observation=observation,
                    memory=memory,
                )

            memory.record_step(
                thought=reply.thought,
                tool=tool_name,
                args=tool_args,
                result=observation,
                eval_result=eval_result,
            )
            step_ix = len(memory.executed)
            last_step = memory.executed[-1]

            if "step_completed" in self._callbacks:
                self._callbacks["step_completed"](
                    tool_name,
                    not is_tool_failure_result(observation),
                    reply.thought,
                    step_ix,
                )
            if "step_recorded" in self._callbacks:
                self._callbacks["step_recorded"](last_step.to_dict())
            if tool_name == "write_file" and "file_updated" in self._callbacks:
                path = tool_args.get("path", "")
                if isinstance(observation, dict) and path:
                    self._callbacks["file_updated"](path, tool_args.get("content", ""))

            memory.provider_events = list(self._router.provider_events)

            # Check for provider switches and emit callback
            if "provider_switched" in self._callbacks:
                prev_len = len(memory.provider_events)
                cur_len = len(self._router.provider_events)
                if cur_len > prev_len:
                    new_events = self._router.provider_events[prev_len:]
                    for ev in new_events:
                        self._callbacks["provider_switched"](
                            ev.get("from", "?"),
                            ev.get("to", "?"),
                            ev.get("reason", "?"),
                        )
                    memory.provider_events = list(self._router.provider_events)

            if eval_result["success"] and eval_result["plan_valid"]:
                memory.advance_subtask()
                if "subtask_advanced" in self._callbacks and memory.active_subtask:
                    self._callbacks["subtask_advanced"](memory.active_subtask.to_dict())
            elif self._self_correction_enabled and isinstance(
                (mode_raw := eval_result.get("mode")), str
            ):
                from backend.ai_agent.working_memory import FailureMode

                mode = FailureMode(mode_raw)
                result = self._controller.recover(
                    mode=mode,
                    memory=memory,
                    action=reply.action,
                    observation=observation,
                    step_ix=len(memory.executed),
                )
                if result.get("unresolvable"):
                    memory.advance_subtask()
                elif result.get("new_action"):
                    corrected = result["new_action"]
                    corrected_tool_name = corrected.get("tool", "")
                    corrected_tool_args = corrected.get("args", {})
                    corrected_tool = self._tools.get(corrected_tool_name)
                    if corrected_tool is not None:
                        observation = corrected_tool.invoke(corrected_tool_args)
                        eval_result = self._evaluator.evaluate(
                            goal_spec=goal.spec,
                            acceptance=goal.acceptance,
                            action=corrected,
                            observation=observation,
                            memory=memory,
                        )
                        memory.record_step(
                            thought=f"[recovery re-invoke] {result.get('strategy', '')}",
                            tool=corrected_tool_name,
                            args=corrected_tool_args,
                            result=observation,
                            eval_result=eval_result,
                            correction_trigger=result.get("mode", ""),
                        )
                        if eval_result["success"] and eval_result["plan_valid"]:
                            memory.advance_subtask()
                if "correction_applied" in self._callbacks and memory.corrections:
                    self._callbacks["correction_applied"](
                        memory.corrections[-1].to_dict()
                    )
            elif not self._self_correction_enabled:
                memory.advance_subtask()

        try:
            if memory.final_output is None:
                final_parts = []
                for s in memory.plan:
                    if s.status.value == "done":
                        final_parts.append(f"[OK] {s.desc}")
                    elif s.status.value == "unresolvable":
                        final_parts.append(f"[UNRESOLVABLE] {s.desc}")
                    else:
                        final_parts.append(f"[{s.status.value.upper()}] {s.desc}")
                memory.final_output = "\n".join(final_parts)
        except Exception as exc:
            memory.final_output = f"Agent crashed after loop: {type(exc).__name__}: {exc}"

        memory.provider_events = list(self._router.provider_events)
        return memory

    def run_and_persist(
        self, goal: Goal, plan_descs: list[str], output_dir: Path | None = None
    ) -> WorkingMemory:
        memory = self.run(goal, plan_descs)
        out = output_dir or config.EVAL_REPORTS_DIR
        path = out / f"{goal.id}_{memory.run_id}.json"
        memory.persist(path)
        return memory


