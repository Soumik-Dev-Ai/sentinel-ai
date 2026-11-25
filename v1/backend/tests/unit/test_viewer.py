"""Unit tests for the CLI and HTML viewers."""

from __future__ import annotations

from pathlib import Path

from backend.ai_agent.working_memory import Goal, WorkingMemory
from backend.reporter.viewer_cli import render_run
from backend.reporter.viewer_html import render_file, render_html


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="V1", spec="viewer test"), ["task1"], 3)


def test_cli_viewer_renders_no_exception() -> None:
    mem = _mem()
    mem.record_step("thought", "write_file", {}, {"ok": True}, {"success": True})
    render_run(mem.to_dict())


def test_html_viewer_emits_selfcontained_file(tmp_path: Path) -> None:
    mem = _mem()
    path = tmp_path / "run.json"
    path.write_text(mem.to_json(), encoding="utf-8")
    html_path = render_file(path)
    assert html_path.exists()
    assert "viewer test" in html_path.read_text(encoding="utf-8")


def test_html_render_contains_metrics() -> None:
    html = render_html(_mem().to_dict())
    assert "Metrics" in html

