from __future__ import annotations

import asyncio
import json
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# noqa: E402 — load_dotenv() must run before src imports (config reads env vars)
from backend.ai_agent.runner import AgentRunner  # noqa: E402
from backend.ai_agent.working_memory import Goal  # noqa: E402
from backend.llm.router import LLMRouter  # noqa: E402
from backend.tools.code_exec import RunPythonTool  # noqa: E402
from backend.tools.file_io import ReadFileTool, WriteFileTool  # noqa: E402
from backend.tools.flaky_net import FlakyNetTool  # noqa: E402
from backend.tools.spec_check import SpecCheckTool  # noqa: E402
from backend.tools.test_run import RunTestsTool  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    EXECUTOR.shutdown(wait=False)


app = FastAPI(title="Sentinel AI Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _collect_generated_code(workspace: Path) -> dict[str, str]:
    generated: dict[str, str] = {}
    if not workspace.exists():
        return generated
    for fp in workspace.rglob("*"):
        if fp.is_file():
            try:
                content = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            generated[str(fp.relative_to(workspace))] = content
    return generated


def _build_result(
    success: bool, goal: str, steps_taken: int, self_corrections: int,
    final_output: Any, errors: list[str], terminal_logs: list[str],
    generated_code: dict[str, str], metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": success, "goal": goal, "steps_taken": steps_taken,
        "self_corrections": self_corrections, "final_output": final_output,
        "errors": errors, "terminal_logs": terminal_logs,
        "generated_code": generated_code, "metrics": metrics,
    }


@app.websocket("/ws/run")
async def ws_run(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
    except TimeoutError:
        await websocket.send_json({"type": "error", "message": "Timeout waiting for goal"})
        await websocket.close()
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "Invalid JSON"})
        await websocket.close()
        return

    goal_spec = (payload.get("goal") or "").strip()
    input_text = (payload.get("input") or "").strip()
    if not goal_spec:
        await websocket.send_json({"type": "error", "message": "Goal is required"})
        await websocket.close()
        return

    terminal_logs: list[str] = []
    errors: list[str] = []
    event_deque: deque[dict[str, Any]] = deque()
    event_avail = asyncio.Event()

    def _tline(text: str, line_type: str) -> None:
        ts = time.strftime("%H:%M:%S")
        event_deque.append({
            "type": "terminal_line",
            "text": f"[{ts}] {text}",
            "line_type": line_type,
        })
        event_avail.set()

    def _q(event: dict[str, Any]) -> None:
        event_deque.append(event)
        event_avail.set()

    workspace = Path(mkdtemp(prefix="agent_ws_"))
    workspace.mkdir(parents=True, exist_ok=True)

    if input_text:
        (workspace / "input.txt").write_text(input_text, encoding="utf-8")

    tools = [
        ReadFileTool(workspace), WriteFileTool(workspace),
        RunPythonTool(workspace), RunTestsTool(workspace),
        SpecCheckTool(workspace), FlakyNetTool(),
    ]
    router = LLMRouter()
    _tline(
        f"LLM chain: {', '.join(p.name for p in router._providers)} | "
        f"Tools: {', '.join(t.name for t in tools)}",
        "info",
    )

    def _cb_step(t: Any, ok: Any, thought: Any, ix: Any) -> None:
        _tline(f"Step {ix} ({t}):\n{thought}", "success" if ok else "error")

    def _cb_step_record(r: Any) -> None:
        _q({"type": "step_recorded", "step": r})

    def _cb_correction(c: Any) -> None:
        _tline(
            f"[RECOVERY] Triggered by {c.get('trigger', '?')}\nStrategy: {c.get('strategy', '?')}\nRemaining Budget: {c.get('budget_after', '?')}",
            "recovery",
        )
        _q({"type": "correction_applied", "correction": c})

    def _cb_provider(f: Any, t: Any, r: Any) -> None:
        _tline(f"Provider: {f} -> {t} ({str(r)[:80]})", "error")

    def _cb_file(p: Any, c: Any) -> None:
        _q({"type": "code_update", "path": p, "content": c})

    def _cb_subtask(s: Any) -> None:
        _tline(f"Subtask advanced: {s.get('desc', 'done')}", "success")

    def _cb_stream(stream_type: str, token: str) -> None:
        if stream_type == "thought":
            _q({"type": "stream_thought", "token": token})
        elif stream_type == "action":
            _q({"type": "stream_action", "token": token})

    runner = AgentRunner(
        router=router, tools=tools,
        callbacks={
            "step_started": lambda ix: _tline(f"Initializing AI reasoning step {ix}...", "info"),
            "step_completed": _cb_step,
            "step_recorded": _cb_step_record,
            "correction_applied": _cb_correction,
            "provider_switched": _cb_provider,
            "file_updated": _cb_file,
            "subtask_advanced": _cb_subtask,
            "stream_callback": _cb_stream,
        },
    )

    def run_blocking() -> None:
        try:
            _tline(f"Starting agent: {goal_spec}", "step")
            start = time.time()
            memory = runner.run(Goal(id="WS-1", spec=goal_spec, acceptance=[]), [goal_spec])
            elapsed = round(time.time() - start, 2)

            if memory.unresolvable:
                errors.extend(
                    f"[UNRESOLVABLE {u.subtask_id}] {u.hypothesis}"
                    for u in memory.unresolvable
                )

            generated = _collect_generated_code(workspace)
            metrics_raw = memory.to_metrics()
            budget_remaining = (
                memory.get_budget(memory.active_subtask.id)
                if memory.active_subtask else 0
            )
            success = bool(memory.final_output) and len(errors) == 0

            _tline(
                f"Finished: success={success}, steps={len(memory.executed)}, "
                f"corrections={len(memory.corrections)}, elapsed={elapsed}s",
                "complete",
            )
            _q({"type": "completed", "result": _build_result(
                success=success, goal=goal_spec,
                steps_taken=len(memory.executed),
                self_corrections=len(memory.corrections),
                final_output=memory.final_output or "No output",
                errors=errors, terminal_logs=terminal_logs,
                generated_code=generated,
                metrics={
                    "steps": metrics_raw.get("steps", 0),
                    "self_corrections": metrics_raw.get("self_corrections", 0),
                    "provider_switches": metrics_raw.get("provider_switches", 0),
                    "unresolvable_count": metrics_raw.get("unresolvable_count", 0),
                    "elapsed_seconds": elapsed,
                    "budget_remaining": budget_remaining,
                },
            )})

        except Exception as exc:
            _tline(f"FATAL: {exc}", "error")
            _q({"type": "completed", "result": _build_result(
                success=False, goal=goal_spec, steps_taken=0, self_corrections=0,
                final_output=f"Error: {exc}", errors=[str(exc), traceback.format_exc()],
                terminal_logs=terminal_logs, generated_code={},
                metrics={"steps": 0, "self_corrections": 0,
                         "provider_switches": 0, "unresolvable_count": 0,
                         "elapsed_seconds": 0, "budget_remaining": 0},
            )})

    future = EXECUTOR.submit(run_blocking)

    while True:
        await event_avail.wait()
        event_avail.clear()
        sent_completed = False
        while event_deque:
            event = event_deque.popleft()
            try:
                await websocket.send_json(event)
            except (WebSocketDisconnect, RuntimeError):
                return
            if event.get("type") == "completed":
                sent_completed = True
        if sent_completed:
            break
        if future.done() and not event_deque:
            await websocket.send_json({
                "type": "error",
                "message": "Agent thread finished without completion event",
            })
            break


