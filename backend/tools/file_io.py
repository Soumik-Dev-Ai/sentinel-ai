from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.tools.base import ToolProtocol, resolve_safe_path


class WriteFileArgs(BaseModel):
    path: str
    content: str


class WriteFileResult(BaseModel):
    path: str
    bytes_written: int


class WriteFileTool(ToolProtocol):
    name = "write_file"
    description = "Write content to a file."
    args_schema = WriteFileArgs
    return_schema = WriteFileResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def _invoke(self, args: WriteFileArgs) -> dict[str, Any]:  # type: ignore[override]
        full = resolve_safe_path(self._workspace, args.path)
        full.parent.mkdir(parents=True, exist_ok=True)
        data = args.content.encode("utf-8")
        full.write_bytes(data)
        return {"path": str(full), "bytes_written": len(data)}


class ReadFileArgs(BaseModel):
    path: str


class ReadFileResult(BaseModel):
    path: str
    content: str
    exists: bool


class ReadFileTool(ToolProtocol):
    name = "read_file"
    description = "Read content from a file."
    args_schema = ReadFileArgs
    return_schema = ReadFileResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def _invoke(self, args: ReadFileArgs) -> dict[str, Any]:  # type: ignore[override]
        full = resolve_safe_path(self._workspace, args.path)
        if full.exists():
            content = full.read_text(encoding="utf-8")
            return {"path": str(full), "content": content, "exists": True}
        return {"path": str(full), "content": "", "exists": False}

