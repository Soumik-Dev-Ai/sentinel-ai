from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.tools.base import ToolProtocol, resolve_safe_path


class SpecCheckArgs(BaseModel):
    file_path: str
    expected_exit_code: int = 0
    expected_stdout_contains: str | None = None
    function_name: str | None = None
    expected_return: Any = None


class SpecCheckResult(BaseModel):
    passed: bool
    checks: list[str]
    failures: list[str]


class SpecCheckTool(ToolProtocol):
    name = "spec_check"
    description = "Validate output against acceptance spec."
    args_schema = SpecCheckArgs
    return_schema = SpecCheckResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def _invoke(self, args: SpecCheckArgs) -> dict[str, Any]:  # type: ignore[override]
        checks: list[str] = []
        failures: list[str] = []

        try:
            full = resolve_safe_path(self._workspace, args.file_path)
        except ValueError as e:
            return {"passed": False, "checks": [], "failures": [str(e)]}

        if not full.exists():
            return {
                "passed": False,
                "checks": [],
                "failures": [f"file not found: {args.file_path}"],
            }

        if args.expected_stdout_contains is not None:
            checks.append(
                f"stdout contains {args.expected_stdout_contains!r}"
            )
            try:
                proc = subprocess.run(
                    [sys.executable, str(full)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=str(self._workspace),
                )
                if args.expected_stdout_contains not in proc.stdout:
                    failures.append("stdout did not contain expected substring")
                if proc.returncode != args.expected_exit_code:
                    failures.append(
                        f"exit {proc.returncode} != expected {args.expected_exit_code}"
                    )
            except subprocess.TimeoutExpired:
                failures.append("subprocess timed out")

        if args.function_name and args.expected_return is not None:
            checks.append(
                f"function {args.function_name} returns {args.expected_return!r}"
            )
            probe_script = (
                f"import importlib.util as iu\n"
                f"spec = iu.spec_from_file_location('mod', r'{full!s}')\n"
                f"mod = iu.module_from_spec(spec)\n"
                f"spec.loader.exec_module(mod)\n"
                f"fn = getattr(mod, {args.function_name!r}, None)\n"
                f"print('OK' if fn and fn() == {args.expected_return!r} else 'FAIL')\n"
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                dir=self._workspace,
                encoding="utf-8",
            ) as tmp:
                tmp.write(probe_script)
                probe_path = tmp.name
            try:
                proc = subprocess.run(
                    [sys.executable, probe_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=str(self._workspace),
                )
                if proc.returncode != 0:
                    failures.append(
                        f"probe exited {proc.returncode}: "
                        f"{proc.stderr.strip()[:200]}"
                    )
                elif "OK" not in proc.stdout:
                    failures.append(
                        f"{args.function_name} check failed: "
                        f"{proc.stdout.strip()[:200]}"
                    )
            except subprocess.TimeoutExpired:
                failures.append("subprocess timed out")
            finally:
                Path(probe_path).unlink(missing_ok=True)

        passed = len(failures) == 0
        return {"passed": passed, "checks": checks, "failures": failures}

