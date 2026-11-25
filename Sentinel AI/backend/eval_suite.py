from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend import config
from backend.llm.router import LLMRouter
from backend.tools.code_exec import RunPythonTool
from backend.tools.file_io import ReadFileTool, WriteFileTool
from backend.tools.flaky_net import FlakyNetTool
from backend.tools.spec_check import SpecCheckTool
from backend.tools.test_run import RunTestsTool

EVAL_GOALS = [
    {
        "id": "goal_1",
        "spec": "Write a Python script 'hello.py' that prints 'Hello World'.",
        "input": ""
    },
    {
        "id": "goal_2",
        "spec": "Write a Python script 'math_op.py' that calculates the factorial of 10 and prints the result.",
        "input": ""
    },
    {
        "id": "goal_3",
        "spec": "Use the FlakyNetTool to fetch data from 'https://example.com' and write the HTML content to 'index.html'. If it fails, retry until it succeeds.",
        "input": ""
    },
    {
        "id": "goal_4",
        "spec": "Write a Python script 'file_read.py' that reads 'input.txt' and counts the number of lines, then prints the count.",
        "input": "Line 1\nLine 2\nLine 3"
    },
    {
        "id": "goal_5",
        "spec": "Write a Python script 'bad_syntax.py' that intentionally contains a syntax error (e.g. missing parenthesis on print), run it using RunPythonTool to observe the error, then fix the script to have correct syntax and print 'Syntax fixed', and run it again.",
        "input": ""
    },
    {
        "id": "goal_6",
        "spec": "Write a Python script 'fetch_todo.py' that uses the 'urllib.request' module to fetch JSON data from 'https://jsonplaceholder.typicode.com/todos/1', extract the 'title', and write it to 'todo.txt'. Run the script to generate the file.",
        "input": ""
    },
    {
        "id": "goal_7",
        "spec": "Write a Python script 'test_math.py' containing a function 'add(a, b)' and a test using 'assert add(2, 2) == 5'. Run the tests using RunTestsTool, observe the failure, and fix the assertion to equal 4. Run the tests again to ensure they pass.",
        "input": ""
    },
    {
        "id": "goal_8",
        "spec": "Write a Python script 'dir_list.py' that lists all files in the current directory using 'os' and writes the comma-separated list to 'files.txt'. Run the script.",
        "input": ""
    },
    {
        "id": "goal_9",
        "spec": "Use the SpecCheckTool to check the specification against the generated files. Wait, just write a file 'spec.md' with the content '# Project Spec'.",
        "input": ""
    },
    {
        "id": "goal_10",
        "spec": "Write a Python script 'calc_pi.py' that calculates an approximation of Pi using the Leibniz formula for 1000 iterations and prints the result. Run the script.",
        "input": ""
    }
]

import concurrent.futures
import traceback

