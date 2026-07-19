import requests
from typing import Any, Optional
from backend import config
from backend.llm.contracts import Provider, Reply

class CohereProvider(Provider):
    BASE_URL = "https://api.cohere.com/v1/chat"

    def __init__(self, api_key: str | None = None, model: str = "command-r-plus"):
        self._api_key = api_key or getattr(config, "COHERE_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "cohere"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        response_schema: Optional[dict[str, Any]] = None,
        stream_callback: Any = None,
    ) -> Reply:
        if not self._api_key:
            raise RuntimeError("COHERE_API_KEY is not set.")

        # Convert OpenAI-style messages to Cohere chat_history + message
        chat_history = []
        message = ""
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                chat_history.append({"role": "SYSTEM", "message": content})
            elif role == "user":
                if msg == messages[-1]:
                    message = content
                else:
                    chat_history.append({"role": "USER", "message": content})
            elif role == "assistant":
                chat_history.append({"role": "CHATBOT", "message": content})

        if not message and chat_history:
            message = chat_history.pop()["message"]

        payload = {
            "model": self._model,
            "message": message,
            "chat_history": chat_history,
        }
        
        # We ignore tools/response_schema for Cohere in this basic wrapper
        # unless strictly necessary for the orchestrator

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self._api_key}"
        }

        resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        
        text = data.get("text", "")
        usage = data.get("meta", {}).get("billed_units", {})
        
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return Reply(
            thought=text,
            action=None,
            finish_reason="stop",
            usage={
                "model": self._model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
