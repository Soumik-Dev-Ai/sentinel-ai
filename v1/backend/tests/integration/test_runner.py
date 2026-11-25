"""Integration tests for the agent runner using a scripted provider."""

from __future__ import annotations

from typing import Any

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter
from backend.tools.file_io import ReadFileTool, WriteFileTool


class ScriptedProvider(Provider):
    def __init__(self, replies: list[Reply]):
        self.replies = replies
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


def test_runner_happy_path(tmp_path) -> None:
    provider = ScriptedProvider(
        [
            Reply(
                thought="I will write a file.",
                action={"tool": "write_file", "args": {"path": "x.py", "content": "print(1)"}},
                finish_reason="stop",
            )
        ]
    )
    runner = AgentRunner(
        router=LLMRouter(providers=[provider]),
        tools=[WriteFileTool(tmp_path), ReadFileTool(tmp_path)],
        self_correction_enabled=True,
        max_steps=2,
    )
    mem = runner.run(Goal(id="I1", spec="write file"), ["write file"])
    assert (tmp_path / "x.py").exists()
    assert mem.to_metrics()["steps"] == 1

