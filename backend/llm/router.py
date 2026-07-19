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
    def __init__(self, provider_timeout: int | None = None):
        self._provider_timeout = provider_timeout or config.PROVIDER_TIMEOUT_SECONDS
        self._provider_events: list[dict[str, Any]] = []
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._last_successful_provider: str = ""
        self._last_successful_model: str = ""
        
        # Build tier providers from config
        self._tier_providers: dict[str, list[dict[str, Any]]] = {}
        for tier, models in config.MODEL_TIERS.items():
            self._tier_providers[tier] = []
            for spec in models:
                provider = self._make_provider(spec["provider"], spec["model"])
                if provider is not None:
                    self._tier_providers[tier].append({
                        "provider": provider,
                        "is_preferred": spec.get("is_preferred", False),
                        "is_free": spec.get("is_free", False),
                        "usage_count": 0
                    })

    def __del__(self) -> None:
        executor = getattr(self, "_executor", None)
        if executor is not None:
            executor.shutdown(wait=False)

    @staticmethod
    def _make_provider(name: str, model: str) -> Provider | None:
        if name == "groq":
            from backend.llm.groq_provider import GroqProvider
            return GroqProvider(model=model)
        if name == "nvidia_nim":
            from backend.llm.nvidia_nim_provider import NVIDIANIMProvider
            return NVIDIANIMProvider(model=model)
        if name == "openrouter":
            from backend.llm.openrouter_provider import OpenRouterProvider
            return OpenRouterProvider(model=model)
        if name == "cerebras":
            from backend.llm.cerebras_provider import CerebrasProvider
            return CerebrasProvider(model=model)
        if name == "sambanova":
            from backend.llm.sambanova_provider import SambaNovaProvider
            return SambaNovaProvider(model=model)
        if name == "cohere":
            from backend.llm.cohere_provider import CohereProvider
            return CohereProvider(model=model)
        return None

    def _sort_providers(self, providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Sort logic: 
        # 1. Preferred models (OpenRouter, NVIDIA) first (True > False, so sort descending)
        # 2. Free models next (True > False, sort descending)
        # 3. Usage count (lowest first, sort ascending)
        return sorted(
            providers, 
            key=lambda x: (
                not x["is_preferred"],  # False sorts before True, so not True (False) goes first
                not x["is_free"],       # Free models prioritized next
                x["usage_count"]        # Load balance: pick the least used one in the same priority bracket
            )
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
        model_tier: str = "strategic",
    ) -> Reply:
        last_error: str = ""
        
        provider_specs = self._tier_providers.get(model_tier)
        if not provider_specs:
            # Fallback to strategic if tier doesn't exist
            provider_specs = self._tier_providers.get("strategic", [])
            
        sorted_specs = self._sort_providers(provider_specs)
            
        for spec in sorted_specs:
            provider = spec["provider"]
            try:
                future = self._executor.submit(
                    provider.chat, messages, tools, response_schema, stream_callback
                )
                reply = future.result(timeout=self._provider_timeout)
                
                # Update usage count for load balancing
                spec["usage_count"] += 1
                
                self._last_successful_provider = provider.name
                self._last_successful_model = getattr(
                    provider, "model", reply.usage.get("model", "") if reply.usage else ""
                )
                return reply
            except TimeoutError:
                last_error = f"{provider.name} ({getattr(provider, 'model', 'unknown')}) timed out after {self._provider_timeout}s"
                self._provider_events.append(
                    {
                        "ts": time.time(),
                        "from": provider.name,
                        "to": "next",
                        "reason": last_error,
                    }
                )
                continue
            except Exception as e:
                last_error = _sanitize(str(e))
                self._provider_events.append(
                    {
                        "ts": time.time(),
                        "from": provider.name,
                        "to": "next",
                        "reason": last_error[:200],
                    }
                )
                continue
        raise RuntimeError(f"All providers in tier '{model_tier}' exhausted. Last error: {_sanitize(last_error)}")

    @property
    def provider_events(self) -> list[dict[str, Any]]:
        return self._provider_events

    @property
    def last_successful_provider(self) -> str:
        return self._last_successful_provider

    @property
    def last_successful_model(self) -> str:
        return self._last_successful_model
