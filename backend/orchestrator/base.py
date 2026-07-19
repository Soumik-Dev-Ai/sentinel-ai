"""Base types & event bus shared by all Sentinel AI 2.0 agents.

Design goals
------------
* Decouple agents from the WebSocket layer: agents emit `AgentEvent`s through
  an `EventBus`, and the WebSocket server subscribes to the bus and forwards
  events over the wire.
* Allow fine-grained UI updates: every agent lifecycle change (start, stream
  token, judge score, retry, escalate, finish) is its own event.
* Be thread-safe (agents run inside a ThreadPoolExecutor invoked from the
  async event loop of FastAPI).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional

from backend.llm.contracts import Reply
from backend.llm.router import LLMRouter
from backend.orchestrator.cost import CostTracker
from backend.memory.vector_store import VectorStore


# -----------------------------------------------------------------------------
# Event types
# -----------------------------------------------------------------------------

# All event types pushed to the frontend over the WebSocket.
EVENT_TYPES = {
    "agent_started",         # agent phase started (planning / writing / judging / executing)
    "agent_finished",         # agent phase finished
    "agent_stream",           # streaming token from an agent
    "graph_node",             # add or update a node in the execution graph
    "graph_edge",             # add an edge in the execution graph
    "critic_verdict",         # critic produced a score
    "code_written",           # coder wrote a file
    "code_executed",          # executor produced stdout/stderr
    "retry_strategy",         # retry router chose a strategy
    "needs_human_review",     # escalation to human-in-the-loop
    "resume_from_human",      # human answered an escalation
    "telemetry_update",       # token / cost snapshot
    "memory_stored",          # a memory was written to the vector db
    "memory_recall",          # memory was retrieved from the vector db
    "terminal_line",          # free-form log line
    "step_recorded",          # generic milestone record (compat w/ legacy UI)
    "correction_applied",     # generic correction (compat w/ legacy UI)
    "completed",              # the whole run is done
    "error",                  # fatal error
}


@dataclass
class AgentEvent:
    """One event in the agent lifecycle.

    `ts` is set automatically; `seq` is assigned by the EventBus so the
    frontend can defensively re-sort if needed.
    """
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Flatten the `payload` fields into the top-level dict so the frontend
        can read e.g. ``msg.result`` instead of ``msg.payload.result``."""
        flat: dict[str, Any] = {"type": self.type, "seq": self.seq, "ts": self.ts}
        flat.update(self.payload)
        return flat


# -----------------------------------------------------------------------------
# Event Bus
# -----------------------------------------------------------------------------

class EventBus:
    """Thread-safe publish/subscribe bus for AgentEvents.

    The WebSocket server attaches one subscriber which drains events into the
    per-client deque. Agents never touch the WebSocket directly.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[Callable[[AgentEvent], None]] = []
        self._seq = 0

    def subscribe(self, cb: Callable[[AgentEvent], None]) -> None:
        with self._lock:
            self._subs.append(cb)

    def unsubscribe(self, cb: Callable[[AgentEvent], None]) -> None:
        with self._lock:
            if cb in self._subs:
                self._subs.remove(cb)

    def publish(self, event: AgentEvent) -> None:
        with self._lock:
            self._seq += 1
            event.seq = self._seq
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                # Never let a slow/crashing subscriber break the agent.
                pass

    def emit(self, type_: str, **payload: Any) -> AgentEvent:
        """Convenience helper: build + publish."""
        ev = AgentEvent(type=type_, payload=payload)
        self.publish(ev)
        return ev


# -----------------------------------------------------------------------------
# Execution context (passed to all agents)
# -----------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Everything an agent needs to do its job without touching globals."""
    goal: str
    acceptance: list[str]
    workspace: Any  # pathlib.Path
    router: LLMRouter
    bus: EventBus
    cost: CostTracker
    memory: VectorStore
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # filled in by subtask routing
    subtask_id: str = ""
    subtask_desc: str = ""
    model_tier: str = "strategic"
    path_to_file: Optional[str] = None  # current file under work
    # mutable scratch pad shared across agents
    scratch: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Base Agent
# -----------------------------------------------------------------------------

class Agent:
    """Common agent shape — subclassed by Orchestrator / Coder / Critic / Executor.

    Subclasses implement `run(ctx, **kw)` returning a structured dict (the
    "result envelope"). All emit events through `ctx.bus`.
    """

    name: str = "agent"
    human_label: str = "Agent"

    def __init__(self) -> None:
        self._node_counter = 0

    # ---------- helpers ----------

    def _llm_chat(
        self,
        ctx: AgentContext,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = True,
    ) -> Reply:
        """Wrap router.chat with telemetry + cost tracking."""
        reply = ctx.router.chat(
            messages,
            tools=tools,
            stream_callback=(self._make_stream_cb(ctx) if stream else None),
            model_tier=ctx.model_tier,
        )
        # Use the router's tracked last-successful provider/model (streaming
        # providers frequently return empty usage dicts, so we rely on the
        # router itself to tell us who answered).
        provider_name = ctx.router.last_successful_provider or ""
        model_name = ctx.router.last_successful_model or ""
        usage = reply.usage or {}
        if usage:
            model_name = usage.get("model", model_name or "default")
            provider_name = usage.get("provider", provider_name or "router")
        else:
            # Fallback token estimate when provider omits usage stats.
            in_toks = self._estimate_tokens(messages)
            out_toks = max(1, len((reply.thought or "").split()))
            usage = {
                "input_tokens": in_toks, "output_tokens": out_toks,
                "model": model_name, "provider": provider_name,
            }
        ctx.cost.record_from_reply(
            agent=self.name,
            provider=provider_name or model_name,
            model=model_name or "default",
            reply_usage=usage,
        )
        return reply

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Rough token estimate when the provider omits usage stats."""
        try:
            import tiktoken  # type: ignore[import-not-found]
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            return sum(len((m.get("content") or "").split()) for m in messages)
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(enc.encode(content))
            elif isinstance(content, list):
                for piece in content:
                    if isinstance(piece, dict):
                        total += len(enc.encode(str(piece.get("text", ""))))
        return total

    def _make_stream_cb(self, ctx: AgentContext) -> Callable[[str, str], None]:
        def _cb(kind: str, token: str) -> None:
            ctx.bus.emit(
                "agent_stream",
                agent=self.name,
                kind=kind,  # "thought" or "action"
                token=token,
                ts=time.time(),
            )
        return _cb

    # ---------- graph helpers ----------

    def add_graph_node(
        self,
        ctx: AgentContext,
        node_id: str,
        label: str,
        agent: str,
        status: str = "active",
        parent: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Tell the frontend to render a node in the execution graph."""
        payload = {
            "id": node_id,
            "label": label,
            "agent": agent,
            "status": status,
            "meta": meta or {},
        }
        if parent is not None:
            payload["parent"] = parent
        ctx.bus.emit("graph_node", **payload)
        if parent:
            ctx.bus.emit(
                "graph_edge",
                id=f"{parent}->{node_id}",
                source=parent,
                target=node_id,
                animated=(status == "active"),
            )

    def update_graph_node(
        self,
        ctx: AgentContext,
        node_id: str,
        **fields: Any,
    ) -> None:
        ctx.bus.emit("graph_node", id=node_id, **fields)

    # ---------- to be overridden ----------

    def run(self, ctx: AgentContext, **kw: Any) -> dict[str, Any]:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Result envelope shape used across agents
# -----------------------------------------------------------------------------

def ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def fail(reason: str, **payload: Any) -> dict[str, Any]:
    return {"ok": False, "reason": reason, **payload}
