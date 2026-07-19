"""Tests for LLM router default chain building."""
from __future__ import annotations

from backend.llm.router import LLMRouter


def test_default_router_has_strategic_tier() -> None:
    router = LLMRouter()
    assert "strategic" in router._tier_providers
    assert len(router._tier_providers["strategic"]) >= 1


def test_providers_from_config_are_callable() -> None:
    router = LLMRouter()
    for tier, specs in router._tier_providers.items():
        for spec in specs:
            p = spec["provider"]
            assert hasattr(p, "name")
            assert hasattr(p, "chat")


def test_make_provider_known_names() -> None:
    for name in ("groq", "nvidia_nim", "openrouter", "cerebras", "sambanova", "cohere"):
        p = LLMRouter._make_provider(name, model="test-model")
        assert p is not None
        assert p.name == name


def test_make_provider_unknown_name() -> None:
    assert LLMRouter._make_provider("nonexistent", model="x") is None


def test_sanitize_noop_no_keys() -> None:
    from backend.llm.router import _sanitize
    msg = _sanitize("hello world")
    assert msg == "hello world"


def test_sanitize_noop_empty() -> None:
    from backend.llm.router import _sanitize
    assert _sanitize("") == ""


def test_default_router_chat_works() -> None:
    """Smoke test: router.chat should raise RuntimeError when no configured providers,
    not crash with an AttributeError."""
    router = LLMRouter()
    router._tier_providers["strategic"] = []
    try:
        router.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass  # expected

