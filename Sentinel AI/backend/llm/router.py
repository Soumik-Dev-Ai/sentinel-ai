from __future__ import annotations

import concurrent.futures
import time
from typing import Any

from backend import config
from backend.llm.contracts import Provider, Reply


def _sanitize(msg: str) -> str:
    patterns = [
        config.GROQ_API_KEY,
        config.NVIDIA_NIM_API_KEY,
        config.OPENROUTER_API_KEY,
        getattr(config, "SAMBANOVA_API_KEY", ""),
        getattr(config, "COHERE_API_KEY", ""),
        config.CEREBRAS_API_KEY,
    ]
    for key in patterns:
        if key:
            msg = msg.replace(key, "***")
    return msg


class LLMRouter:
    def __init__(self, provider_timeout: int | None = None, providers: list[Provider] | None = None):
        self._provider_timeout = provider_timeout or config.PROVIDER_TIMEOUT_SECONDS
        self._provider_events: list[dict[str, Any]] = []
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._last_successful_provider: str = ""
        self._last_successful_model: str = ""

        self._tier_providers: dict[str, list[dict[str, Any]]] = {}
        if providers is not None:
            # Explicit (mock) chain: seed the default tier, skip config.
            self._tier_providers["strategic"] = [
                {"provider": p, "is_preferred": True, "is_free": True, "is_backup": False, "usage_count": 0}
                for p in providers
            ]
        else:
            for tier, models in config.MODEL_TIERS.items():
                self._tier_providers[tier] = []
                for spec in models:
                    provider = self._make_provider(spec["provider"], spec.get("reasoning_type", "logical"))
                    if provider is not None:
                        self._tier_providers[tier].append({
                            "provider": provider,
                            "is_preferred": spec.get("is_preferred", False),
                            "is_free": spec.get("is_free", False),
                            "is_backup": spec.get("is_backup", False),
                            "usage_count": 0
                        })
        # Legacy flat view (manual_test.py / server react mode / agent_cli.py).
        self._providers = [
            spec["provider"] for specs in self._tier_providers.values() for spec in specs
        ]

    def __del__(self) -> None:
        executor = getattr(self, "_executor", None)
        if executor is not None:
            executor.shutdown(wait=False)

    @staticmethod
    def _make_provider(name: str, reasoning_type: str = "logical", model: str | None = None) -> Provider | None:
        def _mk(module: str, cls_name: str) -> Provider:
            import importlib
            cls = getattr(importlib.import_module(f"backend.llm.{module}"), cls_name)
            p = cls(reasoning_type=reasoning_type)
            if model:
                p._model = model
            return p

        factories = {
            "groq": ("groq_provider", "GroqProvider"),
            "nvidia_nim": ("nvidia_nim_provider", "NVIDIANIMProvider"),
            "openrouter": ("openrouter_provider", "OpenRouterProvider"),
            "cerebras": ("cerebras_provider", "CerebrasProvider"),
            "sambanova": ("sambanova_provider", "SambaNovaProvider"),
            "opencode": ("opencode_provider", "OpenCodeProvider"),
            "cohere": ("cohere_provider", "CohereProvider"),
        }
        if name not in factories:
            return None
        return _mk(*factories[name])

    def _sort_providers(self, providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        providers.sort(
            key=lambda x: (
                not x.get("is_backup", False),  # Normal providers (True) sorted before backups (False)
                x.get("is_preferred", False),
                x.get("is_free", False),
                -x.get("usage_count", 0)
            ),
            reverse=True,
        )
        return providers

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, response_schema: dict[str, Any] | None = None, stream_callback: Any = None, model_tier: str = "strategic") -> Reply:
        tier_list = self._tier_providers.get(model_tier, [])
        if not tier_list:
            raise RuntimeError(f"All providers in tier '{model_tier}' exhausted. Chain of failures: none configured")

        sorted_list = self._sort_providers(tier_list)
        error_chain = []

        for p in sorted_list:
            provider_inst: Provider = p["provider"]
            start_t = time.time()
            try:
                if hasattr(provider_inst, "_resolve_dynamic_model"):
                    provider_inst._resolve_dynamic_model()
                    
                future = self._executor.submit(
                    provider_inst.chat,
                    messages,
                    tools,
                    response_schema,
                    stream_callback,
                )
                reply = future.result(timeout=self._provider_timeout)

                p["usage_count"] += 1
                self._last_successful_provider = provider_inst.name
                self._last_successful_model = getattr(provider_inst, "_model", "dynamic")
                return reply

            except concurrent.futures.TimeoutError:
                last_error = f"{provider_inst.name} ({getattr(provider_inst, '_model', 'dynamic')}) timed out after {self._provider_timeout}s"
                error_chain.append(last_error)
                self._provider_events.append({
                    "ts": time.time(),
                    "from": provider_inst.name,
                    "to": "next",
                    "reason": last_error
                })
            except Exception as e:
                last_error = f"{provider_inst.name} failed: {str(e)}"
                error_chain.append(last_error)
                self._provider_events.append({
                    "ts": time.time(),
                    "from": provider_inst.name,
                    "to": "next",
                    "reason": last_error
                })

        # If we got here, ALL providers failed. Let's show the user exactly why each one failed!
        chain_summary = " | ".join([_sanitize(err) for err in error_chain])
        raise RuntimeError(f"All providers in tier '{model_tier}' exhausted. Chain of failures: {chain_summary}")

    @property
    def last_successful_provider(self) -> str:
        return self._last_successful_provider
        
    @property
    def last_successful_model(self) -> str:
        return self._last_successful_model
        
    @property
    def provider_events(self):
        return self._provider_events
        
    @provider_events.setter
    def provider_events(self, value):
        self._provider_events = value
