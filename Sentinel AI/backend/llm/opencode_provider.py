from backend import config
from backend.llm.openai_provider import OpenAIProvider

class OpenCodeProvider(OpenAIProvider):
    def __init__(self, reasoning_type: str = "logical") -> None:
        super().__init__(
            api_key=config.OPEN_CODE_API_KEY,
            max_tokens=None,
            reasoning_type=reasoning_type
        )
        self._base_url = getattr(config, "OPEN_CODE_BASE_URL", "https://opencode.ai/inference/openai/v1")

    @property
    def name(self) -> str:
        return "opencode"

    def _resolve_dynamic_model(self) -> str:
        if hasattr(self, "_fallback_models") and self._fallback_models:
            return self._model
            
        import requests
        try:
            resp = requests.get("https://opencode.ai/inference/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
            else:
                models = ["meta-llama/llama-3-70b-instruct", "meta-llama/llama-3-8b-instruct"]
                
            heavy_models = [m for m in models if any(size in m.lower() for size in ["70b", "72b", "90b", "120b", "405b", "large", "plus"])]
            light_models = [m for m in models if any(size in m.lower() for size in ["8b", "7b", "11b", "14b", "27b", "instant", "small", "mini"])]
            
            if self._reasoning_type == "advanced":
                self._model = heavy_models[0] if heavy_models else models[0]
                self._fallback_models = heavy_models[1:] + light_models + models
            elif self._reasoning_type == "fast":
                self._model = light_models[0] if light_models else models[-1]
                self._fallback_models = light_models[1:] + heavy_models + models
            else:
                self._model = models[0]
                self._fallback_models = models[1:]
                
            seen = {self._model}
            deduped = []
            for m in self._fallback_models:
                if m not in seen:
                    seen.add(m)
                    deduped.append(m)
            self._fallback_models = deduped
        except Exception:
            self._model = "meta-llama/llama-3-70b-instruct"
            self._fallback_models = ["meta-llama/llama-3-8b-instruct"]
            
        return self._model
