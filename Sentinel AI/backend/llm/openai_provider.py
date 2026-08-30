from __future__ import annotations

import json
from typing import Any

from backend.llm.contracts import Provider, Reply


class OpenAIProvider(Provider):
    def __init__(self, api_key: str = "", model: str = "gpt-4o", max_tokens: int = 4096):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._api_key)
            except ImportError:
                pass

    @property
    def name(self) -> str:
        return "openai"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        if self._client is None:
            raise RuntimeError("OpenAI client not configured (no API key or SDK missing)")

        formatted_tools = None
        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get(
                                "input_schema", {"type": "object", "properties": {}}
                            ),
                        },
                    }
                )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if formatted_tools:
            kwargs["tools"] = formatted_tools
        if response_schema:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            # Only retry without response_format when the failure originates from
            # the OpenAI-compatible API (e.g. a model that rejects structured
            # output). Other errors (network, auth, timeouts, bugs) must surface.
            if not (getattr(e, "__module__", "") or "").startswith("openai"):
                raise
            kwargs.pop("response_format", None)
            resp = self._client.chat.completions.create(**kwargs)

        thought = ""
        action_args_str = ""
        tool_name = ""
        finish_reason = "stop"

        for chunk in resp:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            
            delta = choice.delta
            if delta.content:
                token = delta.content
                thought += token
                if stream_callback:
                    stream_callback("thought", token)
            
            if delta.tool_calls:
                tc = delta.tool_calls[0]
                if tc.function:
                    if tc.function.name:
                        tool_name = tc.function.name
                    if tc.function.arguments:
                        token = tc.function.arguments
                        action_args_str += token
                        if stream_callback:
                            stream_callback("action", token)

        action = None
        if tool_name or action_args_str:
            try:
                parsed_args = json.loads(action_args_str) if action_args_str else {}
            except (json.JSONDecodeError, TypeError):
                parsed_args = {"raw": action_args_str}
            action = {"tool": tool_name, "args": parsed_args}

        return Reply(
            thought=thought,
            action=action,
            finish_reason=finish_reason,
            usage={},  # Streaming usually drops usage info unless stream_options={"include_usage": True} is set
        )
