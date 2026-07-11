"""Additional tests for file_io.py â€” ReadFileTool success paths."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from backend.tools.file_io import ReadFileTool, WriteFileTool


def test_read_file_tool_success() -> None:
    d = Path(mkdtemp())
    (d / "test.txt").write_text("hello", encoding="utf-8")
    tool = ReadFileTool(workspace=d)
    result = tool.invoke({"path": "test.txt"})
    assert result["ok"] is True
    assert result["result"]["content"] == "hello"
    assert result["result"]["exists"] is True


def test_read_file_tool_not_found() -> None:
    d = Path(mkdtemp())
    tool = ReadFileTool(workspace=d)
    result = tool.invoke({"path": "missing.txt"})
    assert result["ok"] is True
    assert result["result"]["exists"] is False
    assert result["result"]["content"] == ""


def test_write_file_tool_creates_file() -> None:
    d = Path(mkdtemp())
    tool = WriteFileTool(workspace=d)
    result = tool.invoke({"path": "out.txt", "content": "written"})
    assert result["ok"] is True
    assert (d / "out.txt").exists()
    assert (d / "out.txt").read_text() == "written"


def test_write_file_tool_creates_subdirectories() -> None:
    d = Path(mkdtemp())
    tool = WriteFileTool(workspace=d)
    result = tool.invoke({"path": "sub/deep/out.txt", "content": "nested"})
    assert result["ok"] is True
    assert (d / "sub/deep/out.txt").exists()


def test_write_file_read_back() -> None:
    d = Path(mkdtemp())
    write = WriteFileTool(workspace=d)
    read = ReadFileTool(workspace=d)
    write.invoke({"path": "data.txt", "content": "roundtrip"})
    result = read.invoke({"path": "data.txt"})
    assert result["result"]["content"] == "roundtrip"

