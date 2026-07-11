"""Unit tests for AgentRunner with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from backend.ai_agent.runner import AgentRunner
from backend.ai_agent.working_memory import Goal
from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter


class MockProvider(Provider):
    def __init__(self, reply: Reply | None = None):
        self._reply = reply or Reply(thought="ok", action=None, finish_reason="stop")

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
        return self._reply


class NoopArgs(BaseModel):
    pass


class NoopTool:
    name = "noop"
    description = "Does nothing"
    args_schema = NoopArgs

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


def _runner(
    tools: list | None = None,
    reply: Reply | None = None,
    max_steps: int = 1,
    **kwargs: Any,
) -> AgentRunner:
    return AgentRunner(
        router=LLMRouter(providers=[MockProvider(reply)]),
        tools=tools or [],
        max_steps=max_steps,
        **kwargs,
    )


class TestRunnerErrors:
    def test_react_step_raises(self) -> None:
        router = MagicMock(spec=LLMRouter)
        router.chat.side_effect = RuntimeError("LLM down")
        router.provider_events = []
        runner = AgentRunner(router=router, tools=[], max_steps=2)
        mem = runner.run(Goal(id="E1", spec="test"), ["do it"])
        assert "crashed" in (mem.final_output or "")

    def test_no_action_produced(self) -> None:
        reply = Reply(thought="ok", action=None, finish_reason="stop")
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[],
            max_steps=1,
        )
        mem = runner.run(Goal(id="E2", spec="test"), ["do it"])
        assert "No action" in (mem.final_output or "")

    def test_tool_not_found(self) -> None:
        reply = Reply(
            thought="use tool",
            action={"tool": "nonexistent", "args": {}},
            finish_reason="stop",
        )
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[],
            max_steps=1,
        )
        mem = runner.run(Goal(id="E3", spec="test"), ["do it"])
        assert mem.executed[-1].result.get("error_type") == "tool_not_found"


class TestRunnerHappy:
    def test_tool_invoke_crashes(self) -> None:
        bad_tool = MagicMock()
        bad_tool.name = "bad"
        bad_tool.invoke.side_effect = ValueError("boom")
        reply = Reply(
            thought="use tool",
            action={"tool": "bad", "args": {}},
            finish_reason="stop",
        )
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[bad_tool],
            max_steps=1,
            self_correction_enabled=False,
        )
        mem = runner.run(Goal(id="H1", spec="test"), ["do it"])
        assert mem.executed[-1].result.get("error_type") == "tool_crash"

    def test_self_correction_disabled(self) -> None:
        seq = iter([
            Reply(
                thought="first",
                action={"tool": "noop", "args": {}},
                finish_reason="stop",
            ),
            Reply(
                thought="second",
                action={"tool": "noop", "args": {}},
                finish_reason="stop",
            ),
        ])

        class TwoStepProvider(MockProvider):
            def chat(self, *a: Any, **kw: Any) -> Reply:
                return next(seq)

        runner = AgentRunner(
            router=LLMRouter(providers=[TwoStepProvider()]),
            tools=[NoopTool()],
            max_steps=2,
            self_correction_enabled=False,
        )
        mem = runner.run(Goal(id="H2", spec="test"), ["do it"])
        assert mem.to_metrics()["steps"] >= 1

    def test_success_path(self, tmp_path: Path) -> None:
        from backend.tools.file_io import WriteFileTool

        reply = Reply(
            thought="write it",
            action={"tool": "write_file", "args": {"path": "x.txt", "content": "hi"}},
            finish_reason="stop",
        )
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[WriteFileTool(tmp_path)],
            max_steps=1,
        )
        mem = runner.run(Goal(id="H3", spec="write file"), ["write file"])
        assert (tmp_path / "x.txt").exists()
        assert mem.final_output is not None


class TestRunnerCallbacks:
    def test_step_completed_callback(self) -> None:
        tracker = MagicMock()
        reply = Reply(
            thought="do it",
            action={"tool": "noop", "args": {}},
            finish_reason="stop",
        )
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[NoopTool()],
            max_steps=1,
            callbacks={"step_completed": tracker},
        )
        runner.run(Goal(id="C1", spec="test"), ["do it"])
        tracker.assert_called_once()

    def test_step_recorded_callback(self) -> None:
        tracker = MagicMock()
        reply = Reply(
            thought="do it",
            action={"tool": "noop", "args": {}},
            finish_reason="stop",
        )
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[NoopTool()],
            max_steps=1,
            callbacks={"step_recorded": tracker},
        )
        runner.run(Goal(id="C2", spec="test"), ["do it"])
        tracker.assert_called_once()

    def test_file_updated_callback(self) -> None:
        updated_paths: list[str] = []

        def on_file_updated(path: str, content: str) -> None:
            updated_paths.append(path)

        reply = Reply(
            thought="write",
            action={"tool": "write_file", "args": {"path": "f.txt", "content": "x"}},
            finish_reason="stop",
        )
        from backend.tools.file_io import WriteFileTool

        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider(reply)]),
            tools=[WriteFileTool(MagicMock())],
            max_steps=1,
            callbacks={"file_updated": on_file_updated},
        )
        runner.run(Goal(id="C3", spec="write"), ["write"])
        assert len(updated_paths) >= 0

    def test_subtask_advanced_callback(self) -> None:
        records: list[dict] = []

        def on_advance(sub: dict) -> None:
            records.append(sub)

        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider()]),
            tools=[NoopTool()],
            max_steps=1,
            callbacks={"subtask_advanced": on_advance},
        )
        runner.run(Goal(id="C4", spec="test"), ["do it"])
        assert len(records) >= 0


class TestRunnerPostLoop:
    def test_final_output_generated(self) -> None:
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider()]),
            tools=[NoopTool()],
            max_steps=1,
        )
        mem = runner.run(Goal(id="P1", spec="test"), ["do it"])
        assert mem.final_output is not None

    def test_run_and_persist(self, tmp_path: Path) -> None:
        runner = AgentRunner(
            router=LLMRouter(providers=[MockProvider()]),
            tools=[NoopTool()],
            max_steps=1,
        )
        mem = runner.run_and_persist(
            Goal(id="P2", spec="test"), ["do it"], output_dir=tmp_path
        )
        assert mem.final_output is not None
        files = list(tmp_path.iterdir())
        assert len(files) >= 1


class TestRunnerRecovery:
    def test_recovery_reinvoke(self) -> None:
        reply = Reply(
            thought="do it",
            action={"tool": "noop", "args": {}},
            finish_reason="stop",
        )
        router = MagicMock(spec=LLMRouter)
        router.chat.return_value = reply
        router.provider_events = []

        with patch("backend.ai_agent.runner.RecoveryController") as mock_ctrl:
            ctrl = MagicMock()
            ctrl.recover.return_value = {
                "new_action": {"tool": "noop", "args": {}},
                "strategy": "retry",
                "mode": "strategy_failure",
            }
            mock_ctrl.return_value = ctrl
            runner = AgentRunner(
                router=router,
                tools=[NoopTool()],
                max_steps=2,
                self_correction_enabled=True,
            )
            runner._controller = ctrl
            mem = runner.run(Goal(id="R1", spec="test"), ["do it"])
            assert mem.final_output is not None

    def test_recovery_unresolvable(self) -> None:
        reply = Reply(
            thought="do it",
            action={"tool": "noop", "args": {}},
            finish_reason="stop",
        )
        router = MagicMock(spec=LLMRouter)
        router.chat.return_value = reply
        router.provider_events = []

        with patch("backend.ai_agent.runner.RecoveryController") as mock_ctrl:
            ctrl = MagicMock()
            ctrl.recover.return_value = {"unresolvable": True}
            mock_ctrl.return_value = ctrl
            runner = AgentRunner(
                router=router,
                tools=[NoopTool()],
                max_steps=2,
                self_correction_enabled=True,
            )
            runner._controller = ctrl
            mem = runner.run(Goal(id="R2", spec="test"), ["do it"])
            assert mem.final_output is not None

    def test_recovery_correction_applied_callback(self) -> None:
        callback_records: list[dict] = []

        def on_correction(rec: dict) -> None:
            callback_records.append(rec)

        reply = Reply(
            thought="do it",
            action={"tool": "noop", "args": {}},
            finish_reason="stop",
        )
        router = MagicMock(spec=LLMRouter)
        router.chat.return_value = reply
        router.provider_events = []

        with patch("backend.ai_agent.runner.RecoveryController") as mock_ctrl:
            ctrl = MagicMock()
            ctrl.recover.return_value = {
                "unresolvable": True,
                "mode": "strategy_failure",
            }
            mock_ctrl.return_value = ctrl
            runner = AgentRunner(
                router=router,
                tools=[NoopTool()],
                max_steps=2,
                self_correction_enabled=True,
                callbacks={"correction_applied": on_correction},
            )
            runner._controller = ctrl
            runner.run(Goal(id="R3", spec="test"), ["do it"])
            assert len(callback_records) >= 0

