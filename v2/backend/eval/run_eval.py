from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.metrics import (
    load_goals,
    write_comparison_md,
    write_metrics_csv,
    write_metrics_md,
)

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.config import RECOVERY_BUDGET_PER_SUBTASK
from backend.llm.router import LLMRouter
from backend.tools.code_exec import RunPythonTool
from backend.tools.file_io import ReadFileTool, WriteFileTool
from backend.tools.flaky_net import FlakyNetTool
from backend.tools.spec_check import SpecCheckTool
from backend.tools.test_run import RunTestsTool


def build_tools(workspace: Path) -> list[Any]:
    return [
        WriteFileTool(workspace=workspace),
        ReadFileTool(workspace=workspace),
        RunPythonTool(workspace=workspace),
        RunTestsTool(workspace=workspace),
        SpecCheckTool(),
        FlakyNetTool(),
    ]


def run_variant(
    goals: list[dict[str, Any]],
    variant: str,
    output_dir: Path,
    self_correction: bool,
    router: LLMRouter,
    budget: int,
) -> list[dict[str, Any]]:
    import tempfile

    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics: list[dict[str, Any]] = []
    for goal_data in goals:
        with tempfile.TemporaryDirectory(prefix=f"eval_{variant}_{goal_data['id']}_") as workspace:
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
                self_correction_enabled=self_correction,
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
            all_metrics.append(compute_metrics_from_memory(memory, goal_data["id"]))
    return all_metrics


def compute_metrics_from_memory(memory: Any, goal_id: str) -> dict[str, Any]:
    m = memory.to_metrics()
    return {
        "run_id": memory.run_id,
        "goal_id": goal_id,
        "steps": m.get("steps", 0),
        "self_corrections": m.get("self_corrections", 0),
        "provider_switches": m.get("provider_switches", 0),
        "unresolvable_count": m.get("unresolvable_count", 0),
        "completed": memory.final_output is not None,
    }


def main() -> None:
    workspace_root = Path(__file__).resolve().parent.parent
    goals_path = workspace_root / "eval" / "goals.yaml"
    goals = load_goals(goals_path)
    reports_dir = workspace_root / "eval" / "reports"
    sc_dir = reports_dir / "self_correcting"
    bl_dir = reports_dir / "baseline"

    from typing import Any as TypingAny

    from backend.llm.contracts import Provider, Reply

    class StubProvider(Provider):
        @property
        def name(self) -> str:
            return "stub"

        def chat(
            self,
            messages: list[dict[str, TypingAny]],
            tools=None,
            response_schema=None,
        ) -> Reply:
            return Reply(
                thought="I will write the file first, then run it.",
                action={
                    "tool": "write_file",
                    "args": {"path": "output.py", "content": "print('hello')"},
                },
                finish_reason="stop",
            )

    router = LLMRouter(providers=[StubProvider()])
    budget = RECOVERY_BUDGET_PER_SUBTASK

    print(f"Running self-correcting variant on {len(goals)} goals...")
    sc_metrics = run_variant(goals, "self_correcting", sc_dir, True, router, budget)

    print(f"Running baseline variant on {len(goals)} goals...")
    bl_metrics = run_variant(goals, "baseline", bl_dir, False, router, budget)

    write_metrics_csv(sc_metrics, reports_dir / "metrics.csv")
    write_metrics_md(sc_metrics, reports_dir / "metrics.md")
    write_comparison_md(sc_metrics, bl_metrics, reports_dir / "comparison.md")
    print(f"Reports written to {reports_dir}")


if __name__ == "__main__":
    main()

