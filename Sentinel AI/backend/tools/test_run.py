from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend import config
from backend.tools.base import ToolProtocol


class RunTestsArgs(BaseModel):
    path: str = ""
    timeout: int = 30


class RunTestsResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    tests_passed: bool


class RunTestsTool(ToolProtocol):
    name = "run_tests"
    description = "Run pytest on a test file or directory."
    args_schema = RunTestsArgs
    return_schema = RunTestsResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def _invoke(self, args: RunTestsArgs) -> dict[str, Any]:  # type: ignore[override]
        target = (
            self._workspace
            if not args.path
            else (
                self._workspace / args.path
                if not Path(args.path).is_absolute()
                else Path(args.path)
            )
        )
        timeout = min(args.timeout, config.TOOL_TIMEOUT_SECONDS)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(target), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=timeout,
            )
            passed = proc.returncode == 0
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "tests_passed": passed,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "stdout": "", "stderr": "Timeout", "tests_passed": False}


