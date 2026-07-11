"""Unit tests for LLM contracts: Reply, Provider protocol, and make_tool_specs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.llm.contracts import Provider, Reply, make_tool_specs
from backend.tools.base import ToolProtocol


class _DummyProvider(Provider):
    @property
    def name(self) -> str:
        return "dummy"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        return Reply(thought="ok", action=None, finish_reason="stop")


class _DummyArgs(BaseModel):
    x: int


class _DummyTool(ToolProtocol):
    name = "dummy_tool"
    description = "test tool"
    args_schema = _DummyArgs
    return_schema = None

    def _invoke(self, args: _DummyArgs) -> Any:
        return {}


def test_each_provider_returns_conforming_reply() -> None:
    provider = _DummyProvider()
    reply = provider.chat([])
    assert isinstance(reply, Reply)
    assert isinstance(reply.thought, str)
    assert reply.finish_reason == "stop"


def test_router_contract_transparent_to_agent() -> None:
    provider = _DummyProvider()
    reply = provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"name": "t1", "description": "d"}],
        response_schema={"type": "object"},
    )
    assert reply.thought == "ok"


def test_make_tool_specs_includes_name_and_schema() -> None:
    specs = make_tool_specs([_DummyTool()])
    assert len(specs) == 1
    assert "name" in specs[0]
    assert "input_schema" in specs[0]
    assert specs[0]["name"] == "dummy_tool"


def test_reply_action_can_be_none() -> None:
    r = Reply(thought="no action needed", action=None, finish_reason="stop")
    assert r.action is None
    assert r.thought == "no action needed"

