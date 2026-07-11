"""Tests for OpenAI provider with mocked SDK."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.llm.openai_provider import OpenAIProvider


def test_init_no_sdk() -> None:
    """ImportError is swallowed â€” client stays None."""
    with patch.dict("sys.modules", {"openai": None}):
        p = OpenAIProvider(api_key="sk-test")
    assert p._client is None  # noqa: SLF001


def test_chat_requires_client() -> None:
    p = OpenAIProvider()  # no key â†’ no client
    import pytest  # noqa: F401
    with pytest.raises(RuntimeError, match="not configured"):
        p.chat([{"role": "user", "content": "hi"}])


def _mock_streaming_chunks(
    content: str = "hello",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
) -> list:
    """Build a list of fake streaming chunk MagicMock objects.

    Each element mimics one delta chunk from the OpenAI streaming API.
    """
    chunks = []
    # Content delta chunk(s)
    if content:
        chunk = MagicMock()
        choice = MagicMock()
        choice.delta.content = content
        choice.delta.tool_calls = None
        choice.finish_reason = None
        chunk.choices = [choice]
        chunks.append(chunk)

    # Tool-call delta chunk(s)
    if tool_calls:
        tc = tool_calls[0]
        chunk = MagicMock()
        choice = MagicMock()
        choice.delta.content = None
        choice.delta.tool_calls = [tc]
        choice.finish_reason = None if finish_reason else None
        chunk.choices = [choice]
        chunks.append(chunk)

    # Final chunk with finish reason
    chunk = MagicMock()
    choice = MagicMock()
    choice.delta.content = None
    choice.delta.tool_calls = None
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunks.append(chunk)
    return chunks


def test_chat_basic() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_streaming_chunks()
    p = OpenAIProvider(api_key="sk-test")
    p._client = client  # noqa: SLF001
    reply = p.chat([{"role": "user", "content": "hi"}])
    assert reply.thought == "hello"
    assert reply.action is None


def test_chat_with_tool_calls() -> None:
    tc = MagicMock()
    tc.function.name = "write_file"
    tc.function.arguments = '{"path": "x.txt", "content": "hi"}'

    client = MagicMock()
    client.chat.completions.create.return_value = _mock_streaming_chunks(
        tool_calls=[tc]
    )
    p = OpenAIProvider(api_key="sk-test")
    p._client = client  # noqa: SLF001
    reply = p.chat(
        [{"role": "user", "content": "write"}],
        tools=[{"name": "write_file", "description": "write", "input_schema": {}}],
    )
    assert reply.action is not None
    assert reply.action["tool"] == "write_file"
    assert reply.action["args"] == {"path": "x.txt", "content": "hi"}


def test_chat_tool_call_bad_json() -> None:
    tc = MagicMock()
    tc.function.name = "write_file"
    tc.function.arguments = "not-json"

    client = MagicMock()
    client.chat.completions.create.return_value = _mock_streaming_chunks(
        tool_calls=[tc]
    )
    p = OpenAIProvider(api_key="sk-test")
    p._client = client  # noqa: SLF001
    reply = p.chat([{"role": "user", "content": "write"}], tools=[{"name": "write_file"}])
    assert reply.action is not None
    assert "raw" in reply.action["args"]

