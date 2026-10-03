from __future__ import annotations
from backend import config
from backend.llm.openai_provider import OpenAIProvider

class OpenRouterProvider(OpenAIProvider):
    BASE_URL = "https://openrouter.ai/api/v1"
    def __init__(self, api_key: str | None = None, reasoning_type: str = "advanced", max_tokens: int = 4096):
        super().__init__(api_key=(api_key or config.OPENROUTER_API_KEY), reasoning_type=reasoning_type, max_tokens=max_tokens)
    @property
    def name(self) -> str: return "openrouter"
