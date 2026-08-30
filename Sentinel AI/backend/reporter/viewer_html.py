from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Agent Run: __RUN_ID__</title>
<style>
  body { font-family: 'Segoe UI', sans-serif; margin: 2em; background: #1a1a2e; color: #eee; }
  h1 { color: #0ff; } h2 { color: #0a0; border-bottom: 1px solid #333; padding-bottom: 4px; }
  .step { background: #16213e; padding: 12px; margin: 8px 0; border-radius: 6px; }
  .thought { color: #ffaa00; font-style: italic; }
  .result-ok { color: #0f0; } .result-fail { color: #f00; }
  .correction { background: #331122; padding: 8px; margin: 4px 0; border-left: 4px solid #f0f; }
  .unresolvable { background: #221133; padding: 8px; border-left: 4px solid #f00; }
  .metrics { background: #0a2a0a; padding: 8px; border-radius: 4px; }
  details { margin: 4px 0; } summary { cursor: pointer; font-weight: bold; }
</style>
</head>
<body>
<h1>Agent Run: __RUN_ID__</h1>
<p><strong>Goal:</strong> __GOAL_SPEC__</p>
<h2>Final Output</h2>
<pre>__FINAL_OUTPUT__</pre>
<h2>Steps (__STEP_COUNT__)</h2>
__STEPS_HTML__
<h2>Self-Corrections (__CORR_COUNT__)</h2>
__CORRECTIONS_HTML__
__UNRESOLVABLE_HTML__
<h2>Metrics</h2>
<pre class="metrics">__METRICS__</pre>
</body>
</html>"""


def render_html(log_data: dict[str, Any]) -> str:
    run_id = log_data.get("run_id", "?")
    goal = log_data.get("goal") or {}
    goal_spec = html.escape(goal.get("spec", "N/A"))
    final_output = html.escape(str(log_data.get("final_output", "N/A")))

    steps_html_parts = []
    for s in log_data.get("steps", []):
        result = s.get("result", {})
        ok = (
            isinstance(result, dict)
            and result.get("ok") is not False
            and "error_type" not in result
        )
        result_class = "result-ok" if ok else "result-fail"
        step_ix = s.get("step_ix", "")
        tool_name = html.escape(s.get("tool", ""))
        thought_text = html.escape((s.get("thought", "") or "")[:200])
        result_text = html.escape(str(result)[:300])
        eval_data = s.get("eval", {})
        eval_mode = eval_data.get("mode")
        eval_success = eval_data.get("success")
        steps_html_parts.append(
            f'<details class="step"><summary>Step {step_ix}: {tool_name}</summary>'
            f'<div class="thought">Thought: {thought_text}</div>'
            f'<div class="{result_class}">Result: {result_text}</div>'
            f"<div>Eval: mode={eval_mode} success={eval_success}</div>"
            "</details>"
        )
    steps_html = "\n".join(steps_html_parts)

    corr_html_parts = []
    for c in log_data.get("corrections", []):
        corr_html_parts.append(
            f'<div class="correction"><strong>Step {c.get("step_ix", "")}</strong> '
            f"| Mode: {c.get('mode', '')} | Strategy: {c.get('strategy', '')} | "
            f"Mutated: {c.get('mutated_object', '')}<br>"
            f"Evidence: {html.escape((c.get('evidence', '') or '')[:200])}</div>"
        )
    corrections_html = "\n".join(corr_html_parts) or "<p>No corrections.</p>"

    unresolvable_parts = []
    for u in log_data.get("unresolvable", []):
        unresolvable_parts.append(
            f'<div class="unresolvable"><strong>{u.get("subtask_id", "")}</strong> '
            f"| Modes: {', '.join(u.get('modes', []))} | Attempts: {u.get('attempts', 0)}<br>"
            f"Hypothesis: {html.escape((u.get('hypothesis', '') or '')[:200])}</div>"
        )
    unresolvable_html = "\n".join(unresolvable_parts)

    metrics = html.escape(json.dumps(log_data.get("metrics", {}), indent=2))

    return (
        HTML_TEMPLATE.replace("__RUN_ID__", html.escape(run_id))
        .replace("__GOAL_SPEC__", goal_spec)
        .replace("__FINAL_OUTPUT__", final_output)
        .replace("__STEP_COUNT__", str(len(log_data.get("steps", []))))
        .replace("__STEPS_HTML__", steps_html)
        .replace("__CORR_COUNT__", str(len(log_data.get("corrections", []))))
        .replace("__CORRECTIONS_HTML__", corrections_html)
        .replace("__UNRESOLVABLE_HTML__", unresolvable_html)
        .replace("__METRICS__", metrics)
    )


def render_file(path: Path, output_path: Path | None = None) -> Path:
    data = json.loads(path.read_text(encoding="utf-8"))
    html_str = render_html(data)
    if output_path is None:
        output_path = path.with_suffix(".html")
    output_path.write_text(html_str, encoding="utf-8")
    return output_path

