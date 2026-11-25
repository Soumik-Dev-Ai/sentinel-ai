# Sentinel AI 2.0 — Testing & Verification Plan

## 1. Testing Philosophy & Strategy

Sentinel AI 2.0 adopts a 3-tier testing strategy designed to verify algorithmic determinism, multi-agent coordination, and real-world self-correction lift:

```text
+-----------------------------------------------------------------------------------------+
| Tier 1: Offline Unit Tests (155 Tests)                                                  |
| - 100% offline and deterministic execution (< 15 seconds runtime)                       |
| - Verifies individual components: agent parsing, retry taxonomy, memory, cost tracker  |
+-----------------------------------------------------------------------------------------+
| Tier 2: Pipeline Integration Tests                                                      |
| - Full MultiAgentPipeline execution driven by deterministic _ScriptedProvider mock      |
| - Tests ToT planning, Critic rejections, retry acquisitions, and Escalation triggers     |
+-----------------------------------------------------------------------------------------+
| Tier 3: Evaluation Lab A/B Benchmark Suite (12 Canonical Goals, 24 Full Executions)     |
| - Live comparative evaluation of Self-Correction ON vs Baseline (OFF)                   |
| - Measures completion rate lift, step efficiency, autonomous recovery, and latency       |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Unit Test Suite Inventory (`backend/tests/unit/`)

The unit test suite consists of **155 automated tests** across 26 test files, requiring zero external API keys:

| Test File | Target Module | Test Count | Key Test Assertions |
| :--- | :--- | :---: | :--- |
| `test_multiagent_pipeline.py` | `MultiAgentPipeline` | 6 | Happy path ToT $\rightarrow$ Coder $\rightarrow$ Critic $\rightarrow$ Executor; Critic rejection $\rightarrow$ retry acquisition; Executor syntax error classification. |
| `test_router.py` | `LLMRouter` | 8 | Multi-tier model sorting, failover chain traversal, usage count load balancing, fail-count penalization. |
| `test_openai_provider.py` | `OpenAIProvider` | 7 | Dynamic `/v1/models` catalog parsing, heavy/light model classification, reactive 429 backoff, TPD rotation. |
| `test_router_default_chain.py` | `LLM_CHAIN` | 4 | Fallback chain priority, backup provider sorting, default configuration loading. |
| `test_code_exec.py` | `RunPythonTool` | 5 | Subprocess sandbox isolation, execution timeouts (30s), exit code capture, stdout/stderr extraction. |
| `test_strategies.py` | `RetryRouter` | 8 | Classification into `LINE_PATCH` (syntax), `FULL_REWRITE` (logic), and `BACKOFF` (external); distinct object mutation assertion. |
| `test_taxonomy.py` | `FailureCategory` | 9 | Heuristic exception parser testing syntax errors, logic errors, timeouts, and clean exits. |
| `test_controller.py` | `EscalationManager` | 6 | Attempt counters, confidence moving average, escalation triggers when confidence $< 0.50$, budget reset on human hint. |
| `test_working_memory.py` | `WorkingMemory` | 10 | State persistence, subtask queue transitions, memory snapshots. |
| `test_working_memory_extras.py` | `VectorStore` | 8 | TF-IDF token weighting, cosine similarity calculation, persistence to disk and reloading. |
| `test_server.py` | FastAPI Server | 7 | HTTP routes, `/api/health` status check, CORS middleware verification. |
| `test_server_ws.py` | WebSocket Core | 8 | Connection negotiation, `AgentEvent` serialization, client message dispatch, escalation response handling. |
| `test_flaky_net.py` | `FlakyNetTool` | 4 | Simulated network failure, exponential retry recovery, malformed payload detection. |
| `test_file_io_extras.py` | `WriteFileTool` | 6 | Workspace directory traversal security, safe path resolution, overwrite behavior. |
| `test_spec_check.py` | `SpecCheckTool` | 4 | Specification validation against generated workspace files. |
| `test_test_run.py` | `RunTestsTool` | 5 | Pytest runner execution in sandbox, assert statement verification, test report extraction. |
| `test_logger.py` | Logging Subsystem | 6 | JSON structured event serialization, timestamp and sequence ordering. |
| `test_tools_base.py` | `ToolProtocol` | 6 | Pydantic v2 input argument validation, return schema enforcement, shape violation handling. |
| `test_viewer.py` | Log Viewer | 5 | Formatting of execution traces, table rendering, step summaries. |
| `test_viewer_cli.py` | CLI Viewer | 5 | Rich-based terminal visual output formatting. |
| `test_viewer_html.py` | HTML Viewer | 4 | Jinja2 standalone HTML report rendering. |
| `test_react_errors.py` | Legacy ReAct Engine | 6 | ReAct error handling and fallback stability. |
| `test_runner.py` | Legacy Runner | 6 | ReAct runner execution lifecycle. |
| `test_self_evaluator.py` | Legacy Evaluator | 6 | Single-agent evaluation logic. |
| `test_contracts.py` | Core Contracts | 3 | Pydantic model protocol verification. |
| `test_base_extras.py` | Agent Base | 4 | Context isolation, thread safety, and event bus pub/sub. |
| **Total** | **26 Test Modules** | **155** | **100% Passed** |

---

## 3. Mock Provider Architecture (`_ScriptedProvider`)

In integration testing, the LLM layer is replaced with [`_ScriptedProvider`](file:///c:/Users/user/projects/self%20correcting%20multi%20agent/Sentinel%20AI/backend/tests/unit/test_multiagent_pipeline.py#L37-L79), which provides deterministic canned responses:

```python
class _ScriptedProvider(Provider):
    """Mock provider that returns scripted responses in order."""
    def __init__(self, replies: list[dict[str, Any]]):
        self._replies = replies
        self._idx = 0
        self.calls: list[dict[str, Any]] = []
        self._model = "mock-model"

    def chat(self, messages, tools=None, response_schema=None, stream_callback=None) -> Reply:
        self.calls.append({"messages": messages, "tools": tools, "schema": response_schema})
        raw = self._replies[self._idx]
        self._idx += 1
        return Reply(
            thought=raw["thought"],
            action=raw.get("action"),
            finish_reason="stop",
            usage={"input_tokens": 10, "output_tokens": 20, "model": "mock", "provider": "mock"}
        )
