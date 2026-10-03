import requests
from typing import Any, Optional
from backend import config
from backend.llm.contracts import Provider, Reply

class CohereProvider(Provider):
    BASE_URL = "https://api.cohere.com/v1/chat"

    def __init__(self, api_key: str | None = None, reasoning_type: str = "advanced"):
        self._api_key = api_key or getattr(config, "COHERE_API_KEY", "")
        self._reasoning_type = reasoning_type
        self._model = "command-r-plus-08-2024" if reasoning_type == "advanced" else "command-r-08-2024"

    @property
    def name(self) -> str: return "cohere"

    def _resolve_dynamic_model(self):
        if hasattr(self, "_fallback_models") and self._fallback_models:
            return self._model
            
        try:
            resp = requests.get("https://api.cohere.com/v1/models", headers={"Authorization": f"Bearer {self._api_key}"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("models", [])
                models = [m["name"] for m in data if "chat" in m.get("endpoints", [])]
            else:
                models = ["command-r-plus-08-2024", "command-r-08-2024"]
                
            heavy_models = [m for m in models if "plus" in m.lower() or "32b" in m.lower()]
            light_models = [m for m in models if "plus" not in m.lower() and "32b" not in m.lower()]
            
            if self._reasoning_type == "advanced":
                self._model = heavy_models[0] if heavy_models else models[0]
                self._fallback_models = heavy_models[1:] + light_models
            elif self._reasoning_type == "fast":
                self._model = light_models[0] if light_models else models[-1]
                self._fallback_models = light_models[1:] + heavy_models
            else:
                self._model = models[0]
                self._fallback_models = models[1:]
        except Exception:
            self._model = "command-r-plus-08-2024" if self._reasoning_type == "advanced" else "command-r-08-2024"
            self._fallback_models = ["command-r-08-2024"] if self._reasoning_type == "advanced" else ["command-r-plus-08-2024"]
            
        return self._model

    def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, response_schema: Optional[dict[str, Any]] = None, stream_callback: Any = None) -> Reply:
        if not self._api_key: raise RuntimeError("COHERE_API_KEY is not set.")
        
        chat_history = []
        message = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system": chat_history.append({"role": "SYSTEM", "message": content})
            elif role == "user":
                if msg == messages[-1]: message = content
                else: chat_history.append({"role": "USER", "message": content})
            elif role == "assistant": chat_history.append({"role": "CHATBOT", "message": content})
        if not message and chat_history: message = chat_history.pop()["message"]

        headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {self._api_key}"}
        
        while True:
            payload = {"model": self._model, "message": message, "chat_history": chat_history}
            resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=120)
            
            if resp.status_code in [429, 400, 403, 404, 402, 500, 503]:
                if hasattr(self, "_fallback_models") and self._fallback_models:
                    self._model = self._fallback_models.pop(0)
                    continue
            
            resp.raise_for_status()
            data = resp.json()
            
            text = data.get("text", "")
            usage = data.get("meta", {}).get("billed_units", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            return Reply(thought=text, action=None, finish_reason="stop", usage={"model": self._model, "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens})
