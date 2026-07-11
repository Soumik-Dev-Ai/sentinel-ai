"""Additional tests for working_memory â€” edge cases and remaining uncovered lines."""
from __future__ import annotations

from backend.ai_agent.working_memory import (
    Goal,
    Subtask,
    SubtaskStatus,
    UnresolvableRecord,
    WorkingMemory,
    WorldModel,
)


def test_unresolvable_record_to_dict() -> None:
    u = UnresolvableRecord(
        subtask_id="s1", modes=["err"], attempts=3, evidence="y", hypothesis="fail"
    )
    d = u.to_dict()
    assert d["subtask_id"] == "s1"
    assert d["modes"] == ["err"]
    assert d["attempts"] == 3
    assert d["hypothesis"] == "fail"


def test_world_model_to_dict() -> None:
    w = WorldModel()
    w.record_file("a.txt", "hello")
    w.facts["x"] = 1
    d = w.to_dict()
    assert "files" in d
    assert "facts" in d


def test_insert_subtask_no_active_appends() -> None:
    mem = WorkingMemory.from_goal(
        Goal(id="t1", spec="test", acceptance=[]), ["phase1"], 3
    )
    mem.plan[0].status = SubtaskStatus.PENDING
    s = Subtask("s2", "new task")
    mem.insert_subtask_before_active(s, budget_per=2)
    assert len(mem.plan) == 2
    assert mem.plan[-1].desc == "new task"


def test_insert_subtask_before_active_works() -> None:
    mem = WorkingMemory.from_goal(
        Goal(id="t2", spec="test", acceptance=[]), ["phase1", "phase2"], 3
    )
    s = Subtask("s1b", "inserted")
    mem.insert_subtask_before_active(s, budget_per=2)
    idx = next(i for i, p in enumerate(mem.plan) if p.id == "s1b")
    assert idx == 0
    assert mem.plan[1].status == SubtaskStatus.PENDING

