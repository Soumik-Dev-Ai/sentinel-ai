"""Tests for LLM router default chain building."""
from __future__ import annotations

from backend.llm.router import LLMRouter


def test_default_chain_builds_from_active_providers() -> None:
    router = LLMRouter()
    assert len(router._providers) >= 1
    names = [p.name for p in router._providers]
    assert "groq" in names or "nvidia_nim" in names or "openrouter" in names or "local" in names


def test_default_chain_provider_names_are_strings() -> None:
    router = LLMRouter()
    for p in router._providers:
        assert isinstance(p.name, str)
        assert len(p.name) > 0


def test_sanitize_noop_no_keys() -> None:
    from backend.llm.router import _sanitize
    msg = _sanitize("hello world")
    assert msg == "hello world"


def test_sanitize_noop_empty() -> None:
    from backend.llm.router import _sanitize
    assert _sanitize("") == ""


def test_build_default_chain_returns_list() -> None:
    chain = LLMRouter._build_default_chain()
    assert isinstance(chain, list)


def test_make_provider_known_names() -> None:
    for name in ("groq", "nvidia_nim", "openrouter", "local"):
        p = LLMRouter._make_provider(name)
        assert p is not None
        assert p.name == name


def test_make_provider_unknown_name() -> None:
    assert LLMRouter._make_provider("nonexistent") is None

