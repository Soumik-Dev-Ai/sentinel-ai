from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class TogetherProvider(OpenAIProvider):
    BASE_URL = "https://api.together.xyz/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        max_tokens: int = 4096,
    ):
        self._api_key = api_key or config.TOGETHER_API_KEY
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
        return "together"
