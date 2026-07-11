"""Unit tests for tool base (schema validation -> tool failure synthesis)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.tools.base import (
    ToolProtocol,
    is_tool_failure_result,
)


class _GoodArgs(BaseModel):
    x: int


class _GoodReturn(BaseModel):
    doubled: int
    ok: bool = True


class _DoubleTool(ToolProtocol):
    name = "double"
    description = "double x"
    args_schema = _GoodArgs
    return_schema = _GoodReturn

    def _invoke(self, args: _GoodArgs) -> dict[str, Any]:
        return {"doubled": args.x * 2, "ok": True}


class _BadReturnTool(ToolProtocol):
    name = "bad_return"
    description = "returns wrong shape"
    args_schema = _GoodArgs
    return_schema = _GoodReturn

    def _invoke(self, args: _GoodArgs) -> dict[str, Any]:
        return {"ok": True}  # missing 'doubled' -> shape violation


class _RaisesTool(ToolProtocol):
    name = "raises"
    description = "always raises"
    args_schema = _GoodArgs
    return_schema = _GoodReturn

    def _invoke(self, args: _GoodArgs) -> dict[str, Any]:
        raise RuntimeError("kaboom")


def test_accepts_conforming_return_shape() -> None:
    out = _DoubleTool().invoke({"x": 5})
    assert out["ok"] is True
    assert out["result"]["doubled"] == 10


def test_rejects_missing_field_emits_shape_violation() -> None:
    out = _BadReturnTool().invoke({"x": 1})
    assert out["ok"] is False
    assert out["error_type"] == "shape_violation"
    assert "details" in out


def test_args_validation_emits_args_invalid() -> None:
    out = _DoubleTool().invoke({"x": "not-an-int"})
    assert out["ok"] is False
    assert out["error_type"] == "args_invalid"


def test_runtime_exception_becomes_tool_exception() -> None:
    out = _RaisesTool().invoke({"x": 1})
    assert out["ok"] is False
    assert out["error_type"] == "tool_exception"
    assert "kaboom" in out["details"]


def test_is_tool_failure_result_detects_failures() -> None:
    ok_result = {"ok": True, "tool": "t", "result": {}}
    fail_result = {"ok": False, "error_type": "shape_violation", "tool": "t"}
    assert not is_tool_failure_result(ok_result)
    assert is_tool_failure_result(fail_result)
    assert not is_tool_failure_result({})


def test_no_return_schema_skips_validation() -> None:
    class _NoSchemaTool(ToolProtocol):
        name = "noschema"
        description = "no return schema"
        args_schema = _GoodArgs
        return_schema = None

        def _invoke(self, args: _GoodArgs) -> dict[str, Any]:
            return {"anything": True}

    out = _NoSchemaTool().invoke({"x": 1})
    assert out["ok"] is True
    assert out["result"]["anything"] is True

