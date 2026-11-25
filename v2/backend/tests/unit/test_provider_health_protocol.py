from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend import config
from backend.llm.contracts import Provider, Reply
from backend.llm.openai_provider import OpenAIProvider
from backend.llm.router import LLMRouter


class _FakeModelsAPI:
    def __init__(self, batches: list[list[str]]) -> None:
        self._batches = list(batches)
        self.calls = 0

    def list(self):
        idx = min(self.calls, len(self._batches) - 1)
        self.calls += 1
        return SimpleNamespace(data=[SimpleNamespace(id=m) for m in self._batches[idx]])


def test_dynamic_model_ttl_refresh_and_diff(monkeypatch) -> None:
    p = OpenAIProvider(api_key="test-key", reasoning_type="advanced")
    fake_models = _FakeModelsAPI([["llama-3.1-70b", "qwen-32b"], ["llama-3.3-70b", "qwen-32b"]])
    p._client = SimpleNamespace(models=fake_models)
    p._client_attempted = True

    monkeypatch.setattr(config, "MODEL_REFRESH_TTL_SECONDS", 3600)
    assert p._resolve_dynamic_model() == "llama-3.1-70b"
    assert p._resolve_dynamic_model() == "llama-3.1-70b"
    assert fake_models.calls == 1

    # Simulate TTL expiry: model catalog changed
    p._resolved_at -= 4000
    assert p._resolve_dynamic_model() == "llama-3.3-70b"
    assert fake_models.calls == 2
    assert p._last_model_diff == {"added": ["llama-3.3-70b"], "removed": ["llama-3.1-70b"]}


def test_router_cooldown_recovery_and_probe_cache(monkeypatch) -> None:
    class _StubProvider(Provider):
        def __init__(self, name: str) -> None:
            self._name = name
            self._model = f"{name}-m1"
            self._last_model_diff = {"added": ["new-m2"], "removed": []}
            self.chat_calls = 0

        @property
        def name(self) -> str:
            return self._name

        def chat(self, messages, tools=None, response_schema=None, stream_callback=None) -> Reply:
            self.chat_calls += 1
            return Reply(thought="OK", action=None, finish_reason="stop")

    p1 = _StubProvider("alpha")
    p2 = _StubProvider("beta")
    router = LLMRouter(providers=[p1, p2])

    # Cooldown resets stale fail_count
    monkeypatch.setattr(config, "PROVIDER_HEALTH_COOLDOWN_SECONDS", 60)
    router._tier_providers["strategic"][0]["fail_count"] = 3
    router._tier_providers["strategic"][0]["last_fail_ts"] = time.time() - 120
    router._sort_providers(router._tier_providers["strategic"])
    assert router._tier_providers["strategic"][0]["fail_count"] == 0

    # Passive probe doesn't invoke chat() and caches subsequent call
    r1 = router.probe_providers(active=False, min_interval=300)
    assert r1["cached"] is False
    assert len(r1["providers"]) == 2
    assert p1.chat_calls == 0

    r2 = router.probe_providers(active=False, min_interval=300)
    assert r2["cached"] is True

    # Explicit active probe runs one check per unique provider
    r3 = router.probe_providers(active=True, min_interval=300)
    assert r3["cached"] is False
    assert p1.chat_calls == 1 and p2.chat_calls == 1


def test_server_providers_health_endpoint() -> None:
    from backend.server.server import app

    class _MockProbeProvider(Provider):
        @property
        def name(self) -> str:
            return "mock_probe"

        def chat(self, messages, tools=None, response_schema=None, stream_callback=None) -> Reply:
            return Reply(thought="OK", action=None, finish_reason="stop")

    old_router = getattr(app.state, "router", None)
    app.state.router = LLMRouter(providers=[_MockProbeProvider()])
    try:
        client = TestClient(app)
        resp = client.get("/api/providers/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active_probe"] is False
        assert body["providers"][0]["provider"] == "mock_probe"
    finally:
        app.state.router = old_router
