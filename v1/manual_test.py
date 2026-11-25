import tempfile
from pathlib import Path

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.config import RECOVERY_BUDGET_PER_SUBTASK
from backend.llm.router import LLMRouter
from backend.tools.code_exec import RunPythonTool
from backend.tools.file_io import ReadFileTool, WriteFileTool
from backend.tools.flaky_net import FlakyNetTool
from backend.tools.spec_check import SpecCheckTool
from backend.tools.test_run import RunTestsTool


def build_tools(workspace: Path):
    return [
        WriteFileTool(workspace=workspace),
        ReadFileTool(workspace=workspace),
        RunPythonTool(workspace=workspace),
        RunTestsTool(workspace=workspace),
        SpecCheckTool(),
        FlakyNetTool(),
    ]

def main():
    print("===============================================")
    print(" Sentinel AI - Manual CLI Tester ")
    print("===============================================")
    print("This script will run your custom goal through the REAL multi-LLM chain")
    print("configured in your .env file.")
    print("===============================================\n")

    goal_spec = input(
        "Enter your goal/prompt\n"
        "(e.g. 'Write a python script that prints hello world'):\n> "
    )
    if not goal_spec.strip():
        print("No goal provided. Exiting.")
        return

    print("\n[INFO] Initializing LLM Router with real providers from .env...")
    router = LLMRouter() # By default it uses config.LLM_CHAIN

    if not router._providers:
        print("[ERROR] No LLM providers configured. Please check your .env file.")
        return

    print(f"[INFO] Active LLM Chain: {[p.name for p in router._providers]}")

    with tempfile.TemporaryDirectory(prefix="sentinel_manual_test_") as workspace_dir:
        ws = Path(workspace_dir)
        print(f"[INFO] Created temporary workspace: {ws}")

        tools = build_tools(ws)
        runner = AgentRunner(
            router=router,
            tools=tools,
            budget_per_subtask=RECOVERY_BUDGET_PER_SUBTASK,
            self_correction_enabled=True,
        )

        goal = Goal(
            id="manual_test_01",
            spec=goal_spec,
            acceptance=["Goal is completed to the user's satisfaction"],
        )

        # We'll just define 5 generic steps for the plan
        plan_descs = [f"Step {i + 1}" for i in range(5)]

        print("\n[INFO] Starting Agent Loop...\n")
        try:
            memory = runner.run(goal, plan_descs)

            print("\n===============================================")
            print(" Agent Run Complete ")
            print("===============================================")
            print(f"Final output: {memory.final_output}")
            print(f"Total Steps: {len(memory.executed)}")
            print(f"Self-Corrections: {len(memory.corrections)}")

            report_path = Path("manual_run_report.json")
            report_path.write_text(memory.to_json(), encoding="utf-8")
            print(f"\n[INFO] Saved full detailed run report to: {report_path.absolute()}")

        except Exception as e:
            print(f"\n[ERROR] Agent run failed with exception: {e}")

if __name__ == "__main__":
    main()

