from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Reply:
    thought: str
    action: dict[str, Any] | None
    finish_reason: str
    usage: dict[str, int] = field(default_factory=dict)


class Provider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply: ...


def make_tool_specs(tools: list[Any]) -> list[dict[str, Any]]:
    spec = []
    for t in tools:
        spec.append(
            {
                "name": t.name,
                "description": getattr(t, "description", ""),
                "input_schema": t.args_schema.model_json_schema(),
            }
        )
    return spec

