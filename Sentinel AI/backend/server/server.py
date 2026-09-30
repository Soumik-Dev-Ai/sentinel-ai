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

# Sentinel AI 2.0 multi-agent pipeline
from backend.orchestrator.base import EventBus  # noqa: E402
from backend.orchestrator.pipeline import MultiAgentPipeline  # noqa: E402
from backend.orchestrator.escalation import GLOBAL_ESCALATION_MANAGER  # noqa: E402


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
    """Bidirectional WebSocket endpoint supporting:
      1. Legacy single-agent ReAct flow (mode='react')
      2. New multi-agent pipeline (mode='multi' — default)
      3. Inbound messages (besides the initial goal):
         {"type": "escalation_answer", "escalation_id": "...", "answer": "..."}
         {"type": "cancel"}
         {"type": "start", "goal": "...", "input": "...", "mode": "multi|react"}

    Forward protocol:
      The server transmits JSON events directly from the EventBus,
      augmented with the legacy event types so the existing UI keeps working.
    """
    await websocket.accept()

    # ---- Per-connection state ----
    event_deque: deque[dict[str, Any]] = deque()
    event_avail = asyncio.Event()
    cancel_event = asyncio.Event()
    terminal_logs: list[str] = []
    errors: list[str] = []

    loop = asyncio.get_event_loop()

    def _q(event: dict[str, Any]) -> None:
        event_deque.append(event)
        event_avail.set()

    def _bus_to_deque(event_dict: dict[str, Any]) -> None:
        # event_dict is already a serializable dict (AgentEvent.to_dict())
        _q(event_dict)

    # Build a per-connection EventBus subscriber that bridges events into the deque.
    def _subscriber(ev_agent_event) -> None:
        # ev_agent_event is AgentEvent dataclass. Convert to dict.
        try:
            payload = ev_agent_event.to_dict()
        except Exception:
            payload = {"type": "error", "message": "Failed to serialize event"}
        _bus_to_deque(payload)

    # ---- Receive initial goal OR a structured "start" message ----
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

    # Accept either {"goal": "...", "input": "..."} (legacy) or
    # {"type":"start", "goal":"...", "input":"...", "mode":"react|multi"} (new).
    if payload.get("type") == "start":
        goal_spec = str(payload.get("goal") or "").strip()
        input_text = str(payload.get("input") or "").strip()
        mode = str(payload.get("mode") or "multi").strip().lower()
    else:
        goal_spec = str(payload.get("goal") or "").strip()
        input_text = str(payload.get("input") or "").strip()
        mode = str(payload.get("mode") or "multi").strip().lower()

    if not goal_spec:
        await websocket.send_json({"type": "error", "message": "Goal is required"})
        await websocket.close()
        return

    # Build a fresh EventBus + pipeline so concurrent clients don't share.
    bus = EventBus()

    def _tline(text: str, line_type: str) -> None:
        ts = time.strftime("%H:%M:%S")
        _q({
            "type": "terminal_line",
            "text": f"[{ts}] {text}",
            "line_type": line_type,
        })
        terminal_logs.append(text)

    workspace = Path(mkdtemp(prefix="agent_ws_"))
    workspace.mkdir(parents=True, exist_ok=True)

    if input_text:
        (workspace / "input.txt").write_text(input_text, encoding="utf-8")

    future = None

    # =========================================================
    # MULTI-AGENT PIPELINE MODE (Sentinel AI 2.0)
    # =========================================================
    _escalation_manager = GLOBAL_ESCALATION_MANAGER  # fallback

    if mode in ("multi", "multi-v2"):
        pipeline = MultiAgentPipeline(bus=bus)
        _escalation_manager = pipeline.active_escalation

        # Subscribe to events BEFORE starting the worker.
        bus.subscribe(lambda ev: _subscriber(ev))

        def run_blocking() -> None:
            try:
                _tline(f"[Multi-Agent] Pipeline started: {goal_spec}", "step")
                pipeline.run(
                    goal=goal_spec,
                    acceptance=[],
                    workspace=workspace,
                    input_text=input_text,
                )
            except Exception as exc:
                _q({"type": "error", "message": f"FATAL: {exc}"})
                _q({"type": "completed", "result": {
                    "success": False, "goal": goal_spec,
                    "final_output": f"Error: {exc}",
                    "errors": [str(exc), traceback.format_exc()],
                    "terminal_logs": terminal_logs,
                    "generated_code": {},
                    "steps_taken": 0, "self_corrections": 0,
                    "metrics": {"elapsed_seconds": 0, "tokens_total": 0,
                                "cost_total_usd": 0, "calls": 0},
                    "subtasks": [], "plan": {},
                }})

        future = EXECUTOR.submit(run_blocking)

    # =========================================================
    # LEGACY REACT MODE (1.0 backward compat)
    # =========================================================
    else:
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
                f"[RECOVERY] Triggered by {c.get('trigger', '?')}\n"
                f"Strategy: {c.get('strategy', '?')}\n"
                f"Remaining Budget: {c.get('budget_after', '?')}",
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

    # =========================================================
    # Pump events to the WebSocket while running.
    # Concurrently listen for inbound messages from the client
    # (escalation answers / cancel).
    # =========================================================
    async def _drain_outgoing() -> None:
        sent_completed = False
        while True:
            await event_avail.wait()
            event_avail.clear()
            while event_deque:
                ev = event_deque.popleft()
                try:
                    await websocket.send_json(ev)
                except (WebSocketDisconnect, RuntimeError):
                    return
                if ev.get("type") == "completed":
                    sent_completed = True
            if sent_completed:
                return
            if future is not None and future.done() and not event_deque:
                await websocket.send_json({
                    "type": "error",
                    "message": "Agent thread finished without completion event",
                })
                return
            if cancel_event.is_set() and not event_deque:
                return

    async def _listen_incoming() -> None:
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                mtype = data.get("type")
                if mtype == "escalation_answer":
                    _escalation_manager.answer(
                        data.get("escalation_id", ""),
                        str(data.get("answer", "")),
                    )
                elif mtype == "cancel":
                    cancel_event.set()
                    return
                elif mtype == "ping":
                    await websocket.send_json({"type": "pong", "ts": time.time()})
        except WebSocketDisconnect:
            cancel_event.set()
        except Exception:
            # ignore malformed inbound
            pass

    # Run both pumps concurrently.
    tasks = [
        asyncio.ensure_future(_drain_outgoing()),
        asyncio.ensure_future(_listen_incoming()),
    ]
    try:
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


