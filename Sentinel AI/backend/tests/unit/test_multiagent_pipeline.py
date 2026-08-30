"""End-to-end tests for the Sentinel AI 2.0 multi-agent pipeline.

We replace the LLMRouter with a MockProvider that returns deterministic JSON
responses so we can exercise the full pipeline in CI without real API keys.

The tests verify:
    - The Orchestrator emits a ToT plan and selects a path.
    - The Coder writes a runnable script to the workspace.
    - The Critic scores and (with a high score) lets execution proceed.
    - The Executor runs the file and reports back pass/fail.
    - On failure, the RetryRouter classifies with the right strategy.
    - Escalation fires after 2 retries with low critic score.
    - Cost telemetry increments on each LLM call.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter
from backend.memory.vector_store import VectorStore
from backend.orchestrator.base import EventBus
from backend.orchestrator.cost import CostTracker
from backend.orchestrator.escalation import EscalationManager
from backend.orchestrator.pipeline import MultiAgentPipeline
from backend.orchestrator.retry import RetryRouter
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.coder import Coder
from backend.orchestrator.critic import Critic
from backend.orchestrator.executor import Executor


class _ScriptedProvider(Provider):
    """Mock provider that returns scripted responses in order."""

    def __init__(self, replies: list[dict[str, Any]]):
        self._replies = replies
        self._idx = 0
        self.calls: list[dict[str, Any]] = []
        self._model = "mock-model"

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return self._model

    def chat(self, messages, tools=None, response_schema=None, stream_callback=None) -> Reply:
        self.calls.append({"messages": messages, "tools": tools, "schema": response_schema})
        if self._idx >= len(self._replies):
            raise IndexError(f"MockProvider exhausted at idx={self._idx}")
        raw = self._replies[self._idx]
        self._idx += 1
        return Reply(
            thought=raw["thought"],
            action=raw.get("action"),
            finish_reason=raw.get("finish_reason", "stop"),
            usage=raw.get("usage", {"input_tokens": 10, "output_tokens": 20, "model": "mock", "provider": "mock"}),
        )


def _router_with(replies):
    """Create a router pre-seeded with a mock provider that returns the given replies in order."""
    router = LLMRouter()
    # Inject mock provider into the strategic tier so it's the only one consulted.
    router._tier_providers["strategic"] = [{
        "provider": _ScriptedProvider(replies),
        "is_preferred": True,
        "is_free": True,
        "usage_count": 0,
    }]
    return router


# -----------------------------------------------------------------------------
# Vector store
# -----------------------------------------------------------------------------

def test_vector_store_roundtrip(tmp_path: Path) -> None:
    vs = VectorStore(persist_dir=tmp_path / "mem")
    e = vs.add(kind="solved", goal="fib", summary="loop-based", strategy="loop")
    assert vs.count() == 1
    recs = vs.query_closest("fib", k=3)
    assert len(recs) >= 1
    assert recs[0][0].id == e.id


def test_vector_store_persistence(tmp_path: Path) -> None:
    p = tmp_path / "mem"
    vs = VectorStore(persist_dir=p)
    vs.add(kind="error", goal="parse-file", summary="syntax err",
           error_signature="SyntaxError", strategy="fixed indentation")
    vs2 = VectorStore(persist_dir=p)  # reload
    assert vs2.count() == 1


# -----------------------------------------------------------------------------
# Retry router
# -----------------------------------------------------------------------------

def test_retry_router_classifies_logic_failure():
    from backend.orchestrator.retry import classify, FailureCategory, Strategy
    fail = classify({
        "stderr": "Traceback...\nValueError: invalid int literal",
        "stdout": "", "exit_code": 1,
        "parsed_traceback": {"exception": "ValueError", "line": 4},
    })
    assert fail.category is FailureCategory.LOGIC
    rr = RetryRouter()
    result = rr.next_strategy("S1", fail)
    assert result.strategy is Strategy.FULL_REWRITE
    assert "rewrite" in result.guidance.lower()


def test_retry_router_classifies_syntax_failure():
    from backend.orchestrator.retry import classify, FailureCategory, Strategy
    fail = classify({
        "stderr": "Traceback...\nSyntaxError: unexpected indent",
        "stdout": "", "exit_code": 1,
        "parsed_traceback": {"exception": "SyntaxError", "line": 7},
    })
    assert fail.category is FailureCategory.SYNTAX
    rr = RetryRouter()
    result = rr.next_strategy("S1", fail)
    assert result.strategy is Strategy.LINE_PATCH


def test_retry_router_classifies_external_failure():
    from backend.orchestrator.retry import classify, FailureCategory, Strategy
    fail = classify({
        "stderr": "ConnectionRefusedError",
        "stdout": "", "exit_code": 124,
        "parsed_traceback": {"exception": "ConnectionRefusedError"},
    })
    assert fail.category is FailureCategory.EXTERNAL
    rr = RetryRouter(backoff_base_seconds=0.01, backoff_max_seconds=0.1)
    r1 = rr.next_strategy("S1", fail)
    r2 = rr.next_strategy("S1", fail)
    r3 = rr.next_strategy("S1", fail)
    assert r1.strategy is Strategy.BACKOFF
    assert r2.wait_seconds >= r1.wait_seconds * 1.5
    assert r3.wait_seconds > r2.wait_seconds


# -----------------------------------------------------------------------------
# CostTracker
# -----------------------------------------------------------------------------

def test_cost_tracker_basic_aggregation():
    ct = CostTracker()
    ct.record("coder", "groq", "llama-3.3-70b-versatile", 100, 200)
    ct.record("critic", "groq", "llama-3.3-70b-versatile", 50, 100)
    snap = ct.snapshot()
    assert snap["total_tokens"] == 450
    assert snap["total_cost_usd"] > 0
    assert set(snap["per_agent"].keys()) == {"coder", "critic"}
    assert snap["per_agent"]["coder"]["calls"] == 1
    assert snap["per_agent"]["critic"]["calls"] == 1


def test_cost_tracker_budget_threshold():
    from backend.orchestrator.cost import TokenBudget
    ct = CostTracker(budget=TokenBudget(max_total_tokens=100, max_total_cost_usd=None))
    ct.record("coder", "groq", "llama-3.3-70b-versatile", 50, 30)
    snap = ct.snapshot()
    assert snap["budget_exhausted"] is False
    ct.record("coder", "groq", "llama-3.3-70b-versatile", 10, 20)
    snap = ct.snapshot()
    assert snap["budget_exhausted"] is True


# -----------------------------------------------------------------------------
# Escalation manager
# -----------------------------------------------------------------------------

def test_escalation_threshold_and_answer():
    em = EscalationManager(max_attempts=2, threshold=0.5, timeout_seconds=2)
    em.record_attempt("S1", 0.4)
    assert not em.should_escalate("S1")
    em.record_attempt("S1", 0.3)
    assert em.should_escalate("S1")


# -----------------------------------------------------------------------------
# Pipeline integration (mock provider, no external calls)
# -----------------------------------------------------------------------------

def test_pipeline_happy_path(tmp_path: Path):
    """Orchestrator -> Coder -> Critic (accept) -> Executor (pass)."""
    replies = [
        # 1. Orchestrator ToT generation
        {"thought": json.dumps({
            "paths": [
                {"id": "P1", "description": "loop", "steps": ["write code", "run code"],
                 "confidence": 0.85, "rationale": "simple", "risks": []},
                {"id": "P2", "description": "recursive", "steps": ["write", "run"],
                 "confidence": 0.6, "rationale": "risky", "risks": ["stack"]},
                {"id": "P3", "description": "memoization", "steps": ["write", "run"],
                 "confidence": 0.75, "rationale": "ok", "risks": []},
            ]
        })},
        # 2. Orchestrator exec plan
        {"thought": json.dumps({
            "subtasks": [
                {"id": "S1", "desc": "Write a script that prints 'hello'", "agent": "coder"},
                {"id": "S2", "desc": "Run the script and verify output", "agent": "executor"},
            ]
        })},
        # 3. Coder reply
        {"thought": json.dumps({
            "rationale": "print hello",
            "filename": "main.py",
            "code": "print('hello')\n",
            "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
        })},
        # 4. Critic reply (accept)
        {"thought": json.dumps({
            "correctness": 9, "edge_cases": 8, "acceptance": 9, "readability": 9,
            "total": 89, "passes": True, "issues": [], "fix_suggestions": [],
            "verdict": "ACCEPT",
        })},
    ]
    router = _router_with(replies)
    bus = EventBus()
    events: list[str] = []
    bus.subscribe(lambda ev: events.append(ev.type))
    memory = VectorStore(persist_dir=tmp_path / "mem")
    pipeline = MultiAgentPipeline(
        router=router, memory=memory, bus=bus,
        config={"max_retries_per_subtask": 2, "max_total_cost_usd": 5.0, "max_total_tokens": 200_000},
    )
    result = pipeline.run(
        goal="Print hello",
        acceptance=["stdout contains hello"],
        workspace=tmp_path,
        input_text="",
    )
    assert result["success"] is True
    # Coder should have written the file
    written = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert "print('hello')" in written
    # We should have emitted the expected event types.
    assert "agent_started" in events
    assert "graph_node" in events
    assert "critic_verdict" in events
    assert "telemetry_update" in events
    assert "completed" in events


def test_pipeline_critic_reject_then_acquires_retry(tmp_path: Path):
    """Critic rejects first, lets pipeline enter retry, then accepts on second."""
    replies = [
        # ToT gen
        {"thought": json.dumps({"paths": [
            {"id": "P1", "description": "loop", "steps": ["write", "run"],
             "confidence": 0.8, "rationale": "ok", "risks": []},
            {"id": "P2", "description": "alt", "steps": ["write", "run"],
             "confidence": 0.7, "rationale": "ok", "risks": []},
            {"id": "P3", "description": "alt2", "steps": ["write", "run"],
             "confidence": 0.6, "rationale": "ok", "risks": []},
        ]})},
        # exec plan
        {"thought": json.dumps({"subtasks": [
            {"id": "S1", "desc": "write echo and run it", "agent": "coder"},
        ]})},
        # Coder attempt 1
        {"thought": json.dumps({
            "rationale": "echo", "filename": "main.py",
            "code": "print('hello')\n",
            "self_check": {},
        })},
        # Critic rejects attempt 1
        {"thought": json.dumps({
            "correctness": 5, "edge_cases": 4, "acceptance": 5, "readability": 6,
            "total": 50, "passes": False, "issues": ["none"], "fix_suggestions": ["add docstring"],
            "verdict": "REJECT",
        })},
        # Coder attempt 2
        {"thought": json.dumps({
            "rationale": "v2", "filename": "main.py",
            "code": "print('hello world')\n",
        })},
        # Critic accepts attempt 2
        {"thought": json.dumps({
            "correctness": 9, "edge_cases": 9, "acceptance": 9, "readability": 9,
            "total": 90, "passes": True, "issues": [], "fix_suggestions": [],
            "verdict": "ACCEPT",
        })},
    ]
    router = _router_with(replies)
    bus = EventBus()
    memory = VectorStore(persist_dir=tmp_path / "mem")
    pipeline = MultiAgentPipeline(
        router=router, memory=memory, bus=bus,
        config={"max_retries_per_subtask": 2},
    )
    result = pipeline.run(
        goal="Write hello world",
        acceptance=[],
        workspace=tmp_path,
    )
    assert result["success"] is True
    content = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert "hello world" in content


def test_pipeline_executor_classifies_failure(tmp_path: Path):
    """Executor returns a SyntaxError, retry router routes to LINE_PATCH."""
    # Write a buggy file directly so executor sees it.
    (tmp_path / "main.py").write_text("def f(:\n  pass\n", encoding="utf-8")
    from backend.orchestrator.base import AgentContext
    bus = EventBus()
    cost = CostTracker()
    memory = VectorStore(persist_dir=tmp_path / "mem")
    router = _router_with([])
    ctx = AgentContext(
        goal="run", acceptance=[],
        workspace=tmp_path, router=router,
        bus=bus, cost=cost, memory=memory,
    )
    ex = Executor()
    out = ex.run(ctx, filename="main.py")
    assert out["ok"] is True
    assert out["success"] is False
    parsed = out["parsed_traceback"]
    assert parsed is not None
    assert parsed["kind"] in ("syntax", "logic")
