from __future__ import annotations
import json
from typing import Any
from backend.llm.contracts import Provider, Reply

class OpenAIProvider(Provider):
    def __init__(self, api_key: str = "", reasoning_type: str = "advanced", max_tokens: int = 4096):
        self._api_key = api_key
        self._reasoning_type = reasoning_type
        self._model = None
        self._max_tokens = max_tokens
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, base_url=getattr(self, "_base_url", None))
            except ImportError:
                pass

    @property
    def name(self) -> str: return "openai"
        
    def _resolve_dynamic_model(self) -> str:
        if self._model: return self._model
        
        # Hardcoded overrides for providers with massive catalogs or non-standard names
        if self.name == "openrouter":
            self._model = "openrouter/auto"
            return self._model
        if self.name == "cohere":
            self._model = "command-r-plus-08-2024" if self._reasoning_type == "advanced" else "command-r-08-2024"
            return self._model
            
        # Dynamic lookup (runs for Groq, NVIDIA NIM, Cerebras, SambaNova, etc.)
        try:
            if not self._client: return "default-model"
            model_list = self._client.models.list()
            valid_families = ["llama", "gpt", "claude", "mistral", "qwen", "mixtral", "codellama"]
            invalid_families = ["whisper", "dall", "embed", "orpheus", "guard", "vision", "audio"]
            
            models = []
            for m in model_list.data:
                mid = m.id.lower()
                if any(bad in mid for bad in invalid_families): continue
                if any(good in mid for good in valid_families):
                    models.append(m.id)
            
            if not models:
                models = [m.id for m in model_list.data if "embed" not in m.id.lower() and "guard" not in m.id.lower()]

            # Classify models by size indicators in their names
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
                
            # Deduplicate fallbacks, preserving order
            seen = {self._model}
            deduped = []
            for m in self._fallback_models:
                if m not in seen:
                    seen.add(m)
                    deduped.append(m)
            self._fallback_models = deduped
                    
        except Exception:
            self._model = "default-model"
            self._fallback_models = []
            
        return self._model

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, response_schema: dict[str, Any] | None = None, stream_callback: Any = None) -> Reply:
        if self._client is None: raise RuntimeError(f"{self.name} client not configured (no API key or SDK missing)")
        self._resolve_dynamic_model()

        formatted_tools = None
        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append({"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {"type": "object", "properties": {}})}})

        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "max_tokens": self._max_tokens, "temperature": 0.1}
        if formatted_tools: kwargs["tools"] = formatted_tools
        if response_schema: kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "schema", "schema": response_schema, "strict": True}}

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "max_tokens" in err_str:
                kwargs.pop("max_tokens", None)
                resp = self._client.chat.completions.create(**kwargs)
            elif any(x in err_str for x in ["429", "rate limit", "capacity", "quota", "too many requests"]):
                # Rate limited on primary model. Try fallback models if available!
                success = False
                if hasattr(self, "_fallback_models") and self._fallback_models:
                    for fallback in self._fallback_models:
                        kwargs["model"] = fallback
                        try:
                            resp = self._client.chat.completions.create(**kwargs)
                            self._model = fallback # permanently switch to the working model
                            success = True
                            break
                        except Exception:
                            continue
                
                if not success:
                    raise e
            else:
                raise e

        choice = resp.choices[0]
        msg = choice.message
        
        usage = resp.usage
        usage_dict = {"model": self._model, "input_tokens": usage.prompt_tokens if usage else 0, "output_tokens": usage.completion_tokens if usage else 0, "total_tokens": usage.total_tokens if usage else 0}

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            tc = msg.tool_calls[0]
            action = {"name": tc.function.name, "args": json.loads(tc.function.arguments)}
            return Reply(thought="", action=action, finish_reason="tool_calls", usage=usage_dict)

        return Reply(thought=msg.content or "", action=None, finish_reason=choice.finish_reason or "stop", usage=usage_dict)
