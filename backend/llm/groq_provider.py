from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 4096,
    ):
        self._api_key = api_key or config.GROQ_API_KEY
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
        return "groq"


