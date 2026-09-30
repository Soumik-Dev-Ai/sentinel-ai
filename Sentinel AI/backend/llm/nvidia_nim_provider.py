from backend.llm.openai_provider import OpenAIProvider
from backend import config

class NVIDIANIMProvider(OpenAIProvider):
    def __init__(self, reasoning_type: str = "advanced"):
        self._base_url = config.NVIDIA_NIM_BASE_URL
        super().__init__(api_key=config.NVIDIA_NIM_API_KEY, reasoning_type=reasoning_type)
        
    @property
    def name(self) -> str:
        return "nvidia_nim"
