"""Tests for LocalOllamaProvider (constructor + error paths)."""
from __future__ import annotations

from backend.llm.local_provider import LocalOllamaProvider


def test_local_provider_name() -> None:
    p = LocalOllamaProvider()
    assert p.name == "local"


def test_local_provider_raises_on_no_server() -> None:
    p = LocalOllamaProvider(base_url="http://127.0.0.1:1")
    import httpx
    try:
        p.chat([{"role": "user", "content": "hi"}])
        raise AssertionError("Should have raised")
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
        pass

