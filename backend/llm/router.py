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
    ]
    for key in patterns:
        if key:
            msg = msg.replace(key, "***")
    return msg


class LLMRouter:
    def __init__(
        self,
        providers: list[Provider] | None = None,
        provider_timeout: int | None = None,
    ):
        if providers is None:
            providers = self._build_default_chain()
        self._providers = providers
        self._provider_timeout = provider_timeout or config.PROVIDER_TIMEOUT_SECONDS
        self._provider_events: list[dict[str, Any]] = []
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def __del__(self) -> None:
        executor = getattr(self, "_executor", None)
        if executor is not None:
            executor.shutdown(wait=False)

    @staticmethod
    def _build_default_chain() -> list[Provider]:
        chain: list[Provider] = []
        for name in config.LLM_CHAIN:
            provider = LLMRouter._make_provider(name)
            if provider is not None:
                chain.append(provider)
        return chain

    @staticmethod
    def _make_provider(name: str) -> Provider | None:
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

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        last_error: str = ""
        for provider in self._providers:
            try:
                future = self._executor.submit(
                    provider.chat, messages, tools, response_schema, stream_callback
                )
                reply = future.result(timeout=self._provider_timeout)
                return reply
            except TimeoutError:
                last_error = f"{provider.name} timed out after {self._provider_timeout}s"
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
        raise RuntimeError(f"All providers exhausted. Last error: {_sanitize(last_error)}")

    @property
    def provider_events(self) -> list[dict[str, Any]]:
        return self._provider_events


