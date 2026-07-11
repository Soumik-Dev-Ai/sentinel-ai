"""Unit tests for the LLM router: fallback chain, failover events, timeout."""
from __future__ import annotations

from typing import Any

import pytest

from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter


class _ScriptedProvider(Provider):
    def __init__(self, name: str, script: list[Any]) -> None:
        self._name = name
        self._script = list(script)
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        idx = self.calls
        self.calls += 1
        item = self._script[idx] if idx < len(self._script) else self._script[-1]
        if isinstance(item, Exception):
            raise item
        return Reply(
            thought=item["thought"],
            action=item.get("action"),
            finish_reason="stop",
        )


def _reply(text: str) -> dict[str, Any]:
    return {"thought": text, "action": {"tool": "noop", "args": {}}}


def test_fallback_chain_order() -> None:
    p1 = _ScriptedProvider("p1_slow", [RuntimeError("429")])
    p2 = _ScriptedProvider("p2_fast", [_reply("from-p2")])
    router = LLMRouter(providers=[p1, p2])
    reply = router.chat([])
    assert reply.thought == "from-p2"
    assert p1.calls == 1 and p2.calls == 1
    assert len(router.provider_events) >= 1


def test_fallback_chain_multiple_failures_continues() -> None:
    p1 = _ScriptedProvider("p1", [RuntimeError("err1")])
    p2 = _ScriptedProvider("p2", [RuntimeError("err2")])
    p3 = _ScriptedProvider("p3", [_reply("from-p3")])
    router = LLMRouter(providers=[p1, p2, p3])
    reply = router.chat([])
    assert reply.thought == "from-p3"
    assert len(router.provider_events) == 2


def test_provider_switches_logged_in_provider_events() -> None:
    p1 = _ScriptedProvider("p1", [RuntimeError("429")])
    p2 = _ScriptedProvider("p2", [_reply("ok")])
    router = LLMRouter(providers=[p1, p2])
    router.chat([])
    events = router.provider_events
    assert len(events) >= 1
    assert events[0]["from"] == "p1"
    assert events[0]["to"] == "next"


def test_slow_provider_times_out_and_falls_back() -> None:
    import time as _time

    class _SlowProvider(Provider):
        def __init__(self, name: str, delay: float) -> None:
            self._name = name
            self._delay = delay

        @property
        def name(self) -> str:
            return self._name

        def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            response_schema: dict[str, Any] | None = None,
            stream_callback: Any = None,
        ) -> Reply:
            _time.sleep(self._delay)
            return Reply(
                thought="too-late", action={"tool": "noop", "args": {}},
                finish_reason="stop",
            )

    fast = _ScriptedProvider("fast", [_reply("from-fast")])
    slow = _SlowProvider("slow", 5.0)
    router = LLMRouter(providers=[slow, fast], provider_timeout=1)
    reply = router.chat([])
    assert reply.thought == "from-fast"
    events = router.provider_events
    assert any("timed out" in e.get("reason", "") for e in events)


def test_all_providers_exhausted_raises() -> None:
    p1 = _ScriptedProvider("p1", [RuntimeError("a")])
    p2 = _ScriptedProvider("p2", [RuntimeError("b")])
    router = LLMRouter(providers=[p1, p2])
    with pytest.raises(RuntimeError, match="All providers exhausted"):
        router.chat([])


def test_first_provider_succeeds_no_events() -> None:
    p1 = _ScriptedProvider("p1", [_reply("ok")])
    p2 = _ScriptedProvider("p2", [_reply("also-ok")])
    router = LLMRouter(providers=[p1, p2])
    reply = router.chat([])
    assert reply.thought == "ok"
    assert len(router.provider_events) == 0


def test_empty_provider_list_raises() -> None:
    router = LLMRouter(providers=[])
    with pytest.raises(RuntimeError, match="All providers exhausted"):
        router.chat([])


def test_provider_events_empty_on_success() -> None:
    p = _ScriptedProvider("p1", [_reply("ok")])
    router = LLMRouter(providers=[p])
    router.chat([])
    assert len(router.provider_events) == 0


def test_chat_passes_tools_and_schema() -> None:
    class _SchemaProvider(Provider):
        @property
        def name(self) -> str:
            return "schema"

        def chat(self, messages, tools=None, response_schema=None, stream_callback=None):
            return Reply(
                thought=f"tools={bool(tools)},schema={bool(response_schema)}",
                action={"tool": "noop", "args": {}},
                finish_reason="stop",
            )

    router = LLMRouter(providers=[_SchemaProvider()])
    reply = router.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"name": "t1", "description": "", "input_schema": {}}],
        response_schema={"type": "object", "properties": {}},
    )
    assert "tools=True" in reply.thought
    assert "schema=True" in reply.thought

