"""Unit tests for SpecCheckTool."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.tools.spec_check import SpecCheckTool


def test_spec_check_tool_name() -> None:
    tool = SpecCheckTool()
    assert tool.name == "spec_check"


def test_spec_check_file_not_found() -> None:
    d = Path(mkdtemp())
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({"file_path": "nonexistent.py"})
    assert result["ok"] is True
    assert result["result"]["passed"] is False
    assert "file not found" in result["result"]["failures"][0].lower()


def test_spec_check_absolute_path_raises() -> None:
    d = Path(mkdtemp())
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({"file_path": "/etc/passwd"})
    assert result["ok"] is True
    assert result["result"]["passed"] is False


def test_spec_check_stdout_contains_success() -> None:
    d = Path(mkdtemp())
    script = d / "hello.py"
    script.write_text("print('hello world')", encoding="utf-8")
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({
        "file_path": "hello.py", "expected_stdout_contains": "hello world",
    })
    assert result["ok"] is True
    assert result["result"]["passed"] is True
    assert len(result["result"]["checks"]) == 1


def test_spec_check_stdout_contains_failure() -> None:
    d = Path(mkdtemp())
    script = d / "hello.py"
    script.write_text("print('goodbye')", encoding="utf-8")
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({
        "file_path": "hello.py", "expected_stdout_contains": "hello",
    })
    assert result["ok"] is True
    assert result["result"]["passed"] is False


def test_spec_check_function_return_success() -> None:
    d = Path(mkdtemp())
    script = d / "mymod.py"
    script.write_text("def greet():\n    return 'hi'", encoding="utf-8")
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({
        "file_path": "mymod.py", "function_name": "greet", "expected_return": "hi",
    })
    assert result["ok"] is True
    assert result["result"]["passed"] is True


def test_spec_check_function_return_failure() -> None:
    d = Path(mkdtemp())
    script = d / "mymod.py"
    script.write_text("def greet():\n    return 'bye'", encoding="utf-8")
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({
        "file_path": "mymod.py", "function_name": "greet", "expected_return": "hi",
    })
    assert result["ok"] is True
    assert result["result"]["passed"] is False


def test_spec_check_function_not_found() -> None:
    d = Path(mkdtemp())
    script = d / "mymod.py"
    script.write_text("x = 1", encoding="utf-8")
    tool = SpecCheckTool(workspace=d)
    result = tool.invoke({
        "file_path": "mymod.py", "function_name": "missing", "expected_return": "hi",
    })
    assert result["ok"] is True
    assert result["result"]["passed"] is False

