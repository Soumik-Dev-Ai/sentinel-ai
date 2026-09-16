from __future__ import annotations
from backend import config
from backend.llm.openai_provider import OpenAIProvider

class CerebrasProvider(OpenAIProvider):
    BASE_URL = "https://api.cerebras.ai/v1"
    def __init__(self, api_key: str | None = None, reasoning_type: str = "advanced", max_tokens: int = 4096):
        super().__init__(api_key=(api_key or config.CEREBRAS_API_KEY), reasoning_type=reasoning_type, max_tokens=max_tokens)
        if self._api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, base_url=self.BASE_URL)
            except ImportError:
                pass
    @property
    def name(self) -> str: return "cerebras"
