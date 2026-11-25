"""Baseline variant: ReAct loop with self-correction DISABLED.

This module provides a convenience wrapper around AgentRunner with
self_correction_enabled=False, so eval/run_eval.py can run both variants
on identical goals and tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.run_eval import build_tools
from src.agent.runner import AgentRunner
from src.agent.working_memory import Goal
from src.llm.router import LLMRouter


def run_baseline(
    goals: list[dict[str, Any]],
    router: LLMRouter,
    output_dir: Path,
    budget: int,
) -> list[dict[str, Any]]:
    import tempfile

    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics: list[dict[str, Any]] = []
    for goal_data in goals:
        with tempfile.TemporaryDirectory(prefix=f"baseline_{goal_data['id']}_") as workspace:
            ws = Path(workspace)
            pre = goal_data.get("pre_setup")
            if pre:
                fname = pre.get("create_file", "")
                content = pre.get("content", "")
                if fname and content:
                    fp = ws / fname
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(content, encoding="utf-8")
            tools = build_tools(ws)
            runner = AgentRunner(
                router=router,
                tools=tools,
                budget_per_subtask=budget,
                self_correction_enabled=False,
            )
            goal = Goal(
                id=goal_data["id"],
                spec=goal_data["spec"],
                acceptance=goal_data.get("acceptance", []),
            )
            plan_descs = [f"Step {i + 1}" for i in range(goal_data.get("min_steps", 5))]
            memory = runner.run(goal, plan_descs)
            (output_dir / f"{goal_data['id']}_{memory.run_id}.json").write_text(
                memory.to_json(), encoding="utf-8"
            )
            m = memory.to_metrics()
            all_metrics.append(
                {
                    "run_id": memory.run_id,
                    "goal_id": goal_data["id"],
                    "steps": m.get("steps", 0),
                    "self_corrections": m.get("self_corrections", 0),
                    "provider_switches": m.get("provider_switches", 0),
                    "unresolvable_count": m.get("unresolvable_count", 0),
                    "completed": memory.final_output is not None,
                }
            )
    return all_metrics
