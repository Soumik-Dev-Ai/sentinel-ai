from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError


def resolve_safe_path(workspace: Path, user_path: str) -> Path:
    requested = Path(user_path)
    if requested.is_absolute():
        raise ValueError(f"Absolute paths not allowed: {user_path}")
    resolved = (workspace / requested).resolve()
    workspace_resolved = workspace.resolve()
    try:
        resolved.relative_to(workspace_resolved)
    except ValueError:
        raise ValueError(f"Path escapes workspace: {user_path}") from None
    return resolved


class ToolFailureError(Exception):
    def __init__(self, reason: str, tool: str, raw: Any = None):
        self.reason = reason
        self.tool = tool
        self.raw = raw
        super().__init__(f"ToolFailure[{tool}]: {reason}")


class ToolProtocol(ABC):
    name: str
    description: str = ""
    args_schema: type[BaseModel]
    return_schema: type[BaseModel] | None = None

    @abstractmethod
    def _invoke(self, args: BaseModel) -> Any: ...

    def invoke(self, raw_args: dict[str, Any]) -> dict[str, Any]:
        try:
            validated_args = self.args_schema.model_validate(raw_args)
        except ValidationError as e:
            return {
                "ok": False,
                "error_type": "args_invalid",
                "tool": self.name,
                "details": e.errors(),
            }

        try:
            result = self._invoke(validated_args)
        except Exception as e:
            return {
                "ok": False,
                "error_type": "tool_exception",
                "tool": self.name,
                "details": str(e),
            }

        if (
            self.return_schema is not None
            and not isinstance(result, dict)
            and hasattr(result, "model_dump")
        ):
            result = result.model_dump()

        if self.return_schema is not None:
            try:
                self.return_schema.model_validate(result)
            except ValidationError as e:
                return {
                    "ok": False,
                    "error_type": "shape_violation",
                    "tool": self.name,
                    "details": e.errors(),
                    "raw_result": result,
                }

        return {"ok": True, "tool": self.name, "result": result}


def is_tool_failure_result(result: dict[str, Any]) -> bool:
    return isinstance(result, dict) and result.get("ok") is False and "error_type" in result


def extract_result(result: dict[str, Any]) -> Any:
    if isinstance(result, dict) and "ok" in result:
        if result.get("ok"):
            return result.get("result")
        return None
    return result

