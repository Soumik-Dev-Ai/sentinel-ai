from __future__ import annotations
from backend import config
from backend.llm.openai_provider import OpenAIProvider

class GroqProvider(OpenAIProvider):
    BASE_URL = "https://api.groq.com/openai/v1"
    def __init__(self, api_key: str | None = None, reasoning_type: str = "advanced", max_tokens: int = 4096):
        super().__init__(api_key=(api_key or config.GROQ_API_KEY), reasoning_type=reasoning_type, max_tokens=max_tokens)
    @property
    def name(self) -> str: return "groq"
