from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class SambaNovaProvider(OpenAIProvider):
    BASE_URL = "https://api.sambanova.ai/v1"

    def __init__(self, api_key: str | None = None, model: str = "Meta-Llama-3.1-70B-Instruct"):
        self._api_key = api_key or getattr(config, "SAMBANOVA_API_KEY", "")
        self._model = model
        self._max_tokens = 4096
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key, base_url=self.BASE_URL)
            except ImportError:
                pass

    @property
    def name(self) -> str:
        return "sambanova"