EVAL_DIR = Path("reports")
EVAL_STATE_FILE = EVAL_DIR / "eval_state.json"

def get_shared_eval_state():
    if EVAL_STATE_FILE.exists():
        try:
            return json.loads(EVAL_STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "running": False,
        "progress": 0,
        "total": 0,
        "current_goal": "",
        "sc_enabled": False,
        "last_result": None
    }

def save_shared_eval_state(state):
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_STATE_FILE.write_text(json.dumps(state))

from pydantic import BaseModel
from typing import Optional

class RunEvalRequest(BaseModel):
    custom_goals: Optional[list[dict[str, Any]]] = None

@app.post("/api/evaluations/run")
def start_evaluation(req: RunEvalRequest = None) -> dict[str, Any]:
    state = get_shared_eval_state()
    if state["running"]:
        return {"status": "error", "message": "Evaluation already running"}
    
    state.update({
        "running": True,
        "progress": 0,
        "total": 0,
        "current_goal": "",
        "sc_enabled": False,
        "last_result": None
    })
    save_shared_eval_state(state)
    
    custom_goals = req.custom_goals if req else None
    
    def _progress(current: int, total: int, goal_id: str, sc_enabled: bool) -> None:
        curr_state = get_shared_eval_state()
        curr_state.update({
            "progress": current,
            "total": total,
            "current_goal": goal_id,
            "sc_enabled": sc_enabled
        })
        save_shared_eval_state(curr_state)
        
    def _run_task() -> None:
        try:
            from backend.eval_suite import run_evaluation_suite
            result = run_evaluation_suite(EVAL_DIR, on_progress=_progress, custom_goals=custom_goals)
            
            final_state = get_shared_eval_state()
            final_state["last_result"] = result
            final_state["running"] = False
            save_shared_eval_state(final_state)
        except Exception as e:
            final_state = get_shared_eval_state()
            final_state["last_result"] = {"error": str(e), "trace": traceback.format_exc()}
            final_state["running"] = False
            save_shared_eval_state(final_state)

    EXECUTOR.submit(_run_task)
    return {"status": "started"}

@app.get("/api/evaluations/status")
def get_evaluation_status() -> dict[str, Any]:
    return get_shared_eval_state()

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

@app.get('/api/history')
def get_run_history(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    from backend.db.store import list_runs
    return list_runs(limit=limit, offset=offset)

