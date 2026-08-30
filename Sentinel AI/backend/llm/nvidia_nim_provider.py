from __future__ import annotations

from backend import config
from backend.llm.openai_provider import OpenAIProvider


class NVIDIANIMProvider(OpenAIProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "meta/llama-3.1-70b-instruct",
        max_tokens: int = 4096,
    ):
        self._api_key = api_key or config.NVIDIA_NIM_API_KEY
        self._model = model
        self._max_tokens = max_tokens
        self._client = None
        base_url = config.NVIDIA_NIM_BASE_URL
        if self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key, base_url=base_url)
            except ImportError:
                pass

    @property
    def name(self) -> str:
        return "nvidia_nim"


