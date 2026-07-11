"""Unit tests for the structured run logger."""

from __future__ import annotations

import json
from pathlib import Path

from backend.ai_agent.working_memory import Goal, WorkingMemory
from backend.reporter.logger import RunLogger


def _mem() -> WorkingMemory:
    return WorkingMemory.from_goal(Goal(id="T1", spec="test"), ["task1"], 3)


def test_roundtrip_record_serialize_reload_equals() -> None:
    mem = _mem()
    mem.record_step("thinking", "write_file", {}, {"ok": True}, {"success": True})
    data = RunLogger.deserialize(RunLogger.serialize(mem))
    assert data["goal"]["id"] == "T1"
    assert data["steps"][0]["tool"] == "write_file"


def test_persist_creates_file(tmp_path: Path) -> None:
    mem = _mem()
    path = RunLogger(output_dir=tmp_path).persist(mem)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["goal"]["id"] == "T1"


def test_load_roundtrip(tmp_path: Path) -> None:
    mem = _mem()
    logger = RunLogger(output_dir=tmp_path)
    path = logger.persist(mem)
    loaded = logger.load(path)
    assert loaded["goal"]["id"] == "T1"

