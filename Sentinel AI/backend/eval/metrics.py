from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_goals(yaml_path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return data.get("goals", [])


def compute_metrics(run_log: dict[str, Any]) -> dict[str, Any]:
    metrics = run_log.get("metrics", {})
    return {
        "run_id": run_log.get("run_id", "?"),
        "goal_id": (run_log.get("goal") or {}).get("id", "?"),
        "steps": metrics.get("steps", 0),
        "self_corrections": metrics.get("self_corrections", 0),
        "provider_switches": metrics.get("provider_switches", 0),
        "unresolvable_count": metrics.get("unresolvable_count", 0),
        "completed": run_log.get("final_output") is not None,
    }


def aggregate_runs(reports_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for f in sorted(reports_dir.glob("*.json")):
        run_log = json.loads(f.read_text(encoding="utf-8"))
        results.append(compute_metrics(run_log))
    return results


def write_metrics_csv(metrics_list: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["run_id,goal_id,steps,self_corrections,provider_switches,unresolvable_count,completed"]
    for m in metrics_list:
        lines.append(
            f"{m['run_id']},{m['goal_id']},{m['steps']},{m['self_corrections']},"
            f"{m['provider_switches']},{m['unresolvable_count']},{m['completed']}"
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_metrics_md(metrics_list: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Evaluation Metrics\n",
        "| Run ID | Goal | Steps | Corrections | Switches | Unresolvable | Completed |",
        "|--------|------|-------|-------------|----------|--------------|-----------|",
    ]
    for m in metrics_list:
        lines.append(
            f"| {m['run_id']} | {m['goal_id']} | {m['steps']} | {m['self_corrections']} | "
            f"{m['provider_switches']} | {m['unresolvable_count']} | {m['completed']} |"
        )
    completed = sum(1 for m in metrics_list if m["completed"])
    total = len(metrics_list)
    avg_steps = sum(m["steps"] for m in metrics_list) / max(total, 1)
    total_corrections = sum(m["self_corrections"] for m in metrics_list)
    total_unresolvable = sum(m["unresolvable_count"] for m in metrics_list)
    lines.append(
        f"\n**Completion rate:** {completed}/{total} ({completed / max(total, 1) * 100:.1f}%)"
    )
    lines.append(f"**Average steps:** {avg_steps:.1f}")
    lines.append(f"**Total self-corrections:** {total_corrections}")
    lines.append(f"**Unresolvable cases:** {total_unresolvable}")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_comparison_md(
    self_corr_metrics: list[dict[str, Any]],
    baseline_metrics: list[dict[str, Any]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Self-Correcting vs Baseline Comparison\n"]
    lines.append(
        "| Goal | Self-Corr Steps | Self-Corr Corrections | Self-Corr Completed | "
        "Baseline Steps | Baseline Completed |"
    )
    lines.append(
        "|------|-----------------|----------------------|---------------------|"
        "----------------|---------------------|"
    )
    baseline_by_goal = {m["goal_id"]: m for m in baseline_metrics}
    for sm in self_corr_metrics:
        gid = sm["goal_id"]
        bm = baseline_by_goal.get(gid, {})
        lines.append(
            f"| {gid} | {sm['steps']} | {sm['self_corrections']} | {sm['completed']} | "
            f"{bm.get('steps', '?')} | {bm.get('completed', '?')} |"
        )
    sc_completed = sum(1 for m in self_corr_metrics if m["completed"])
    bl_completed = sum(1 for m in baseline_metrics if m["completed"])
    lines.append(f"\n**Self-correcting completion:** {sc_completed}/{len(self_corr_metrics)}")
    lines.append(f"**Baseline completion:** {bl_completed}/{len(baseline_metrics)}")
    output_path.write_text("\n".join(lines), encoding="utf-8")