def run_evaluation_suite(report_dir: Path | str, on_progress: Any = None, custom_goals: list[dict[str, Any]] = None) -> dict[str, Any]:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    run_name = f"eval_{timestamp}"
    run_dir = report_dir / run_name
    run_dir.mkdir()
    
    results = []
    goals_to_run = custom_goals if custom_goals else EVAL_GOALS
    
    total_runs = len(goals_to_run) * 2
    completed_runs = [0]
    shared_router = LLMRouter(provider_timeout=getattr(config, "PROVIDER_TIMEOUT_SECONDS", 90))
    
    def run_single_eval(goal_data: dict[str, Any], self_correction_enabled: bool) -> dict[str, Any]:
        workspace = Path(mkdtemp(prefix=f"eval_ws_{goal_data['id']}_"))
        if goal_data.get("input"):
            (workspace / "input.txt").write_text(goal_data["input"], encoding="utf-8")
            
        start_time = time.time()
        try:
            from backend.orchestrator.pipeline import MultiAgentPipeline
            from backend.orchestrator.escalation import EscalationManager

            pipeline = MultiAgentPipeline(
                router=shared_router,
                escalation=EscalationManager(timeout_seconds=10),
                config={
                    "max_retries_per_subtask": 3 if self_correction_enabled else 1,
                    "budget": 1000
                }
            )
            
            result = pipeline.run(
                goal=goal_data["spec"], 
                acceptance=[], 
                workspace=workspace, 
                input_text=goal_data.get("input", "")
            )
            elapsed = time.time() - start_time
            
            success = result.get("success", False)
            metrics = result.get("metrics", {})
            steps = result.get("steps_taken", 0)
            self_corrections = result.get("self_corrections", 0)
            
            # Convert MultiAgent trace into legacy ReAct steps for UI compatibility
            legacy_steps = []
            for st in result.get("subtasks", []):
                outcome = st.get("outcome", {})
                legacy_steps.append({
                    "thought": f"Subtask [{st.get('subtask_id', 'unknown')}]: {st.get('agent', 'coder')} assignment",
                    "tool": "MultiAgent",
                    "args": {"agent": st.get("agent", "unknown")},
                    "result": {"resolved": st.get("resolved"), "attempts": st.get("attempts")},
                    "correction_trigger": None
                })
            
            run_result = {
                "goal_id": goal_data["id"],
                "spec": goal_data["spec"],
                "self_correction_enabled": self_correction_enabled,
                "success": success,
                "steps": steps,
                "self_corrections": self_corrections,
                "elapsed_seconds": elapsed,
                "memory_dump": {
                    "final_output": result.get("final_output"),
                    "steps": legacy_steps
                }
            }
        except Exception as e:
            run_result = {
                "goal_id": goal_data["id"],
                "spec": goal_data["spec"],
                "self_correction_enabled": self_correction_enabled,
                "success": False,
                "steps": 0,
                "self_corrections": 0,
                "elapsed_seconds": 0,
                "memory_dump": {
                    "final_output": f"Agent crashed: {type(e).__name__}: {e}",
                    "steps": []
                }
            }
            
        # Save individual trace
        mode_str = "with_sc" if self_correction_enabled else "no_sc"
        trace_path = run_dir / f"{goal_data['id']}_{mode_str}.json"
        trace_path.write_text(json.dumps(run_result, indent=2), encoding="utf-8")
        
        return run_result

    # Sequential: free-tier rate limits (TPD/tokens-per-min) break under burst load.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = []
        for goal_data in goals_to_run:
            for sc in [False, True]:
                futures.append(executor.submit(run_single_eval, goal_data, sc))
                
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            completed_runs[0] += 1
            if on_progress:
                on_progress(completed_runs[0], total_runs, res["goal_id"], res["self_correction_enabled"])
                
    # Sort results to maintain deterministic ordering
    results.sort(key=lambda r: (r["goal_id"], r["self_correction_enabled"]))
    
    sc_results = [r for r in results if r["self_correction_enabled"]]
    base_results = [r for r in results if not r["self_correction_enabled"]]
    
    def calc_metrics(res_list: list[dict[str, Any]]) -> dict[str, Any]:
        if not res_list:
            return {}
        return {
            "completion_rate": sum(1 for r in res_list if r["success"]) / len(res_list),
            "avg_steps": sum(r["steps"] for r in res_list) / len(res_list),
            "total_self_corrections": sum(r["self_corrections"] for r in res_list),
            "avg_elapsed": sum(r["elapsed_seconds"] for r in res_list) / len(res_list)
        }
        
    summary = {
        "run_name": run_name,
        "timestamp": timestamp,
        "total_goals": len(goals_to_run),
        "metrics_with_self_correction": calc_metrics(sc_results),
        "metrics_baseline": calc_metrics(base_results),
        "runs": [
            {
                "goal_id": r["goal_id"],
                "self_correction_enabled": r["self_correction_enabled"],
                "success": r["success"],
                "steps": r["steps"],
                "self_corrections": r["self_corrections"],
                "elapsed_seconds": round(r["elapsed_seconds"], 2)
            }
            for r in results
        ]
    }
    
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
