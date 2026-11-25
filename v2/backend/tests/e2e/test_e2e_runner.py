"""End-to-end tests that run the full agent loop with a scripted provider.

Requires HEVA_E2E=1 to run; skipped by default in CI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.llm.router import LLMRouter
from backend.tools.file_io import ReadFileTool, WriteFileTool

pytestmark = pytest.mark.e2e


class _ScriptedE2EProvider:
    def __init__(self, actions: list[dict[str, Any]]):
        self.actions = actions
        self.idx = 0

    @property
    def name(self) -> str:
        return "e2e-scripted"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Any:
        from backend.llm.contracts import Reply

        if self.idx >= len(self.actions):
            return Reply(thought="done", action=None, finish_reason="stop")
        a = self.actions[self.idx]
        self.idx += 1
        return Reply(thought=f"step {self.idx}", action=a, finish_reason="continue")


@pytest.mark.skipif(
    os.getenv("HEVA_E2E", "0") != "1",
    reason="E2E tests require HEVA_E2E=1 (slow, may need real API)",
)
def test_e2e_file_write_inspects_output(tmp_path: Path) -> None:
    provider = _ScriptedE2EProvider(
        [
            {"tool": "write_file", "args": {"path": "hello.py", "content": "print('hello world')"}},
        ]
    )
    runner = AgentRunner(
        router=LLMRouter(providers=[provider]),
        tools=[WriteFileTool(tmp_path), ReadFileTool(tmp_path)],
        max_steps=2,
        self_correction_enabled=True,
    )
    mem = runner.run(Goal(id="e2e1", spec="write hello.py"), ["write file"])
    assert (tmp_path / "hello.py").exists()
    assert mem.final_output is not None

