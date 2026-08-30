from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render_run(log_data: dict[str, Any], console: Console | None = None) -> None:
    console = console or Console()

    goal = log_data.get("goal") or {}
    console.print(
        Panel(
            f"[bold]Goal:[/bold] {goal.get('spec', 'N/A')}\n"
            f"[bold]Run ID:[/bold] {log_data.get('run_id', '?')}\n"
            f"[bold]Final Output:[/bold] {str(log_data.get('final_output', 'N/A'))[:200]}",
            title="Agent Run Summary",
            border_style="cyan",
        )
    )

    steps = log_data.get("steps", [])
    step_table = Table(title="Steps", show_lines=True)
    step_table.add_column("#", style="dim")
    step_table.add_column("Tool")
    step_table.add_column("Thought", max_width=40)
    step_table.add_column("Result", max_width=30)
    step_table.add_column("Eval")
    for s in steps:
        result = s.get("result", {})
        result_str = "OK" if isinstance(result, dict) and result.get("ok") else "FAIL"
        eval_data = s.get("eval", {})
        eval_str = f"success={eval_data.get('success')}, mode={eval_data.get('mode')}"
        step_table.add_row(
            str(s.get("step_ix", "")),
            s.get("tool", ""),
            (s.get("thought", "") or "")[:80],
            result_str,
            eval_str,
        )
    console.print(step_table)

    corrections = log_data.get("corrections", [])
    if corrections:
        corr_table = Table(title="Self-Corrections", show_lines=True)
        corr_table.add_column("Step", style="dim")
        corr_table.add_column("Mode")
        corr_table.add_column("Strategy")
        corr_table.add_column("Mutated")
        corr_table.add_column("Evidence", max_width=50)
        for c in corrections:
            corr_table.add_row(
                str(c.get("step_ix", "")),
                c.get("mode", ""),
                c.get("strategy", ""),
                c.get("mutated_object", ""),
                (c.get("evidence", "") or "")[:100],
            )
        console.print(corr_table)

    unresolvable = log_data.get("unresolvable", [])
    if unresolvable:
        unres_table = Table(title="Unresolvable Subtasks")
        unres_table.add_column("Subtask")
        unres_table.add_column("Modes")
        unres_table.add_column("Attempts")
        unres_table.add_column("Hypothesis", max_width=50)
        for u in unresolvable:
            unres_table.add_row(
                u.get("subtask_id", ""),
                ", ".join(u.get("modes", [])),
                str(u.get("attempts", 0)),
                (u.get("hypothesis", "") or "")[:100],
            )
        console.print(unres_table)

    metrics = log_data.get("metrics", {})
    console.print(f"\n[bold green]Metrics:[/bold green] {json.dumps(metrics)}")


def render_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    render_run(data)

