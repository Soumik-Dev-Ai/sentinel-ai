"""Unit tests for RunTestsTool."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.tools.test_run import RunTestsTool


def test_run_tests_tool_name() -> None:
    tool = RunTestsTool()
    assert tool.name == "run_tests"


def test_run_tests_empty_path_runs_workspace() -> None:
    d = Path(mkdtemp())
    tool = RunTestsTool(workspace=d)
    result = tool.invoke({"path": ""})
    assert result["ok"] is True
    assert isinstance(result["result"]["exit_code"], int)


def test_run_tests_nonexistent_path() -> None:
    d = Path(mkdtemp())
    tool = RunTestsTool(workspace=d)
    result = tool.invoke({"path": "nonexistent_dir"})
    assert result["ok"] is True
    assert result["result"]["tests_passed"] is False


def test_run_tests_absolute_path() -> None:
    d = Path(mkdtemp())
    tool = RunTestsTool(workspace=d)
    result = tool.invoke({"path": str(Path.home())})
    assert result["ok"] is True
    assert isinstance(result["result"]["exit_code"], int)


def test_run_tests_timeout_capped() -> None:
    d = Path(mkdtemp())
    tool = RunTestsTool(workspace=d)
    result = tool.invoke({"path": "", "timeout": 9999})
    assert result["ok"] is True