```

This ensures that multi-agent planning, Critic rejections, and retry loops are tested thoroughly in continuous integration without network dependencies or API costs.

---

## 4. Evaluation Lab Benchmark Suite

The Evaluation Lab executes automated A/B benchmark runs across 12 standardized algorithmic and systems programming challenges.

### 4.1 Canonical Goal Definitions (`custom_goals` in `run_custom_test.py`)
1. **`goal_1` (Data Structures):** Singly linked list with insert, delete, search, and reverse methods + assert verification in `test_linked_list.py`.
2. **`goal_2` (Algorithm Benchmarking):** Bubble sort vs. merge sort timing comparison on 500 random integers with performance measurement.
3. **`goal_3` (File & Data Processing):** CSV analyzer calculating mean, median, and stdev of the 'value' column without pandas.
4. **`goal_4` (Debugging & Repair):** Broken recursive Fibonacci function diagnosis and repair returning the correct 10th number (55).
5. **`goal_5` (Text Tokenization):** Word frequency counter reading `essay.txt`, tokenizing, stripping punctuation, and outputting top 5 words.
6. **`goal_6` (Matrix Math):** 3x3 matrix multiplication from scratch (pure Python loops, no NumPy).
7. **`goal_7` (Data Transformation):** JSON transformer reading `users.json`, filtering age > 25, sorting by name, and writing `filtered_users.json`.
8. **`goal_8` (Resilience & Networking):** Exponential backoff retry logic (1s, 2s, 4s) using `FlakyNetTool`.
9. **`goal_9` (Graph Algorithms):** Graph BFS traversal on an adjacency list asserting order `['A','B','C','D','E']`.
10. **`goal_10` (Modular Imports):** Multi-file import chain creation (`config.py` $\rightarrow$ `utils.py` $\rightarrow$ `main.py`) verifying cross-module imports.
11. **`goal_11` (Exception Handling):** Intentional `ImportError` crash script repaired with a graceful fallback import.
12. **`goal_12` (Search Algorithms):** Iterative binary search with 5 edge-case assert scenarios.

---

## 5. Verification Commands & Execution Guide

### 5.1 Run Offline Unit Test Suite
```bash
# Execute all 155 unit tests
.\.venv\Scripts\python.exe -m pytest backend/tests/unit -v

# Run with concise summary
.\.venv\Scripts\python.exe -m pytest backend/tests/unit -q
```

### 5.2 Run Full Evaluation Lab Benchmark
```bash
# Execute the complete 24-run A/B evaluation suite
.\.venv\Scripts\python.exe run_custom_test.py
```
Outputs are written to `local_test_report/eval_<timestamp>/summary.json`.
