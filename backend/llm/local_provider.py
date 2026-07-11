from __future__ import annotations

import json
from typing import Any

import httpx

from backend import config
from backend.llm.contracts import Provider, Reply


class LocalOllamaProvider(Provider):
    def __init__(self, base_url: str | None = None, model: str = "llama3.1"):
        self._base_url = base_url or config.OLLAMA_BASE_URL
        self._model = model

    @property
    def name(self) -> str:
        return "local"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        sys_content = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                sys_content = m["content"]
            else:
                conv_messages.append(m)

        if sys_content:
            conv_messages = [{"role": "system", "content": sys_content}] + conv_messages

        prompt_parts = []
        for m in conv_messages:
            prompt_parts.append(m["content"])
        prompt = "\n\n".join(prompt_parts)

        schema_hint = ""
        if response_schema:
            schema_hint = (
                f"\n\nYou MUST respond with valid JSON matching this schema:\n"
                f'{{"thought": "your reasoning...",'
                f' "action": {{"tool": "<tool_name>", "args": {{...}}}}}}\n'
            )
        if tools:
            tool_desc = "\n".join(f"- {t['name']}: {t.get('description', '')}" for t in tools)
            prompt += (
                f"\n\nAvailable tools:\n{tool_desc}\n"
                f"{schema_hint}"
                "Respond with valid JSON containing 'thought' and 'action'"
                " (with 'tool' and 'args' keys)."
            )

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("response", "")
        thought = text
        action = None
        try:
            parsed = json.loads(text)
            thought = parsed.get("thought", text)
            action = parsed.get("action")
        except (json.JSONDecodeError, TypeError):
            pass

        return Reply(thought=thought, action=action, finish_reason="stop")


