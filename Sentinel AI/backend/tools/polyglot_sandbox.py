from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel

from backend import config
from backend.tools.base import ToolProtocol, resolve_safe_path

LANGUAGE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "c": {
        "extension": "main.c",
        "compile_cmd": "gcc -Wall -Wextra -O2 {src} -o {bin} -pthread -lm",
        "run_cmd": "{bin}",
        "timeout": 12,
    },
    "cpp": {
        "extension": "main.cpp",
        "compile_cmd": "g++ -std=c++20 -Wall -Wextra -O2 {src} -o {bin} -pthread",
        "run_cmd": "{bin}",
        "timeout": 12,
    },
    "rust": {
        "extension": "main.rs",
        "compile_cmd": "rustc -O {src} -o {bin}",
        "run_cmd": "{bin}",
        "timeout": 15,
    },
    "go": {
        "extension": "main.go",
        "compile_cmd": "go build -o {bin} {src}",
        "run_cmd": "{bin}",
        "timeout": 15,
    },
    "python": {
        "extension": "main.py",
        "compile_cmd": None,
        "run_cmd": "python3 {src}",
        "timeout": 15,
    },
    "javascript": {
        "extension": "main.js",
        "compile_cmd": None,
        "run_cmd": "node {src}",
        "timeout": 10,
    },
}

EXT_MAP: Dict[str, str] = {
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
}


def _set_linux_rlimits() -> None:
    if os.name == "nt":
        return
    try:
        import resource
        # Allow 4 GB virtual address space and 50 MB file size limit
        resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 * 1024 * 1024, 4 * 1024 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    except Exception:
        pass


class PolyglotRunArgs(BaseModel):
    path: Optional[str] = None
    code: Optional[str] = None
    language: Optional[str] = None
    timeout: int = 15


class PolyglotRunResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    stage: str = "runtime"
    error_type: Optional[str] = None


class PolyglotSandboxTool(ToolProtocol):
    name = "polyglot_sandbox"
    description = "Run C, C++, Rust, Go, Python, or JS inside an isolated polyglot sandbox."
    args_schema = PolyglotRunArgs
    return_schema = PolyglotRunResult

    def __init__(self, workspace: Path | None = None):
        self._workspace = workspace or Path.cwd()

    def run(self, code: str, language: str = "python", custom_filename: str | None = None, timeout: int | None = None) -> dict[str, Any]:
        lang = language.lower().strip()
        if lang in ("js", "node"):
            lang = "javascript"
        cfg = LANGUAGE_CONFIGS.get(lang, LANGUAGE_CONFIGS["python"])

        temp_dir = Path(tempfile.mkdtemp(prefix=f"sandbox_{lang}_"))
        filename = custom_filename or cfg["extension"]
        src_path = temp_dir / filename
        bin_path = temp_dir / ("exec.exe" if os.name == "nt" else "exec.bin")
        src_path.write_text(code, encoding="utf-8")

        run_timeout = timeout or cfg["timeout"]

        sub_env = os.environ.copy()
        sub_env["GOMAXPROCS"] = "1"
        sub_env["CGO_ENABLED"] = "0"
        sub_env["GOCACHE"] = "/tmp/gocache"
        sub_env["GOTMPDIR"] = "/tmp"

        try:
            # Stage 1: Compilation
            if cfg["compile_cmd"]:
                comp_cmd = cfg["compile_cmd"].format(src=str(src_path), bin=str(bin_path))
                import shlex
                comp_args = shlex.split(comp_cmd, posix=(os.name != "nt"))
                comp_proc = subprocess.run(
                    comp_args,
                    shell=False,
                    cwd=temp_dir,
                    env=sub_env,
                    capture_output=True,
                    text=True,
                    timeout=min(run_timeout + 10, config.TOOL_TIMEOUT_SECONDS),
                )
                if comp_proc.returncode != 0:
                    return {
                        "exit_code": comp_proc.returncode,
                        "stdout": comp_proc.stdout,
                        "stderr": comp_proc.stderr,
                        "stage": "compilation",
                        "error_type": "CompileError",
                    }

            # Stage 2: Runtime Execution
            if cfg["compile_cmd"]:
                run_args = [str(bin_path)]
            elif lang == "python":
                import sys
                run_args = [sys.executable, str(src_path)]
            elif lang == "javascript":
                run_args = ["node", str(src_path)]
            else:
                import shlex
                run_cmd_str = cfg["run_cmd"].format(src=str(src_path), bin=str(bin_path))
                run_args = shlex.split(run_cmd_str, posix=(os.name != "nt"))

            run_proc = subprocess.run(
                run_args,
                shell=False,
                cwd=temp_dir,
                env=sub_env,
                capture_output=True,
                text=True,
                timeout=run_timeout,
            )

            exit_code = run_proc.returncode
            error_type = None
            if exit_code in (139, -11, 3221225477):  # Linux 139 / NT 0xC0000005
                error_type = "SegmentationFault (SIGSEGV)"
            elif exit_code in (134, -6, 3221225786):  # Linux 134 / NT abort
                error_type = "AssertionFailure / Abort (SIGABRT)"
            elif exit_code != 0:
                error_type = "RuntimeError"

            return {
                "exit_code": exit_code,
                "stdout": run_proc.stdout,
                "stderr": run_proc.stderr,
                "stage": "runtime",
                "error_type": error_type,
            }

        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Execution timed out after {run_timeout}s",
                "stage": "timeout",
                "error_type": "TimeoutError",
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _invoke(self, args: PolyglotRunArgs) -> dict[str, Any]:
        if args.code:
            code = args.code
            lang = args.language or "python"
            fname = None
        elif args.path:
            full = resolve_safe_path(self._workspace, args.path)
            if not full.exists():
                return {
                    "exit_code": 127,
                    "stdout": "",
                    "stderr": f"File not found: {full}",
                    "stage": "runtime",
                    "error_type": "FileNotFoundError",
                }
            code = full.read_text(encoding="utf-8")
            lang = args.language or EXT_MAP.get(full.suffix.lower(), "python")
            fname = full.name
        else:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Neither code nor path provided",
                "stage": "runtime",
                "error_type": "ValueError",
            }

        return self.run(code=code, language=lang, custom_filename=fname, timeout=args.timeout)
