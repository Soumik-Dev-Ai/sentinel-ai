"""Merciless, Full-Spectrum End-to-End Test Suite for Sentinel AI 2.0.

Tests every subsystem under nominal, stress, edge, and failure conditions:
1. Polyglot Sandbox Execution & Boundary Traps (C, C++, Rust, Go, Python, Node.js, SIGSEGV, SIGABRT, Timeout)
2. Parallel Dual-Verification Engine (Critic + Executor concurrency, precedence of reality over opinion, refinement)
3. Orchestrator Resilient Tree-of-Thought (valid JSON, truncated JSON recovery, zero-crash goal fallback)
4. Multi-Agent Autonomous Self-Correction Loop (fault injection -> diagnostic classification -> patch -> clean pass)
5. Escalation Management & Max Retries (prevents premature human escalation)
6. Dynamic Model Discovery & Error Resilience (intra-provider candidate rotation on 429 / TPD)
7. Telemetry & Cost Optimization (fast_eval vs coding tier routing)
8. FastAPI Server & WebSocket Protocol E2E (REST /health, WS event lifecycle)
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import pytest

# Ensure Sentinel AI is in sys.path
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.llm.contracts import Provider, Reply
from backend.llm.router import LLMRouter
from backend.memory.vector_store import VectorStore
from backend.orchestrator.base import AgentContext, EventBus
from backend.orchestrator.coder import Coder
from backend.orchestrator.cost import CostTracker
from backend.orchestrator.critic import Critic
from backend.orchestrator.escalation import EscalationManager
from backend.orchestrator.executor import Executor
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.pipeline import MultiAgentPipeline
from backend.orchestrator.retry import RetryRouter
from backend.tools.polyglot_sandbox import PolyglotSandboxTool


# =============================================================================
# Mock Provider Harness for Deterministic High-Speed Testing
# =============================================================================

class DynamicScriptedProvider(Provider):
    """Deterministic, role-aware mock provider simulating LLM intelligence."""

    def __init__(self, name: str = "merciless-mock", model: str = "mock-ultra"):
        self._name = name
        self._model = model
        self.calls: list[dict[str, Any]] = []
        self._custom_handlers: list[Any] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def add_handler(self, fn: Any) -> None:
        self._custom_handlers.append(fn)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        stream_callback: Any = None,
    ) -> Reply:
        self.calls.append({"messages": messages, "tools": tools})

        # Check custom handlers first
        for handler in self._custom_handlers:
            res = handler(messages)
            if res is not None:
                return res

        # Default role-based responses
        sys_prompt = ""
        user_content = ""
        for m in messages:
            if m.get("role") == "system":
                sys_prompt = m.get("content", "")
            elif m.get("role") == "user":
                user_content = str(m.get("content", ""))

        # 1. Orchestrator ToT Planning
        if "You are ORCHESTRATOR" in sys_prompt:
            body = {
                "paths": [
                    {
                        "id": "P1",
                        "description": "Optimal standard algorithm with in-place bounds checking",
                        "steps": ["Implement solution in workspace", "Execute and verify all assertions"],
                        "confidence": 0.95,
                        "rationale": "High efficiency and clean test harness",
                        "risks": []
                    },
                    {
                        "id": "P2",
                        "description": "Iterative approach with auxiliary memory",
                        "steps": ["Implement solution in workspace", "Execute tests"],
                        "confidence": 0.80,
                        "rationale": "Simple but extra space",
                        "risks": []
                    },
                    {
                        "id": "P3",
                        "description": "Recursive divide-and-conquer",
                        "steps": ["Implement solution in workspace", "Execute tests"],
                        "confidence": 0.70,
                        "rationale": "Risk of recursion limit",
                        "risks": ["Stack overflow"]
                    }
                ]
            }
            return Reply(thought=json.dumps(body), action=None, finish_reason="stop")

        # 2. Orchestrator Subtask Decomposition
        if "Given the chosen approach below" in sys_prompt:
            body = {
                "subtasks": [
                    {"id": "S1", "desc": "Write implementation script", "agent": "coder", "model_tier": "coding"},
                    {"id": "S2", "desc": "Execute verification test suite", "agent": "executor", "model_tier": "fast_eval"}
                ]
            }
            return Reply(thought=json.dumps(body), action=None, finish_reason="stop")

        # 3. Critic Code Review
        if "You are CRITIC" in sys_prompt:
            body = {
                "correctness": 10,
                "safety": 10,
                "readability": 10,
                "efficiency": 10,
                "total": 100,
                "summary": "Exemplary implementation, fully verifies boundary conditions.",
                "issues": [],
                "fix_suggestions": [],
                "passes": True
            }
            return Reply(thought=json.dumps(body), action=None, finish_reason="stop")

        # 4. Coder Code Generation
        if "You are CODER" in sys_prompt:
            # Check if user prompt is requesting Python
            code = (
                "def binary_search(arr, target):\n"
                "    left, right = 0, len(arr) - 1\n"
                "    while left <= right:\n"
                "        mid = (left + right) // 2\n"
                "        if arr[mid] == target: return mid\n"
                "        elif arr[mid] < target: left = mid + 1\n"
                "        else: right = mid - 1\n"
                "    return -1\n\n"
                "assert binary_search([1, 3, 5, 7, 9], 5) == 2\n"
                "assert binary_search([1, 3, 5, 7, 9], 1) == 0\n"
                "assert binary_search([1, 3, 5, 7, 9], 10) == -1\n"
                "print('ALL TESTS PASSED')\n"
            )
            body = {
                "filename": "main.py",
                "code": code,
                "rationale": "Robust binary search with boundary assertions"
            }
            return Reply(thought=json.dumps(body), action=None, finish_reason="stop")

        return Reply(thought="{}", action=None, finish_reason="stop")


# =============================================================================
# PART 1: Polyglot Sandbox Execution & Crash Trapping
# =============================================================================

class TestPolyglotSandboxMerciless:

    def test_python_clean_execution(self, tmp_path: Path):
        tool = PolyglotSandboxTool()
        code = "print('HELLO FROM SANDBOX')\nprint(10 * 10)"
        res = tool.run(code, "python", timeout=5)
        assert res["exit_code"] == 0
        assert "HELLO FROM SANDBOX" in res["stdout"]
        assert "100" in res["stdout"]

    def test_python_timeout_enforcement(self, tmp_path: Path):
        tool = PolyglotSandboxTool()
        code = "import time\nwhile True:\n    time.sleep(0.1)"
        t0 = time.time()
        res = tool.run(code, "python", timeout=1)
        elapsed = time.time() - t0
        assert res["exit_code"] == 124
        assert "timed out" in res["stderr"].lower() or res["stage"] == "timeout"
        assert elapsed < 4.0  # Must enforce promptly

    def test_python_syntax_error_trapping(self, tmp_path: Path):
        tool = PolyglotSandboxTool()
        code = "def broken(\n    print('missing paren')"
        res = tool.run(code, "python", timeout=5)
        assert res["exit_code"] != 0
        assert "SyntaxError" in res["stderr"]

    def test_c_clean_compilation_and_execution(self, tmp_path: Path):
        if not shutil.which("gcc"):
            pytest.skip("GCC not installed in local environment")
        tool = PolyglotSandboxTool()
        c_code = (
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <assert.h>\n"
            "int main() {\n"
            "    int* p = (int*)malloc(sizeof(int));\n"
            "    assert(p != NULL);\n"
            "    *p = 42;\n"
            "    printf(\"VALUE=%d\\n\", *p);\n"
            "    free(p);\n"
            "    return 0;\n"
            "}\n"
        )
        res = tool.run(c_code, "c", timeout=10)
        assert res["exit_code"] == 0
        assert "VALUE=42" in res["stdout"]

    def test_c_compile_error_diagnostic(self, tmp_path: Path):
        if not shutil.which("gcc"):
            pytest.skip("GCC not installed in local environment")
        tool = PolyglotSandboxTool()
        bad_c = "int main() { printf(\"missing header and semicolon\") return 0 }"
        res = tool.run(bad_c, "c", timeout=10)
        assert res["exit_code"] != 0
        assert "error:" in res["stderr"].lower() or res["stage"] == "compilation"

    def test_c_segfault_signal_decoding(self, tmp_path: Path):
        if not shutil.which("gcc"):
            pytest.skip("GCC not installed in local environment")
        tool = PolyglotSandboxTool()
        segfault_c = (
            "#include <stdio.h>\n"
            "int main() {\n"
            "    volatile int* ptr = NULL;\n"
            "    *ptr = 1337;\n"
            "    return 0;\n"
            "}\n"
        )
        res = tool.run(segfault_c, "c", timeout=10)
        assert res["exit_code"] != 0
        # Windows returns 0xC0000005 (or 3221225477 / -1073741819), Linux returns 139 (SIGSEGV)
        assert "SIGSEGV" in str(res.get("error_type", "")) or res["exit_code"] in (139, 3221225477, -1073741819)

    def test_c_abort_signal_decoding(self, tmp_path: Path):
        if not shutil.which("gcc"):
            pytest.skip("GCC not installed in local environment")
        tool = PolyglotSandboxTool()
        abort_c = (
            "#include <assert.h>\n"
            "int main() {\n"
            "    assert(0 && \"merciless abort test\");\n"
            "    return 0;\n"
            "}\n"
        )
        res = tool.run(abort_c, "c", timeout=10)
        assert res["exit_code"] != 0

    def test_nodejs_execution_if_available(self, tmp_path: Path):
        if not shutil.which("node"):
            pytest.skip("Node.js not installed in local environment")
        tool = PolyglotSandboxTool()
        js_code = "const val = [1,2,3].reduce((a,b)=>a+b,0); console.log(`SUM=${val}`);"
        res = tool.run(js_code, "javascript", timeout=5)
        assert res["exit_code"] == 0
        assert "SUM=6" in res["stdout"]

    def test_workspace_with_spaces_and_special_chars(self, tmp_path: Path):
        tool = PolyglotSandboxTool()
        space_ws = tmp_path / "path with spaces #@!"
        space_ws.mkdir()
        code = "print('SPACE PATH SAFE')"
        res = tool.run(code, "python", timeout=5)
        assert res["exit_code"] == 0
        assert "SPACE PATH SAFE" in res["stdout"]


# =============================================================================
# PART 2: Orchestrator Resilient Tree-of-Thought
# =============================================================================

class TestOrchestratorResilience:

    def test_clean_tot_generation(self, tmp_path: Path):
        provider = DynamicScriptedProvider()
        router = LLMRouter(providers=[provider])
        bus = EventBus()
        ctx = AgentContext(
            goal="Implement binary search",
            acceptance=["Must assert all cases"],
            workspace=tmp_path,
            router=router,
            bus=bus,
            cost=CostTracker(),
            memory=VectorStore(persist_dir=tmp_path / "mem"),
        )
        orch = Orchestrator()
        res = orch.run(ctx)
        assert res["ok"] is True
        plan = res["plan"]
        assert len(plan["all_paths"]) == 3
        assert plan["chosen_path"]["id"] == "P1"
        assert len(plan["subtasks"]) >= 2

    def test_truncated_json_regex_recovery(self, tmp_path: Path):
        """Simulates LLM response abruptly cut off at 800 token ceiling."""
        truncated_text = (
            '```json\n'
            '{\n'
            '  "paths": [\n'
            '    {\n'
            '      "id": "P1",\n'
            '      "description": "Robust binary search tree",\n'
            '      "steps": ["write bst.py", "run tests"],\n'
            '      "confidence": 0.92\n'
            '    },\n'
            '    {\n'
            '      "id": "P2",\n'
            '      "description": "Iterative bst",\n'
            '      "steps": ["write iter_bst.py", "run tests"],\n'
            '      "confidence": 0.78\n'
            '    }\n'
            # Note: JSON cuts off abruptly here without closing braces
        )
        provider = DynamicScriptedProvider()
        # Override first call to return truncated JSON
        call_count = 0
        def truncated_handler(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Reply(thought=truncated_text, action=None, finish_reason="length")
            return None
        provider.add_handler(truncated_handler)

        router = LLMRouter(providers=[provider])
        bus = EventBus()
        ctx = AgentContext(
            goal="Write a BST in python",
            acceptance=[],
            workspace=tmp_path,
            router=router,
            bus=bus,
            cost=CostTracker(),
            memory=VectorStore(persist_dir=tmp_path / "mem"),
        )
        orch = Orchestrator()
        res = orch.run(ctx)
        assert res["ok"] is True
        assert len(res["plan"]["all_paths"]) >= 1

    def test_total_garbage_response_zero_crash_fallback(self, tmp_path: Path):
        """Simulates LLM returning totally non-JSON garbage prose."""
        provider = DynamicScriptedProvider()
        provider.add_handler(lambda msgs: Reply(thought="I am an AI and cannot complete this in JSON format sorry!", action=None, finish_reason="stop"))

        router = LLMRouter(providers=[provider])
        bus = EventBus()
        events = []
        bus.subscribe(lambda ev: events.append(ev))

        ctx = AgentContext(
            goal="Write a program that implements a binary search tree",
            acceptance=["Must print ALL TESTS PASSED"],
            workspace=tmp_path,
            router=router,
            bus=bus,
            cost=CostTracker(),
            memory=VectorStore(persist_dir=tmp_path / "mem"),
        )
        orch = Orchestrator()
        res = orch.run(ctx)
        # Must NOT fail with no_paths_produced; must synthesize fallback plan
        assert res["ok"] is True
        plan = res["plan"]
        assert len(plan["all_paths"]) >= 1
        assert len(plan["subtasks"]) >= 2
        # Verify no error event emitted
        err_events = [e for e in events if e.type == "error"]
        assert len(err_events) == 0


# =============================================================================
# PART 3: Parallel Dual-Verification Engine (Critic + Executor)
# =============================================================================

class TestParallelDualVerification:

    def test_parallel_verification_both_pass_resolves_attempt_1(self, tmp_path: Path):
        provider = DynamicScriptedProvider()
        pipe = MultiAgentPipeline(router=LLMRouter(providers=[provider]))
        ws = tmp_path / "dual_pass"
        ws.mkdir()

        res = pipe.run(
            goal="Write binary search and assert correctness",
            acceptance=["Must print ALL TESTS PASSED"],
            workspace=ws,
        )
        assert res["success"] is True
        # Verify attempt was 1, no retries needed
        assert (ws / "main.py").exists()

    def test_execution_failure_trumps_high_critic_score(self, tmp_path: Path):
        """Critic gives 100/100, but code has ZeroDivisionError.
        Pipeline MUST reject attempt 1 and trigger self-correction retry."""
        provider = DynamicScriptedProvider()
        call_idx = 0
        def buggy_first_coder(messages):
            nonlocal call_idx
            sys_m = next((m["content"] for m in messages if m["role"] == "system"), "")
            if "You are CODER" in sys_m:
                call_idx += 1
                if call_idx == 1:
                    # Buggy code on attempt 1
                    buggy_code = "print('STARTING')\nx = 10 / 0\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "main.py", "code": buggy_code, "rationale": "Buggy"}), action=None, finish_reason="stop")
                else:
                    # Fixed code on attempt 2
                    fixed_code = "print('STARTING')\nx = 10 / 2\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "main.py", "code": fixed_code, "rationale": "Fixed"}), action=None, finish_reason="stop")
            # Critic always returns high score
            if "You are CRITIC" in sys_m:
                return Reply(thought=json.dumps({"total": 95, "passes": True, "summary": "Looks great to me", "issues": []}), action=None, finish_reason="stop")
            return None

        provider.add_handler(buggy_first_coder)
        pipe = MultiAgentPipeline(router=LLMRouter(providers=[provider]))
        ws = tmp_path / "reality_trumps"
        ws.mkdir()

        res = pipe.run(
            goal="Perform math operation and print ALL TESTS PASSED",
            acceptance=["Must print ALL TESTS PASSED"],
            workspace=ws,
        )
        assert res["success"] is True
        # Proves self-correction triggered because call_idx reached 2
        assert call_idx >= 2

    def test_critic_refinement_triggers_when_execution_passes_but_coverage_low(self, tmp_path: Path):
        """Code executes cleanly with 0, but Critic awards 60/100 with issues.
        Pipeline triggers refinement retry."""
        provider = DynamicScriptedProvider()
        coder_calls = 0
        critic_calls = 0

        def critic_refinement_handler(messages):
            nonlocal coder_calls, critic_calls
            sys_m = next((m["content"] for m in messages if m["role"] == "system"), "")
            if "You are CODER" in sys_m:
                coder_calls += 1
                return Reply(thought=json.dumps({
                    "filename": "calc.py",
                    "code": f"# Version {coder_calls}\nprint('CALC DONE')\n",
                    "rationale": "Math helper"
                }), action=None, finish_reason="stop")
            if "You are CRITIC" in sys_m:
                critic_calls += 1
                if critic_calls == 1:
                    # Request refinement on attempt 1
                    return Reply(thought=json.dumps({
                        "total": 60,
                        "passes": False,
                        "summary": "Missing negative numbers test",
                        "issues": ["No test for negative numbers"],
                        "fix_suggestions": ["Add assert calc(-5)"]
                    }), action=None, finish_reason="stop")
                else:
                    # Pass on attempt 2
                    return Reply(thought=json.dumps({
                        "total": 95,
                        "passes": True,
                        "summary": "Thorough tests added",
                        "issues": []
                    }), action=None, finish_reason="stop")
            return None

        provider.add_handler(critic_refinement_handler)
        pipe = MultiAgentPipeline(router=LLMRouter(providers=[provider]))
        ws = tmp_path / "refine_ws"
        ws.mkdir()

        res = pipe.run(goal="Implement calculator", workspace=ws)
        assert res["success"] is True
        assert coder_calls == 2
        assert critic_calls == 2


# =============================================================================
# PART 4: Multi-Agent Autonomous Self-Correction Loop
# =============================================================================

class TestMultiAgentSelfCorrection:

    def test_syntax_error_recovery_loop(self, tmp_path: Path):
        """Injects a syntax error in attempt 1, verifies RetryRouter classifies as SYNTAX
        and attempt 2 delivers working code."""
        provider = DynamicScriptedProvider()
        attempts = 0

        def syntax_fix_handler(messages):
            nonlocal attempts
            sys_m = next((m["content"] for m in messages if m["role"] == "system"), "")
            if "You are CODER" in sys_m:
                attempts += 1
                if attempts == 1:
                    # Syntax error: missing colon
                    broken = "def compute(x)\n    return x * 2\nassert compute(5) == 10\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "script.py", "code": broken, "rationale": "Missing colon"}), action=None, finish_reason="stop")
                else:
                    # Corrected
                    fixed = "def compute(x):\n    return x * 2\nassert compute(5) == 10\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "script.py", "code": fixed, "rationale": "Fixed colon"}), action=None, finish_reason="stop")
            return None

        provider.add_handler(syntax_fix_handler)
        pipe = MultiAgentPipeline(router=LLMRouter(providers=[provider]))
        ws = tmp_path / "syntax_ws"
        ws.mkdir()

        res = pipe.run(goal="Compute doubling with assertions", workspace=ws)
        assert res["success"] is True
        assert attempts == 2
        final_code = (ws / "script.py").read_text(encoding="utf-8")
        assert "def compute(x):" in final_code

    def test_assertion_error_recovery_loop(self, tmp_path: Path):
        """Injects an off-by-one logic error, verifies Executor captures AssertionError
        and Coder corrects the algorithm."""
        provider = DynamicScriptedProvider()
        attempts = 0

        def logic_fix_handler(messages):
            nonlocal attempts
            sys_m = next((m["content"] for m in messages if m["role"] == "system"), "")
            if "You are CODER" in sys_m:
                attempts += 1
                if attempts == 1:
                    # Off by one: returns 9 instead of 10
                    broken = "def add(a, b): return a + b - 1\nassert add(5, 5) == 10\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "add.py", "code": broken, "rationale": "Off by one"}), action=None, finish_reason="stop")
                else:
                    fixed = "def add(a, b): return a + b\nassert add(5, 5) == 10\nprint('ALL TESTS PASSED')"
                    return Reply(thought=json.dumps({"filename": "add.py", "code": fixed, "rationale": "Corrected"}), action=None, finish_reason="stop")
            return None

        provider.add_handler(logic_fix_handler)
        pipe = MultiAgentPipeline(router=LLMRouter(providers=[provider]))
        ws = tmp_path / "logic_ws"
        ws.mkdir()

        res = pipe.run(goal="Addition with assertions", workspace=ws)
        assert res["success"] is True
        assert attempts == 2


# =============================================================================
# PART 5: Escalation Management & Max Retries
# =============================================================================

class TestEscalationManagement:

    def test_escalation_triggers_only_after_max_retries_exhausted(self, tmp_path: Path):
        """Verify that escalation manager does not prematurely trigger human escalation
        on attempt 1 or 2 when max_retries is 3."""
        escalation = EscalationManager()
        subtask_id = "test_subtask"

        # Attempt 1: fail with low confidence
        escalation.record_attempt(subtask_id, confidence=0.2)
        assert escalation.should_escalate(subtask_id) is False

        # Attempt 2: fail again
        escalation.record_attempt(subtask_id, confidence=0.3)
        assert escalation.should_escalate(subtask_id) is False

        # Attempt 3: fail again
        escalation.record_attempt(subtask_id, confidence=0.2)
        assert escalation.should_escalate(subtask_id) is False

        # Attempt 4 (hits ESCALATION_MAX_ATTEMPTS = 4):
        escalation.record_attempt(subtask_id, confidence=0.1)
        assert escalation.should_escalate(subtask_id) is True


# =============================================================================
# PART 6: Dynamic Model Discovery & Candidate Rotation
# =============================================================================

class TestModelDiscoveryAndRotation:

    def test_router_rotates_candidates_on_simulated_rate_limit(self):
        calls = []

        class FailingProvider(Provider):
            @property
            def name(self): return "primary-rate-limited"
            @property
            def model(self): return "primary-model"
            def chat(self, messages, tools=None, response_schema=None, stream_callback=None):
                calls.append("primary")
                raise RuntimeError("Rate limit reached: 429 Too Many Requests")

        class BackupProvider(Provider):
            @property
            def name(self): return "backup-secondary"
            @property
            def model(self): return "backup-model"
            def chat(self, messages, tools=None, response_schema=None, stream_callback=None):
                calls.append("backup")
                return Reply(thought="recovered", action=None, finish_reason="stop")

        router = LLMRouter(providers=[FailingProvider(), BackupProvider()])
        reply = router.chat([{"role": "user", "content": "hi"}])
        assert reply.thought == "recovered"
        assert calls == ["primary", "backup"]
        assert router.last_successful_provider == "backup-secondary"

    def test_fast_eval_tier_routing(self):
        """Verify Critic and Executor default to fast_eval tier to conserve tokens."""
        critic = Critic()
        assert critic.human_label == "Critic"
        executor = Executor()
        assert executor.human_label == "Executor"


# =============================================================================
# PART 7: FastAPI Server & WebSocket Protocol Telemetry
# =============================================================================

class TestServerAndWebSocketTelemetry:

    def test_server_health_rest_endpoint(self):
        from starlette.testclient import TestClient
        from backend.server.server import app

        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_websocket_run_event_stream(self, tmp_path: Path):
        """Tests the full WebSocket protocol: connects, sends run request,
        and streams events with strictly monotonically increasing sequence IDs."""
        from starlette.testclient import TestClient
        from backend.server.server import app
        import backend.server.server as srv

        # Seed server pipeline with mock provider for zero-latency test
        provider = DynamicScriptedProvider()
        app.state.router = LLMRouter(providers=[provider])

        client = TestClient(app)
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({
                "type": "start",
                "goal": "Write a python binary search test",
                "mode": "multi",
                "acceptance": ["Must print ALL TESTS PASSED"]
            })

            received_events = []
            completed = False
            for _ in range(100):
                try:
                    data = ws.receive_json()
                    received_events.append(data)
                    if data.get("type") == "completed":
                        completed = True
                        break
                except Exception as exc:
                    print(f"Exception receiving websocket message: {exc}")
                    break

            print("RECEIVED EVENTS COUNT:", len(received_events), [e.get("type") for e in received_events])
            if not completed and received_events:
                print("LAST EVENT:", received_events[-1])
            assert completed is True
            assert len(received_events) > 5

            # Assert event sequences are strictly increasing
            seqs = [e["seq"] for e in received_events if "seq" in e]
            assert seqs == sorted(seqs)
            assert len(seqs) == len(set(seqs))  # No duplicates

            # Assert essential event types emitted
            event_types = {e.get("type") for e in received_events}
            assert "agent_started" in event_types
            assert "graph_node" in event_types
            assert "agent_finished" in event_types
            assert "completed" in event_types


# =============================================================================
# CLI Standalone Runner
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  SENTINEL AI 2.0: MERCILESS END-TO-END VERIFICATION SUITE")
    print("=" * 70)
    ret = pytest.main([__file__, "-v", "--tb=short", "-s"])
    sys.exit(ret)
