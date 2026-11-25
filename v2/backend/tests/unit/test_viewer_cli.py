"""Tests for CLI viewer."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.reporter.viewer_cli import render_file, render_run


def _sample_log() -> dict:
    return {
        "run_id": "run-1",
        "goal": {"spec": "test goal"},
        "final_output": "done",
        "steps": [
            {"step_ix": 0, "tool": "noop", "thought": "thinking",
             "result": {"ok": True}, "eval": {"success": True, "mode": None}},
            {"step_ix": 1, "tool": "write_file", "thought": "write it",
             "result": {"ok": False},
             "eval": {"success": False, "mode": "strategy_failure"}},
        ],
        "corrections": [
            {"step_ix": 1, "mode": "strategy_failure",
             "strategy": "retry", "mutated_object": "tool_args",
             "evidence": "was wrong"},
        ],
        "unresolvable": [
            {"subtask_id": "sub-1", "modes": ["strategy_failure"],
             "attempts": 3, "hypothesis": "cannot solve"},
        ],
        "metrics": {"steps": 2, "self_corrections": 1},
    }


def test_render_run_with_all_data() -> None:
    from io import StringIO

    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf, width=120)
    render_run(_sample_log(), console)
    output = buf.getvalue()
    assert "run-1" in output
    assert "test goal" in output
    assert "noop" in output
    assert "retry" in output
    assert "cannot solve" in output
    assert "steps" in output


def test_render_run_empty_log() -> None:
    from io import StringIO

    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf, width=120)
    render_run({}, console)
    output = buf.getvalue()
    assert output


def test_render_file_roundtrip() -> None:
    d = Path(mkdtemp())
    p = d / "log.json"
    import json
    p.write_text(json.dumps(_sample_log()), encoding="utf-8")
    render_file(p)

