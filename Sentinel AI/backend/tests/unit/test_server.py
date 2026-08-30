"""Unit tests for the API server module (pure functions + app setup)."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.server.server import _build_result, _collect_generated_code


def test_collect_generated_code_empty_dir() -> None:
    d = Path(mkdtemp())
    result = _collect_generated_code(d)
    assert result == {}


def test_collect_generated_code_with_files() -> None:
    d = Path(mkdtemp())
    (d / "foo.txt").write_text("hello", encoding="utf-8")
    (d / "sub").mkdir()
    (d / "sub" / "bar.py").write_text("print(1)", encoding="utf-8")
    result = _collect_generated_code(d)
    assert result.get("foo.txt") == "hello"
    # Use as_posix() to normalize Windows backslashes
    bar_key = next(k for k in result if "bar" in k)
    assert result[bar_key] == "print(1)"


def test_collect_generated_code_skips_binary() -> None:
    d = Path(mkdtemp())
    (d / "data.bin").write_bytes(b"\xff\xfe\x00\x01")
    result = _collect_generated_code(d)
    assert "data.bin" not in result


def test_collect_generated_code_nonexistent_dir() -> None:
    result = _collect_generated_code(Path("/nonexistent/path/xyz"))
    assert result == {}


def test_build_result_shape() -> None:
    r = _build_result(
        success=True, goal="test goal", steps_taken=3, self_corrections=1,
        final_output="done", errors=[], terminal_logs=["log"],
        generated_code={"a.py": "code"}, metrics={"steps": 3, "elapsed_seconds": 1.5},
    )
    assert r["success"] is True
    assert r["goal"] == "test goal"
    assert r["steps_taken"] == 3
    assert r["self_corrections"] == 1
    assert r["final_output"] == "done"
    assert r["errors"] == []
    assert r["terminal_logs"] == ["log"]
    assert r["generated_code"] == {"a.py": "code"}
    assert r["metrics"] == {"steps": 3, "elapsed_seconds": 1.5}


def test_build_result_error_case() -> None:
    r = _build_result(
        success=False, goal="fail", steps_taken=0, self_corrections=0,
        final_output=None, errors=["crash"], terminal_logs=[],
        generated_code={}, metrics={},
    )
    assert r["success"] is False
    assert r["final_output"] is None
    assert r["errors"] == ["crash"]


def test_app_routes_registered() -> None:
    from backend.server.server import app

    paths = {r.path for r in app.routes}
    assert "/ws/run" in paths
    assert "/openapi.json" in paths


def test_app_middleware_cors() -> None:
    from backend.server.server import app

    mids = [m.cls for m in app.user_middleware]
    from fastapi.middleware.cors import CORSMiddleware
    assert CORSMiddleware in mids

