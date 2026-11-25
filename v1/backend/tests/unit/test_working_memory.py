"""Unit tests for WorkingMemory and its components."""

from __future__ import annotations

import json
from pathlib import Path

from backend.ai_agent.working_memory import (
    CorrectionRecord,
    Goal,
    Subtask,
    SubtaskStatus,
    WorkingMemory,
    WorldModel,
)


def _make_memory(budget: int = 3) -> WorkingMemory:
    goal = Goal(id="T", spec="test goal", acceptance=["a1"])
    mem = WorkingMemory.from_goal(goal, ["first", "second", "third"], budget)
    return mem


def test_advance_subtask_moves_active_to_done() -> None:
    mem = _make_memory()
    active = mem.active_subtask
    assert active is not None and active.id == "S1"
    assert active.status == SubtaskStatus.ACTIVE
    mem.advance_subtask()
    assert mem.plan[0].status == SubtaskStatus.DONE
    assert mem.active_subtask is not None
    assert mem.active_subtask.id == "S2"


def test_budget_decrement_per_correction() -> None:
    mem = _make_memory(budget=3)
    assert mem.get_budget("S1") == 3
    assert mem.decrement_budget("S1") == 2
    assert mem.decrement_budget("S1") == 1
    assert mem.decrement_budget("S1") == 0
    assert mem.decrement_budget("S1") == -1


def test_escalation_fires_at_zero_budget() -> None:
    mem = _make_memory()
    mem.decrement_budget("S1")
    mem.decrement_budget("S1")
    mem.decrement_budget("S1")
    assert mem.get_budget("S1") == 0
    mem.mark_unresolvable("S1", modes=["F3"], attempts=3, evidence="e", hypothesis="h")
    assert mem.plan[0].status == SubtaskStatus.UNRESOLVABLE
    assert len(mem.unresolvable) == 1
    assert mem.unresolvable[0].modes == ["F3"]
    assert mem.unresolvable[0].hypothesis == "h"


def test_pending_frontier_respects_order() -> None:
    mem = _make_memory()
    ids = mem.pending
    assert ids == ["S2", "S3"]
    mem.advance_subtask()
    ids = mem.pending
    assert ids == ["S3"]


def test_persist_roundtrip_creates_equal_memory(tmp_path: Path) -> None:
    mem = _make_memory()
    mem.advance_subtask()
    mem.add_finding("S1", "k", "v")
    mem.world_model.record_file("fib.py", "content")
    mem.add_correction(
        CorrectionRecord(
            ts="t",
            step_ix=1,
            mode="F1",
            strategy="tool_failure",
            mutated_object="call",
            budget_after=2,
        )
    )
    mem.final_output = "done"

    p = tmp_path / "mem.json"
    mem.persist(p)
    data = json.loads(p.read_text(encoding="utf-8"))

    assert data["goal"]["id"] == "T"
    assert len(data["plan_current"]) == 3
    assert data["final_output"] == "done"
    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["mutated_object"] == "call"
    assert data["metrics"]["steps"] == 0  # no record_step calls
    assert data["metrics"]["self_corrections"] == 1


def test_world_model_content_hash_is_added_on_read() -> None:
    wm = WorldModel()
    wm.record_file("mod.py", "def clamp(x): ...")
    assert wm.has_file("mod.py")
    assert len(wm.hashes["mod.py"]) == 64
    assert wm.files["mod.py"] == "def clamp(x): ..."
    assert not wm.check_divergence("mod.py", "def clamp(x): ...")
    assert wm.check_divergence("mod.py", "def different(): pass")


def test_is_finished_when_no_live_subtasks() -> None:
    mem = _make_memory()
    for _ in mem.plan:
        mem.advance_subtask()
    assert mem.is_finished()


def test_replace_plan_from_discards_tail() -> None:
    mem = _make_memory()
    mem.advance_subtask()  # S1 done, S2 active
    new_subs = [Subtask(id="R1", desc="replan1"), Subtask(id="R2", desc="replan2")]
    mem.replace_plan_from(1, new_subs, 3)
    assert len(mem.plan) == 3  # S1 + R1 + R2
    assert mem.plan[1].id == "R1"
    assert mem.plan[2].id == "R2"


def test_insert_subtask_before_active() -> None:
    mem = _make_memory()
    gather = Subtask(id="G1", desc="gather info")
    mem.insert_subtask_before_active(gather, 3)
    assert mem.plan[0].id == "G1"
    assert mem.plan[1].id == "S1"
    assert mem.plan[1].status == SubtaskStatus.PENDING  # S1 demoted
    assert mem.active_subtask is None  # G1 is pending, not active


def test_to_metrics_counts() -> None:
    mem = _make_memory()
    mem.record_step(
        thought="t",
        tool="write_file",
        args={},
        result={"ok": True},
        eval_result={"success": True, "plan_valid": True},
    )
    mem.add_correction(
        CorrectionRecord(
            ts="t",
            step_ix=1,
            mode="F1",
            strategy="s",
            mutated_object="call",
        )
    )
    mem.provider_events.append({"from": "a", "to": "b"})
    m = mem.to_metrics()
    assert m["steps"] == 1
    assert m["self_corrections"] == 1
    assert m["provider_switches"] == 1

