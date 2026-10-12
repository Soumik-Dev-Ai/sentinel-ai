from __future__ import annotations
import json
from typing import Any
from backend.llm.contracts import Provider, Reply

class OpenAIProvider(Provider):
    BASE_URL: str | None = None
    _base_url: str | None = None

    def __init__(self, api_key: str = "", reasoning_type: str = "advanced", max_tokens: int = 4096):
        self._api_key = api_key
        self._reasoning_type = reasoning_type
        self._model = None
        self._max_tokens = max_tokens
        self._client = None
        self._client_attempted = False

    def _ensure_client(self) -> None:
        """Lazily build the OpenAI client on first use (avoids slow SSL/head-of-line at init)."""
        if self._client is not None or self._client_attempted:
            return
        self._client_attempted = True
        if self._api_key:
            try:
                from openai import OpenAI
                from backend import config
                self._client = OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url or self.BASE_URL,
                    timeout=getattr(config, "PROVIDER_CALL_TIMEOUT_SECONDS", 35),
                )
            except ImportError:
                pass

    @property
    def name(self) -> str: return "openai"
        
    def _resolve_dynamic_model(self) -> str:
        self._ensure_client()
        if self._model: return self._model
        
        # Hardcoded overrides for providers with massive catalogs or non-standard names
        if self.name == "cohere":
            self._model = "command-r-plus-08-2024" if self._reasoning_type == "advanced" else "command-r-08-2024"
            return self._model
            
        # Dynamic lookup (runs for Groq, NVIDIA NIM, Cerebras, SambaNova, OpenRouter, etc.)
        try:
            if not self._client: return "default-model"
            model_list = self._client.models.list()
            valid_families = ["llama", "gpt", "claude", "mistral", "qwen", "mixtral", "codellama", "nemotron", "gemma", "phi", "deepseek"]
            invalid_families = ["whisper", "dall", "embed", "orpheus", "guard", "vision", "audio"]
            
            if self.name == "openrouter":
                models = [m.id for m in model_list.data if ":free" in m.id.lower()]
            else:
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
            light_models = [m for m in models if any(size in m.lower() for size in ["8b", "7b", "11b", "14b", "27b", "31b", "32b", "33b", "instant", "small", "mini"])]
            
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
        self._ensure_client()
        if self._client is None: raise RuntimeError(f"{self.name} client not configured (no API key or SDK missing)")
        self._resolve_dynamic_model()

        formatted_tools = None
        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append({"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {"type": "object", "properties": {}})}})

        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "max_tokens": self._max_tokens, "temperature": 0.1}
        
        # Provider free-tier limits (Output Tokens)
        limits = {"groq": 800, "cerebras": 4000, "sambanova": 4000, "nvidia_nim": 4000, "cohere": 4000}
        cap = limits.get(self.name, 4096)
        if kwargs.get("max_tokens", cap) > cap:
            kwargs["max_tokens"] = cap
            
        if formatted_tools: kwargs["tools"] = formatted_tools
        if response_schema: kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "schema", "schema": response_schema, "strict": True}}

        import time
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "max_tokens" in err_str:
                kwargs["max_tokens"] = 500  # Clamp hard if it still complains
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                except Exception as e2:
                    err_str = str(e2).lower()
            
            if "resp" not in locals():
                if any(x in err_str for x in ["429", "rate limit", "capacity", "quota", "too many requests", "404", "not found", "402", "insufficient credits", "payment required", "403", "permission denied", "disabled", "400", "unavailable", "timeout", "timed out", "timedout"]):
                    
                    # Reactive backoff
                    if "429" in err_str or "rate limit" in err_str:
                        time.sleep(2)
                        
                    # Rate limited or model locked. Try fallback models if available!
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

        thought_parts: list[str] = []
        tool_name: str | None = None
        tool_args: str = ""
        finish_reason: str = "stop"
        usage_obj: Any = getattr(resp, "usage", None)

        # Discriminator: a full response object has .choices; a stream is iterated.
        stream_mode = not hasattr(resp, "choices")

        if stream_mode:
            # Streaming response: aggregate delta chunks.
            for chunk in resp:
                if usage_obj is None:
                    usage_obj = getattr(chunk, "usage", None)
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None:
                    delta = getattr(choice, "message", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if content:
                    thought_parts.append(content)
                tcs = getattr(delta, "tool_calls", None) if delta is not None else None
                if tcs:
                    for tc in tcs:
                        fn = getattr(tc, "function", None)
                        if fn is None:
                            continue
                        if getattr(fn, "name", None):
                            tool_name = fn.name
                        if getattr(fn, "arguments", None):
                            tool_args += fn.arguments
                fr = getattr(choice, "finish_reason", None)
                if fr:
                    finish_reason = fr
        else:
            # Non-streaming response object.
            choice = resp.choices[0]
            msg = choice.message
            if msg.content:
                thought_parts.append(msg.content)
            if msg.tool_calls:
                fn = msg.tool_calls[0].function
                tool_name = fn.name
                tool_args = fn.arguments or ""
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        usage_dict = {
            "model": self._model,
            "input_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
        }

        action = None
        if tool_name:
            try:
                parsed_args = json.loads(tool_args) if tool_args else {}
            except (json.JSONDecodeError, TypeError):
                parsed_args = {"raw": tool_args}
            action = {"tool": tool_name, "args": parsed_args}

        return Reply(
            thought="".join(thought_parts),
            action=action,
            finish_reason=finish_reason or "stop",
            usage=usage_dict,
        )
