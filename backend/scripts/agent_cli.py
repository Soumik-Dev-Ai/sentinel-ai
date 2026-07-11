#!/usr/bin/env python
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from dotenv import load_dotenv

load_dotenv()

CWD = Path(__file__).resolve().parent.parent.parent
if str(CWD) not in sys.path:
    sys.path.insert(0, str(CWD))

from backend.ai_agent.runner import AgentRunner  # noqa: E402
from backend.ai_agent.working_memory import Goal  # noqa: E402
from backend.llm.router import LLMRouter  # noqa: E402
from backend.tools.file_io import ReadFileTool, WriteFileTool  # noqa: E402


def collect_generated_code(workspace: Path) -> dict[str, str]:
    """Return a mapping of relative-path -> content for all text files created under workspace."""
    generated: dict[str, str] = {}
    if not workspace.exists():
        return generated
    for fp in workspace.rglob("*"):
        if fp.is_file():
            try:
                content = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            generated[str(fp.relative_to(workspace))] = content
    return generated


def build_result(
    success: bool,
    goal: str,
    steps_taken: int,
    self_corrections: int,
    final_output: Any,
    errors: list[str],
    terminal_logs: list[str],
    generated_code: dict[str, str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": success,
        "goal": goal,
        "steps_taken": steps_taken,
        "self_corrections": self_corrections,
        "final_output": final_output,
        "errors": errors,
        "terminal_logs": terminal_logs,
        "generated_code": generated_code,
        "metrics": metrics,
    }


def _log(terminal_logs: list[str], msg: str) -> None:
    terminal_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def run_agent(
    goal_spec: str,
    input_text: str = "",
    workspace_dir: str | None = None,
    max_steps: int | None = None,
    budget_per_subtask: int | None = None,
    self_correction_enabled: bool = True,
) -> dict[str, Any]:
    terminal_logs: list[str] = []
    errors: list[str] = []

    try:
        _log(terminal_logs, f"Starting agent with goal: {goal_spec}")
        if input_text:
            _log(terminal_logs, f"Input text provided ({len(input_text)} chars)")

        workspace = Path(workspace_dir) if workspace_dir else Path(mkdtemp(prefix="agent_cli_"))
        workspace.mkdir(parents=True, exist_ok=True)
        _log(terminal_logs, f"Workspace: {workspace}")

        read_tool = ReadFileTool(workspace)
        write_tool = WriteFileTool(workspace)
        tools = [read_tool, write_tool]

        if input_text:
            input_path = workspace / "input.txt"
            input_path.write_text(input_text, encoding="utf-8")
            _log(terminal_logs, f"Wrote input to {input_path}")

        router = LLMRouter()
        _log(terminal_logs, f"LLM providers: {[p.name for p in router._providers]}")

        runner = AgentRunner(
            router=router,
            tools=tools,
            budget_per_subtask=budget_per_subtask,
            max_steps=max_steps,
            self_correction_enabled=self_correction_enabled,
        )

        goal = Goal(id="CLI-1", spec=goal_spec, acceptance=[])
        plan_descs = [goal_spec]

        _log(terminal_logs, "Running agent...")

        start_time = time.time()
        memory = runner.run(goal, plan_descs)
        elapsed = round(time.time() - start_time, 2)

        _log(terminal_logs, f"Agent finished in {elapsed}s")

        for _, step in enumerate(memory.executed):
            tool = step.tool or "(none)"
            ev = step.eval_result or {}
            ok = ev.get("success", "?")
            corr = step.correction_trigger or ""
            _log(
                terminal_logs,
                f"  Step {step.step_ix}: {tool} | ok={ok}"
                + (f" | correction={corr}" if corr else ""),
            )

        metrics_raw = memory.to_metrics()
        metrics = {
            "steps": metrics_raw.get("steps", 0),
            "self_corrections": metrics_raw.get("self_corrections", 0),
            "provider_switches": metrics_raw.get("provider_switches", 0),
            "unresolvable_count": metrics_raw.get("unresolvable_count", 0),
            "elapsed_seconds": elapsed,
            "budget_remaining": (
                memory.active_subtask
                and memory.get_budget(memory.active_subtask.id)
                or 0
            ),
        }

        generated_code = collect_generated_code(workspace)

        steps_taken = len(memory.executed)
        self_corrections = len(memory.corrections)
        final_output = memory.final_output

        success = bool(final_output) and errors == []
        if memory.unresolvable:
            errors.extend(
                f"[UNRESOLVABLE {u.subtask_id}] {u.hypothesis}" for u in memory.unresolvable
            )

        result = build_result(
            success=success,
            goal=goal_spec,
            steps_taken=steps_taken,
            self_corrections=self_corrections,
            final_output=final_output,
            errors=errors,
            terminal_logs=terminal_logs,
            generated_code=generated_code,
            metrics=metrics,
        )

        _log(
            terminal_logs,
            f"Result: success={success}, steps={steps_taken},"
            f" corrections={self_corrections}",
        )
        return result

    except KeyboardInterrupt:
        _log(terminal_logs, "Interrupted by user")
        return build_result(
            success=False,
            goal=goal_spec,
            steps_taken=0,
            self_corrections=0,
            final_output=None,
            errors=["Interrupted by user"],
            terminal_logs=terminal_logs,
            generated_code={},
            metrics={"elapsed_seconds": 0, "provider_switches": 0, "budget_remaining": 0},
        )

    except Exception as exc:
        _log(terminal_logs, f"Fatal error: {exc}")
        tb = traceback.format_exc()
        errors.append(f"{type(exc).__name__}: {exc}")
        errors.append(tb)
        return build_result(
            success=False,
            goal=goal_spec,
            steps_taken=0,
            self_corrections=0,
            final_output=None,
            errors=errors,
            terminal_logs=terminal_logs,
            generated_code={},
            metrics={"elapsed_seconds": 0, "provider_switches": 0, "budget_remaining": 0},
        )


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv

    args = argv[1:]

    workspace_dir: str | None = None
    goal_spec: str | None = None
    input_text: str = ""
    max_steps: int | None = None
    budget: int | None = None
    self_correction_enabled: bool = True
    output_file: str | None = None

    i = 0
    positional: list[str] = []
    while i < len(args):
        arg = args[i]
        if arg == "--workspace" and i + 1 < len(args):
            i += 1
            workspace_dir = args[i]
        elif arg == "--input" and i + 1 < len(args):
            i += 1
            input_text = args[i]
        elif arg == "--max-steps" and i + 1 < len(args):
            i += 1
            max_steps = int(args[i])
        elif arg == "--budget" and i + 1 < len(args):
            i += 1
            budget = int(args[i])
        elif arg == "--no-self-correction":
            self_correction_enabled = False
        elif arg == "--output" and i + 1 < len(args):
            i += 1
            output_file = args[i]
        elif arg in ("--help", "-h"):
            print(
                "Usage: python scripts/agent_cli.py [OPTIONS] <goal> [<input text>]\n"
                "\n"
                "Options:\n"
                "  --workspace DIR       Working directory (default: temp dir)\n"
                "  --input TEXT          Optional input text (alternative to positional)\n"
                "  --max-steps N         Max agent steps (default: config MAX_AGENT_STEPS)\n"
                "  --budget N            Recovery budget per subtask (default: config value)\n"
                "  --no-self-correction  Disable self-correction\n"
                "  --output FILE         Write JSON result to file instead of stdout\n"
                "  --help, -h            Show this help\n"
                "\n"
                "Positional arguments:\n"
                "  goal                  Goal specification text\n"
                "  input_text            Optional input text provided to the agent\n"
                "\n"
                "Examples:\n"
                "  python scripts/agent_cli.py \"Write a hello-world script\"\n"
                "  python scripts/agent_cli.py --workspace ./out"
                ' "Fix the bug" "The code is..."\n'
            )
            return
        elif arg.startswith("-"):
            print(f"Unknown option: {arg}", file=sys.stderr)
            sys.exit(2)
        else:
            positional.append(arg)
        i += 1

    if not positional:
        print("Error: goal argument is required", file=sys.stderr)
        print("Use --help for usage", file=sys.stderr)
        sys.exit(2)

    goal_spec = positional[0]
    if len(positional) > 1:
        input_text = positional[1]

    result = run_agent(
        goal_spec=goal_spec,
        input_text=input_text,
        workspace_dir=workspace_dir,
        max_steps=max_steps,
        budget_per_subtask=budget,
        self_correction_enabled=self_correction_enabled,
    )

    json_out = json.dumps(result, indent=2, default=str)

    if output_file:
        Path(output_file).write_text(json_out, encoding="utf-8")
        print(f"Result written to {output_file}")
    else:
        print(json_out)


if __name__ == "__main__":
    main()

