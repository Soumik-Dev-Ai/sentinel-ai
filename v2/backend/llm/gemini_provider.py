from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-pro",
        max_tokens: int = 4096,
    ):
        self._api_key = api_key or config.GEMINI_API_KEY
        self._model = model
        self._max_tokens = max_tokens
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key, base_url=self.BASE_URL)
            except ImportError:
                pass

    @property
    def name(self) -> str:
        return "gemini"
