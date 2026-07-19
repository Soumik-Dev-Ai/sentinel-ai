from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str | None = None, model: str = "anthropic/claude-3.5-sonnet"):
        self._api_key = api_key or config.OPENROUTER_API_KEY
        self._model = model
        self._max_tokens = 1500
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key, base_url=self.BASE_URL)
            except ImportError:
                pass

    @property
    def name(self) -> str:
        return "openrouter"


