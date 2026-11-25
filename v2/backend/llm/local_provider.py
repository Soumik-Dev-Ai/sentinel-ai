"""Local Ollama provider — last-resort degradation (OpenAI-compatible API)."""
from __future__ import annotations

import os

from backend.llm.openai_provider import OpenAIProvider


class LocalOllamaProvider(OpenAIProvider):
    BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

    def __init__(self, reasoning_type: str = "logic", model: str | None = None):
        # Ollama ignores the key but the SDK requires a non-empty string.
        super().__init__(api_key="ollama", reasoning_type=reasoning_type)
        self._model = model or self.DEFAULT_MODEL

    def _ensure_client(self) -> None:
        """Reuse the lazy client, but fail fast if Ollama isn't reachable."""
        if self._client is None and not self._client_attempted:
            try:
                import httpx

                httpx.get("http://localhost:11434/api/tags", timeout=2).raise_for_status()
            except Exception as e:
                self._client_attempted = True  # don't probe on every call
                raise RuntimeError(f"local Ollama unavailable at {self.BASE_URL}: {e}") from e
        super()._ensure_client()

    @property
    def name(self) -> str:
        return "local"
