"""Executor agent — actually runs the code the Coder wrote.

Wraps the existing `RunPythonTool` so we keep the same sandbox + path-safety
semantics as Sentinel AI 1.0. After running, parses the traceback (if any)
into a structured failure report that feeds into the adaptive retry router.

If `run_tests` is True (passed when subtask indicates testing), it instead
runs `pytest` via `RunTestsTool`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from backend.orchestrator.base import Agent, AgentContext, fail, ok


class Executor(Agent):
    name = "executor"
    human_label = "Executor"

    # ---- traceback parsing ----
    TRACEBACK_ERROR_RE = re.compile(
        r"^\s*(?P<file>.+?)[:\s]+line\s+(?P<line>\d+)\s*[:\s]*(?P<reason>.+)$"
    )
    GCC_ERROR_RE = re.compile(
        r"(?P<file>[^:\s\n]+):(?P<line>\d+):(?:\d+:)?\s*(?:fatal\s+)?error:\s*(?P<msg>.+)",
        re.IGNORECASE,
    )
    EXCEPTION_RE = re.compile(
        r"^(?P<exc>[A-Z]\w*(?:Error|Exception|Warning)[: ]*)",
        re.MULTILINE,
    )
    SYNTAX_RE = re.compile(
        r"(File .+?, line \d+)\n(?:\s+\^|.+?)\n(.*?):(?!:).*?$",
        re.MULTILINE | re.DOTALL,
    )

    def __init__(self, strict: bool = False) -> None:
        super().__init__()
        self._strict = strict

    def run(self, ctx: AgentContext, **kw: Any) -> dict[str, Any]:
        filename = str(kw.get("filename") or ctx.path_to_file or "main.py")
        test_mode = bool(kw.get("test_mode", False))
        node_id = kw.get("node_id") or f"exec_{filename}"

        ctx.bus.emit("agent_started", agent=self.name, label=f"Running: {filename}")
        self.add_graph_node(
            ctx,
            node_id=node_id,
            label=f"▶ Run: {filename}",
            agent="executor",
            status="active",
            parent=kw.get("parent_node"),
        )

        from backend.tools.polyglot_sandbox import PolyglotSandboxTool, EXT_MAP
        detected_lang = kw.get("language") or EXT_MAP.get(Path(filename).suffix.lower(), "python")

        if test_mode and detected_lang == "python":
            from backend.tools.test_run import RunTestsTool

            tool = RunTestsTool(workspace=ctx.workspace)
            args: dict[str, Any] = {"path": kw.get("test_path") or "tests/", "timeout": 30}
        else:
            tool = PolyglotSandboxTool(workspace=ctx.workspace)
            args = {"path": filename, "language": detected_lang, "timeout": 30}

        # --- Safety guardrails ---
        from backend.safety.guardrails import scan as safety_scan

        code_path = ctx.workspace / filename
        if code_path.exists():
            source = code_path.read_text(encoding="utf-8")
            violations = safety_scan(source)
            critical = [v for v in violations if v.severity == "critical"]
            if critical:
                ctx.bus.emit(
                    "terminal_line",
                    text=f"[SAFETY] BLOCKED {filename}: {len(critical)} critical violation(s): "
                         + ", ".join(f"L{v.line}: {v.pattern}" for v in critical[:3]),
                    line_type="error",
                )
                self.update_graph_node(ctx, node_id, status="error",
                                       meta={"safety_violations": len(critical)})
                return fail(
                    "safety_violation",
                    violations=[v.to_dict() for v in critical],
                )

        raw = tool.invoke(args)

        if not raw.get("ok"):
            # Tool crashed (args invalid, etc.)
            self.update_graph_node(ctx, node_id, status="error")
            ctx.bus.emit(
                "code_executed",
                ok=False,
                filename=filename,
                error_type=str(raw.get("error_type", "tool_failure")),
                details=raw.get("details"),
            )
            return fail("tool_invocation_failed", raw=raw)

        # raw.result is a dict shaped as in code_exec.py / test_run.py
        result = raw.get("result", {})
        if isinstance(result, dict):
            if not test_mode:
                exit_code = int(result.get("exit_code", -1))
                stdout = str(result.get("stdout", ""))
                stderr = str(result.get("stderr", ""))
            else:
                exit_code = int(result.get("exit_code", 0))
                stdout = str(result.get("stdout", ""))
                stderr = str(result.get("stderr", ""))
        else:
            self.update_graph_node(ctx, node_id, status="error")
            return fail("unexpected_result_shape", raw=raw)

        ok_exec = exit_code == 0 and (test_mode or not stderr.strip() or ("Traceback" not in stderr and "Error:" not in stderr and "FAILED" not in stderr))
        parsed = self._parse_traceback(stderr) if stderr.strip() else None

        ctx.bus.emit(
            "code_executed",
            ok=ok_exec,
            filename=filename,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            parsed_traceback=parsed,
        )
        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[EXEC] {'PASS' if ok_exec else 'FAIL'} {filename} "
                f"exit={exit_code}"
            ),
            line_type="success" if ok_exec else "error",
        )
        if stdout.strip():
            ctx.bus.emit(
                "terminal_line",
                text=f"[EXEC stdout]\n{stdout[:1500]}",
                line_type="info",
            )
        if stderr.strip():
            ctx.bus.emit(
                "terminal_line",
                text=f"[EXEC stderr]\n{stderr[:1500]}",
                line_type="error",
            )

        self.update_graph_node(
            ctx,
            node_id,
            status="success" if ok_exec else "rejected",
            meta={"exit_code": exit_code},
        )
        ctx.bus.emit("agent_finished", agent=self.name, status="ok" if ok_exec else "fail")

        return ok(
            filename=filename,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            parsed_traceback=parsed,
            success=ok_exec,
            node_id=node_id,
        )

    # ---------- traceback parsing ----------

    def _parse_traceback(self, stderr: str) -> Optional[dict[str, Any]]:
        """Return a structured dict describing the parseable traceback.

        Fields:
            kind:                 'syntax' | 'logic' | 'external' | 'unknown'
            exception:            e.g. 'AssertionError'
            line:                 line number nearest the failure
            snippet:             offending file:line fallback
            demands_strategy:    'line_patch' | 'full_rewrite' | 'backoff' | 'none'
        """
        if not stderr.strip():
            return None

        # Locate the error class.
        match_exc = list(self.EXCEPTION_RE.finditer(stderr))
        exception = match_exc[-1].group("exc").strip().rstrip(":") if match_exc else ""
        line: Optional[int] = None

        # Check for low-level signals & compiler errors
        lowered = stderr.lower()
        if any(sig in lowered for sig in ("segmentation fault", "sigsegv", "0xc0000005")):
            kind = "logic"
            exception = "SegmentationFault"
            demands = "full_rewrite"
        elif any(sig in lowered for sig in ("sigabrt", "assertion failed", "assertion error")):
            kind = "logic"
            exception = "AssertionError"
            demands = "full_rewrite"
        elif not exception and self.GCC_ERROR_RE.search(stderr):
            gcc_m = self.GCC_ERROR_RE.search(stderr)
            kind = "syntax"
            exception = "CompileError"
            demands = "line_patch"
            line = None
            if gcc_m:
                try:
                    line = int(gcc_m.group("line"))
                except Exception:
                    pass
        else:
            # Determine category from exception name.
            kind = "unknown"
            demands = "none"
            if exception:
                if exception.endswith("SyntaxError"):
                    kind = "syntax"
                    demands = "line_patch"
                elif exception in {
                    "TimeoutError", "ConnectionError", "ConnectionRefusedError",
                    "OSError", "IOError", "FileNotFoundError",
                } or exception.lower().endswith("timeouterror"):
                    kind = "external"
                    demands = "backoff"
                elif exception in {"AssertionError", "ValueError", "TypeError",
                                   "IndexError", "KeyError", "ZeroDivisionError", "AttributeError"}:
                    kind = "logic"
                    demands = "full_rewrite"
                elif "Error" in exception or "Exception" in exception:
                    kind = "logic"
                    demands = "full_rewrite"

        # Parse file/line if not already found from compiler.
        if line is None:
            file_line_search = None
            for m in self.TRACEBACK_ERROR_RE.finditer(stderr):
                file_line_search = m
            if file_line_search:
                try:
                    line = int(file_line_search.group("line"))
                except Exception:
                    line = None

        # Detect generic syntax-error block style for older python.
        if kind == "syntax" and line is None:
            sm = self.SYNTAX_RE.search(stderr)
            if sm:
                kind = "syntax"
                demands = "line_patch"
                try:
                    line = int(re.search(r"line (\d+)", sm.group(0)).group(1))
                except Exception:
                    line = None

        return {
            "kind": kind,
            "exception": exception or "<unknown>",
            "line": line,
            "snippet": stderr.strip().splitlines()[-1][:200] if stderr.strip() else "",
            "demands_strategy": demands,
        }
