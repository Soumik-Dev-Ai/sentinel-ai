from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
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
    current_run = 0
    
    for goal_data in goals_to_run:
        for self_correction_enabled in [False, True]:
            current_run += 1
            if on_progress:
                on_progress(current_run, total_runs, goal_data["id"], self_correction_enabled)
                
            workspace = Path(mkdtemp(prefix=f"eval_ws_{goal_data['id']}_"))
            if goal_data["input"]:
                (workspace / "input.txt").write_text(goal_data["input"], encoding="utf-8")
                
            tools = [
                ReadFileTool(workspace), WriteFileTool(workspace),
                RunPythonTool(workspace), RunTestsTool(workspace),
                SpecCheckTool(workspace), FlakyNetTool(),
            ]
            router = LLMRouter()
            runner = AgentRunner(
                router=router, 
                tools=tools,
                self_correction_enabled=self_correction_enabled,
                callbacks={}
            )
            
            start_time = time.time()
            memory = runner.run(Goal(id=goal_data["id"], spec=goal_data["spec"], acceptance=[]), [goal_data["spec"]])
            elapsed = time.time() - start_time
            
            metrics = memory.to_metrics()
            
            # Simple check for success: the final output is populated and no unresolvable tasks.
            success = bool(memory.final_output) and not memory.unresolvable
            
            run_result = {
                "goal_id": goal_data["id"],
                "spec": goal_data["spec"],
                "self_correction_enabled": self_correction_enabled,
                "success": success,
                "steps": metrics.get("steps", 0),
                "self_corrections": metrics.get("self_corrections", 0),
                "elapsed_seconds": elapsed,
                "memory_dump": memory.to_dict()
            }
            results.append(run_result)
            
            # Save individual trace
            mode_str = "with_sc" if self_correction_enabled else "no_sc"
            trace_path = run_dir / f"{goal_data['id']}_{mode_str}.json"
            trace_path.write_text(json.dumps(run_result, indent=2))
            
    # Calculate aggregate metrics
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
    
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary
