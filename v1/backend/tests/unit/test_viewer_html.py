"""Tests for HTML viewer."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.reporter.viewer_html import render_file, render_html


def _sample_log() -> dict:
    return {
        "run_id": "run-1",
        "goal": {"spec": "test goal"},
        "final_output": "done",
        "steps": [
            {"step_ix": 0, "tool": "noop", "thought": "thinking",
             "result": {"ok": True}, "eval": {"success": True}},
            {"step_ix": 1, "tool": "write_file", "thought": "write it",
             "result": {"ok": False, "error_type": "fail"},
             "eval": {"success": False, "mode": "err"}},
        ],
        "corrections": [
            {"step_ix": 1, "mode": "err", "strategy": "retry",
             "mutated_object": "args", "evidence": "was wrong"},
        ],
        "unresolvable": [
            {"subtask_id": "sub-1", "modes": ["err"], "attempts": 3, "hypothesis": "cannot solve"},
        ],
        "metrics": {"steps": 2},
    }


def test_render_html_basic() -> None:
    html = render_html(_sample_log())
    assert "run-1" in html
    assert "test goal" in html
    assert "thinking" in html
    assert "write it" in html
    assert "retry" in html
    assert "cannot solve" in html
    assert "steps" in html
    assert "<!DOCTYPE html>" in html


def test_render_html_empty() -> None:
    html = render_html({})
    assert "<!DOCTYPE html>" in html


def test_render_html_no_corrections() -> None:
    data = _sample_log()
    data["corrections"] = []
    html = render_html(data)
    assert "No corrections" in html


def test_render_html_no_unresolvable() -> None:
    data = _sample_log()
    data["unresolvable"] = []
    html = render_html(data)
    assert "</body>" in html


def test_render_html_special_chars_escaped() -> None:
    data = _sample_log()
    data["goal"] = {"spec": "<script>alert('xss')</script>"}
    html = render_html(data)
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_render_file_output() -> None:
    d = Path(mkdtemp())
    p = d / "log.json"
    import json
    p.write_text(json.dumps(_sample_log()), encoding="utf-8")
    out = render_file(p)
    assert out.exists()
    assert "run-1" in out.read_text(encoding="utf-8")

