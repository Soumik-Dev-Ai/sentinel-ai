from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend import config
from backend.tools.base import ToolProtocol, resolve_safe_path


class RunPythonArgs(BaseModel):
    path: str
    timeout: int = 30


class RunPythonResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class RunPythonTool(ToolProtocol):
    name = "run_python"
    description = "Run a Python file in a subprocess sandbox."
    args_schema = RunPythonArgs
    return_schema = RunPythonResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def _invoke(self, args: RunPythonArgs) -> dict[str, Any]:  # type: ignore[override]
        full = resolve_safe_path(self._workspace, args.path)
        if not full.exists():
            return {"exit_code": 127, "stdout": "", "stderr": f"File not found: {full}"}
        env = os.environ.copy()
        env["PATH"] = os.environ.get("PATH", "")
        timeout = min(args.timeout, config.TOOL_TIMEOUT_SECONDS)
        try:
            proc = subprocess.run(
                [sys.executable, str(full)],
                capture_output=True,
                text=True,
                cwd=str(full.parent),
                timeout=timeout,
                env=env,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "stdout": "", "stderr": "Timeout exceeded"}


