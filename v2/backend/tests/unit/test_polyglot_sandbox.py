from __future__ import annotations

import os
from pathlib import Path
import pytest
from backend.tools.polyglot_sandbox import (
    PolyglotSandboxTool,
    LANGUAGE_CONFIGS,
    EXT_MAP,
)
from backend.orchestrator.executor import Executor
from backend.orchestrator.retry import classify, FailureCategory


def test_language_configs_present():
    for lang in ("c", "cpp", "rust", "go", "python", "javascript"):
        assert lang in LANGUAGE_CONFIGS
        assert "extension" in LANGUAGE_CONFIGS[lang]
        assert "timeout" in LANGUAGE_CONFIGS[lang]


def test_ext_map_mapping():
    assert EXT_MAP[".c"] == "c"
    assert EXT_MAP[".cpp"] == "cpp"
    assert EXT_MAP[".rs"] == "rust"
    assert EXT_MAP[".go"] == "go"
    assert EXT_MAP[".py"] == "python"
    assert EXT_MAP[".js"] == "javascript"


def test_polyglot_python_execution(tmp_path: Path):
    tool = PolyglotSandboxTool(workspace=tmp_path)
    res = tool.run(code="print('HELLO_POLYGLOT')", language="python")
    assert res["exit_code"] == 0
    assert "HELLO_POLYGLOT" in res["stdout"]
    assert res["error_type"] is None


def test_polyglot_python_timeout(tmp_path: Path):
    tool = PolyglotSandboxTool(workspace=tmp_path)
    res = tool.run(code="import time; time.sleep(5)", language="python", timeout=1)
    assert res["exit_code"] == 124
    assert res["error_type"] == "TimeoutError"


def test_polyglot_javascript_execution(tmp_path: Path):
    import shutil
    if not shutil.which("node"):
        pytest.skip("node runtime not found in PATH")
    tool = PolyglotSandboxTool(workspace=tmp_path)
    res = tool.run(code="console.log('HELLO_NODE');", language="javascript")
    assert res["exit_code"] == 0
    assert "HELLO_NODE" in res["stdout"]


def test_executor_traceback_c_segfault():
    executor = Executor()
    parsed = executor._parse_traceback("Segmentation fault (core dumped)")
    assert parsed is not None
    assert parsed["exception"] == "SegmentationFault"
    assert parsed["kind"] == "logic"
    assert parsed["demands_strategy"] == "full_rewrite"


def test_executor_traceback_gcc_compile_error():
    executor = Executor()
    err_text = "main.c:14:5: error: expected ';' before 'return'"
    parsed = executor._parse_traceback(err_text)
    assert parsed is not None
    assert parsed["exception"] == "CompileError"
    assert parsed["kind"] == "syntax"
    assert parsed["line"] == 14
    assert parsed["demands_strategy"] == "line_patch"


def test_retry_router_classification_segfault():
    failure = classify({
        "exit_code": 139,
        "stderr": "Segmentation fault (core dumped)",
        "parsed_traceback": {
            "exception": "SegmentationFault",
            "kind": "logic",
            "line": 20,
        },
    })
    assert failure.category == FailureCategory.LOGIC
    assert failure.exception == "SegmentationFault"


def test_retry_router_classification_compile_error():
    failure = classify({
        "exit_code": 1,
        "stderr": "main.c:10: error: undefined reference to 'foo'",
        "parsed_traceback": {
            "exception": "CompileError",
            "kind": "syntax",
            "line": 10,
        },
    })
    assert failure.category == FailureCategory.SYNTAX
    assert failure.exception == "CompileError"