EVAL_DIR = Path("reports")
eval_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_goal": "",
    "sc_enabled": False,
    "last_result": None
}

from pydantic import BaseModel
from typing import Optional

class RunEvalRequest(BaseModel):
    custom_goals: Optional[list[dict[str, Any]]] = None

@app.post("/api/evaluations/run")
def start_evaluation(req: RunEvalRequest = None) -> dict[str, Any]:
    if eval_state["running"]:
        return {"status": "error", "message": "Evaluation already running"}
    
    eval_state["running"] = True
    eval_state["progress"] = 0
    eval_state["total"] = 0
    eval_state["current_goal"] = ""
    eval_state["sc_enabled"] = False
    
    custom_goals = req.custom_goals if req else None
    
    def _progress(current: int, total: int, goal_id: str, sc_enabled: bool) -> None:
        eval_state["progress"] = current
        eval_state["total"] = total
        eval_state["current_goal"] = goal_id
        eval_state["sc_enabled"] = sc_enabled
        
    def _run_task() -> None:
        try:
            from backend.eval_suite import run_evaluation_suite
            result = run_evaluation_suite(EVAL_DIR, on_progress=_progress, custom_goals=custom_goals)
            eval_state["last_result"] = result
        except Exception as e:
            eval_state["last_result"] = {"error": str(e), "trace": traceback.format_exc()}
        finally:
            eval_state["running"] = False

    EXECUTOR.submit(_run_task)
    return {"status": "started"}

@app.get("/api/evaluations/status")
def get_evaluation_status() -> dict[str, Any]:
    return eval_state

@app.get("/api/evaluations")
def list_evaluations() -> list[dict[str, Any]]:
    if not EVAL_DIR.exists():
        return []
    
    reports = []
    for d in EVAL_DIR.iterdir():
        if d.is_dir():
            summary_file = d / "summary.json"
            if summary_file.exists():
                try:
                    data = json.loads(summary_file.read_text())
                    reports.append(data)
                except Exception:
                    pass
    return sorted(reports, key=lambda x: x.get("timestamp", 0), reverse=True)

@app.get("/api/evaluations/{run_name}")
def get_evaluation(run_name: str) -> dict[str, Any]:
    run_dir = EVAL_DIR / run_name
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        return {"error": "Not found"}
    
    try:
        summary = json.loads(summary_file.read_text())
        runs_data = []
        for f in run_dir.glob("*.json"):
            if f.name != "summary.json":
                runs_data.append(json.loads(f.read_text()))
        summary["detailed_runs"] = runs_data
        return summary
    except Exception as e:
        return {"error": str(e)}
