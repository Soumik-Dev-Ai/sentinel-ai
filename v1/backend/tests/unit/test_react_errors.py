"""Tests for react_step error paths."""
from __future__ import annotations

from typing import Any

from backend.ai_agent.react import react_step
from backend.ai_agent.working_memory import Goal, WorkingMemory
from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter


class _NoActionProvider(Provider):
    def __init__(self, thought: str) -> None:
        self._thought = thought

    @property
    def name(self) -> str:
        return "test"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        return Reply(thought=self._thought, action=None, finish_reason="stop")


def test_react_step_parses_json_from_thought() -> None:
    memory = WorkingMemory.from_goal(
        Goal(id="t1", spec="test", acceptance=[]), ["test"], 3
    )
    router = LLMRouter(providers=[
        _NoActionProvider('{"thought": "parsed", "action": {"tool": "noop", "args": {}}}')
    ])
    reply = react_step(memory, router, [])
    assert reply.thought == "parsed"
    assert reply.action == {"tool": "noop", "args": {}}


def test_react_step_bad_json_keeps_original_thought() -> None:
    memory = WorkingMemory.from_goal(
        Goal(id="t2", spec="test", acceptance=[]), ["test"], 3
    )
    router = LLMRouter(providers=[
        _NoActionProvider("this is not json at all")
    ])
    reply = react_step(memory, router, [])
    assert reply.thought == "this is not json at all"
    assert reply.action is None


def test_react_step_typeerror_keeps_original() -> None:
    memory = WorkingMemory.from_goal(
        Goal(id="t3", spec="test", acceptance=[]), ["test"], 3
    )
    router = LLMRouter(providers=[
        _NoActionProvider(None)  # type: ignore[arg-type]
    ])
    reply = react_step(memory, router, [])
    assert reply.action is None

