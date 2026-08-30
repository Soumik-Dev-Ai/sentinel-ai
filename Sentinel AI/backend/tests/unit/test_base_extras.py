"""Additional tests for tools/base.py â€” model_dump, extract_result."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from pydantic import BaseModel

from backend.tools.base import extract_result, resolve_safe_path


class _DummyResult(BaseModel):
    value: str

    def model_dump(self) -> dict[str, str]:
        return {"value": self.value}


def test_model_dump_path_in_invoke() -> None:
    from backend.tools.base import ToolProtocol

    class _DummyTool(ToolProtocol):
        name = "dummy"
        description = ""
        args_schema = _DummyResult
        return_schema = _DummyResult

        def _invoke(self, args: _DummyResult) -> _DummyResult:
            return _DummyResult(value="wrapped")

    tool = _DummyTool()
    result = tool.invoke({"value": "test"})
    assert result["ok"] is True
    assert result["result"]["value"] == "wrapped"


def test_shape_violation() -> None:
    from backend.tools.base import ToolProtocol

    class _StrictResult(BaseModel):
        x: int

    class _BadTool(ToolProtocol):
        name = "bad"
        description = ""
        args_schema = _DummyResult
        return_schema = _StrictResult

        def _invoke(self, args: _DummyResult) -> dict[str, str]:
            return {"wrong": "data"}

    tool = _BadTool()
    result = tool.invoke({"value": "test"})
    assert result["ok"] is False
    assert result["error_type"] == "shape_violation"


def test_extract_result_ok() -> None:
    assert extract_result({"ok": True, "result": "data"}) == "data"


def test_extract_result_not_ok() -> None:
    assert extract_result({"ok": False, "error_type": "err"}) is None


def test_extract_result_no_ok() -> None:
    assert extract_result({"raw": "value"}) == {"raw": "value"}


def test_extract_result_non_dict() -> None:
    assert extract_result("string") == "string"
    assert extract_result(42) == 42


def test_resolve_safe_path_absolute_raises() -> None:
    d = Path(mkdtemp())
    try:
        resolve_safe_path(d, "C:\\Windows\\system32")
        raise AssertionError("Should have raised")
    except ValueError as e:
        assert "not allowed" in str(e).lower() or "escapes" in str(e).lower()


def test_resolve_safe_path_escape_raises() -> None:
    d = Path(mkdtemp())
    try:
        resolve_safe_path(d, "../etc/passwd")
        raise AssertionError("Should have raised")
    except ValueError as e:
        assert "escapes" in str(e).lower()

