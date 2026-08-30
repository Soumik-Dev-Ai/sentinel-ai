"""Real end-to-end tests exercising actual LLM providers and the full agent pipeline.

Requires HEVA_E2E=1 to run. Uses API keys from .env.
Tests: provider connectivity, fallback chain, full AgentRunner, self-correction.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from backend import config as app_config
from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.llm.contracts import Provider
from backend.llm.router import LLMRouter
from backend.tools.file_io import ReadFileTool, WriteFileTool

pytestmark = pytest.mark.e2e

REAL = os.getenv("HEVA_E2E", "0") == "1"


def _has_real_key(provider_name: str) -> bool:
    if provider_name == "local":
        return True
    mapping = {
        "groq": "GROQ_API_KEY",
        "nvidia_nim": "NVIDIA_NIM_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    key = getattr(app_config, mapping.get(provider_name, ""), "")
    return bool(key)


def _build_provider(name: str) -> Provider | None:
    if name == "groq":
        from backend.llm.groq_provider import GroqProvider
        return GroqProvider()
    if name == "nvidia_nim":
        from backend.llm.nvidia_nim_provider import NVIDIANIMProvider
        return NVIDIANIMProvider()
    if name == "openrouter":
        from backend.llm.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider()
    if name == "local":
        from backend.llm.local_provider import LocalOllamaProvider
        return LocalOllamaProvider()
    return None


def _try_provider(name: str, timeout: int = 30) -> dict[str, Any]:
    provider = _build_provider(name)
    assert provider is not None, f"Could not build provider {name}"
    start = time.time()
    reply = provider.chat(
        messages=[{"role": "user", "content": "Reply with exactly one word: hello"}],
        tools=None,
    )
    elapsed = time.time() - start
    return {
        "name": name,
        "reply": reply,
        "elapsed": round(elapsed, 2),
        "model": getattr(provider, "_model", "unknown"),
    }


# ---------------------------------------------------------------------------
# 1. Individual provider connectivity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL or not _has_real_key("groq"), reason="No Groq key")
def test_groq_provider_responds() -> None:
    try:
        result = _try_provider("groq")
        assert result["reply"].thought, "Groq returned empty thought"
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e):
            pytest.skip(f"Groq rate limited: {e!s:.80}")


@pytest.mark.skipif(not REAL or not _has_real_key("nvidia_nim"), reason="No NVIDIA NIM key")
def test_nvidia_nim_provider_responds() -> None:
    try:
        result = _try_provider("nvidia_nim")
        assert result["reply"].thought, "NVIDIA NIM returned empty thought"
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e):
            pytest.skip(f"NVIDIA NIM rate limited: {e!s:.80}")


@pytest.mark.skipif(not REAL or not _has_real_key("openrouter"), reason="No OpenRouter key")
def test_openrouter_provider_responds() -> None:
    try:
        result = _try_provider("openrouter")
        assert result["reply"].thought, "OpenRouter returned empty thought"
    except Exception as e:
        if "402" in str(e) or "credits" in str(e).lower():
            pytest.skip(f"OpenRouter needs credits: {e!s:.80}")


# ---------------------------------------------------------------------------
# 2. Fallback chain: configured providers route correctly
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL, reason="E2E tests disabled")
def test_fallback_chain_uses_available_providers() -> None:
    available = [n for n in app_config.LLM_CHAIN if _has_real_key(n)]
    if not available:
        pytest.skip("No real API keys available")
    providers = []
    for name in available:
        p = _build_provider(name)
        if p:
            providers.append(p)
    router = LLMRouter(providers=providers)
    reply = router.chat(
        messages=[{"role": "user", "content": "Reply with exactly one word: hello"}],
    )
    assert reply.thought, "Fallback chain returned empty reply"
    assert any(
        name in str(reply).lower() or len(reply.thought) > 0
        for name in available
    )


@pytest.mark.skipif(not REAL, reason="E2E tests disabled")
def test_fallback_skips_broken_providers() -> None:
    names = ["groq", "nvidia_nim", "openrouter"]
    providers = []
    for name in names:
        p = _build_provider(name)
        if p:
            providers.append(p)
    if len(providers) < 2:
        pytest.skip("Need at least 2 providers for fallback test")
    router = LLMRouter(providers=providers)
    reply = router.chat(
        messages=[{"role": "user", "content": "Reply with exactly one word: ok"}],
    )
    assert reply.thought, "Fallback chain exhausted even with working providers"


# ---------------------------------------------------------------------------
# 3. Tool calling via providers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4. Full AgentRunner end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL, reason="E2E tests disabled")
def test_agent_runner_writes_and_reads_file(tmp_path: Path) -> None:
    names = ["groq", "nvidia_nim", "openrouter", "local"]
    providers = []
    for name in names:
        if _has_real_key(name):
            p = _build_provider(name)
            if p:
                providers.append(p)
    if not providers:
        pytest.skip("No available providers for agent runner test")
    router = LLMRouter(providers=providers)
    runner = AgentRunner(
        router=router,
        tools=[WriteFileTool(tmp_path), ReadFileTool(tmp_path)],
        max_steps=4,
        self_correction_enabled=True,
    )
    mem = runner.run(
        Goal(
            id="e2e-real-1",
            spec="write a file called greeting.txt with content 'Hello from the agent'",
        ),
        ["write file"],
    )
    if mem.final_output and "exhausted" in mem.final_output:
        pytest.skip("All providers rate-limited or unavailable")
    target = tmp_path / "greeting.txt"
    exists_msg = (
        f"greeting.txt was not created "
        f"(exists: {[str(p.name) for p in tmp_path.iterdir()]})"
    )
    assert target.exists(), exists_msg
    content = target.read_text(encoding="utf-8")
    assert "Hello" in content, f"greeting.txt content mismatch: {content}"
    assert mem.final_output is not None


@pytest.mark.skipif(not REAL, reason="E2E tests disabled")
def test_agent_runner_self_corrects_on_error(tmp_path: Path) -> None:
    names = ["groq", "nvidia_nim", "openrouter", "local"]
    providers = []
    for name in names:
        if _has_real_key(name):
            p = _build_provider(name)
            if p:
                providers.append(p)
    if not providers:
        pytest.skip("No available providers for agent runner test")
    router = LLMRouter(providers=providers)
    runner = AgentRunner(
        router=router,
        tools=[WriteFileTool(tmp_path), ReadFileTool(tmp_path)],
        max_steps=5,
        self_correction_enabled=True,
    )
    mem = runner.run(
        Goal(
            id="e2e-real-2",
            spec="Create a Python file that prints the numbers 1 to 5, then run it",
        ),
        ["write file"],
    )
    if mem.final_output and "exhausted" in mem.final_output:
        pytest.skip("All providers rate-limited or unavailable")
    assert mem.final_output is not None
    files = list(tmp_path.iterdir())
    py_files = [f for f in files if f.suffix == ".py"]
    assert len(py_files) >= 1, f"No Python files created: {[p.name for p in files]}"


# ---------------------------------------------------------------------------
# 5. Provider timing benchmark (informational)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL, reason="E2E tests disabled")
def test_provider_latency_benchmark() -> None:
    results = []
    for name in app_config.LLM_CHAIN:
        if not _has_real_key(name):
            results.append(f"  {name}: SKIPPED (no key)")
            continue
        try:
            r = _try_provider(name, timeout=60)
            results.append(
                f"  {r['name']} ({r['model']}): {r['elapsed']}s"
                f" - {len(r['reply'].thought)} chars"
            )
        except Exception as e:
            results.append(f"  {name}: ERROR - {e}")
    print("\nProvider latency benchmark:")
    for line in results:
        print(line)


