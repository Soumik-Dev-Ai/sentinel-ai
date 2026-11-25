import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from backend.llm.contracts import Provider, Reply

os.environ["ANSI_COLORS_DISABLE"] = "1"


class MockProvider(Provider):
    def __init__(self, replies: list[dict[str, Any]]):
        self._replies = replies
        self._idx = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        self.calls.append({"messages": messages, "tools": tools, "schema": response_schema})
        if self._idx >= len(self._replies):
            raise IndexError(f"No more mock replies at index {self._idx}")
        raw = self._replies[self._idx]
        self._idx += 1
        return Reply(
            thought=raw["thought"],
            action=raw.get("action"),
            finish_reason=raw.get("finish_reason", "stop"),
            usage=raw.get("usage", {}),
        )

    def set_replies(self, replies: list[dict[str, Any]]) -> None:
        self._replies = replies
        self._idx = 0


@pytest.fixture
def tmp_workspace() -> Path:
    with tempfile.TemporaryDirectory(prefix="sca_") as td:
        yield Path(td)


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider([])

