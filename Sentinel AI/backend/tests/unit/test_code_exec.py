"""Unit tests for RunPythonTool."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.tools.code_exec import RunPythonTool


def test_run_python_tool_name() -> None:
    tool = RunPythonTool()
    assert tool.name == "run_python"


def test_run_python_file_not_found() -> None:
    d = Path(mkdtemp())
    tool = RunPythonTool(workspace=d)
    result = tool.invoke({"path": "nonexistent.py"})
    assert result["ok"] is True
    assert result["result"]["exit_code"] == 127


def test_run_python_success() -> None:
    d = Path(mkdtemp())
    script = d / "hello.py"
    script.write_text("print('hello from test')", encoding="utf-8")
    tool = RunPythonTool(workspace=d)
    result = tool.invoke({"path": "hello.py"})
    assert result["ok"] is True
    assert "hello from test" in result["result"]["stdout"]
    assert result["result"]["exit_code"] == 0


def test_run_python_with_stderr() -> None:
    d = Path(mkdtemp())
    script = d / "error.py"
    script.write_text("import sys; sys.stderr.write('warn\\n'); print('ok')", encoding="utf-8")
    tool = RunPythonTool(workspace=d)
    result = tool.invoke({"path": "error.py"})
    assert result["ok"] is True
    assert result["result"]["stderr"] == "warn\n"


def test_run_python_timeout_capped_by_config() -> None:
    d = Path(mkdtemp())
    script = d / "infinite.py"
    script.write_text("import time; time.sleep(999)", encoding="utf-8")
    tool = RunPythonTool(workspace=d)
    result = tool.invoke({"path": "infinite.py", "timeout": 9999})
    assert result["ok"] is True
    assert result["result"]["exit_code"] == 124

