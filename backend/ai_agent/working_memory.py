from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class SubtaskStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    BLOCKED = "blocked"
    UNRESOLVABLE = "unresolvable"


class FailureMode(StrEnum):
    TOOL_FAILURE = "F1"
    RESULT_INCONSISTENCY = "F2"
    GOAL_DRIFT = "F3"
    INSUFFICIENT_INFORMATION = "F4"
    BUDGET_EXCEEDED = "F5"


@dataclass
class Goal:
    id: str
    spec: str
    acceptance: list[str] = field(default_factory=list)


@dataclass
class Subtask:
    id: str
    desc: str
    status: SubtaskStatus = SubtaskStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "desc": self.desc, "status": self.status.value}


@dataclass
class StepRecord:
    ts: str
    step_ix: int
    thought: str
    tool: str
    args: dict[str, Any]
    result: Any
    eval_result: dict[str, Any]
    correction_trigger: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "step_ix": self.step_ix,
            "thought": self.thought,
            "tool": self.tool,
            "args": self.args,
            "result": self.result,
            "eval": self.eval_result,
            "correction_trigger": self.correction_trigger,
        }


@dataclass
class Finding:
    subtask_id: str
    key: str
    value: Any
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CorrectionRecord:
    ts: str
    step_ix: int
    mode: str
    strategy: str
    mutated_object: str
    new_plan: list[dict[str, Any]] | None = None
    budget_after: int | None = None
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "step_ix": self.step_ix,
            "mode": self.mode,
            "strategy": self.strategy,
            "mutated_object": self.mutated_object,
            "new_plan": self.new_plan,
            "budget_after": self.budget_after,
            "evidence": self.evidence,
        }


@dataclass
class UnresolvableRecord:
    subtask_id: str
    modes: list[str]
    attempts: int
    evidence: str
    hypothesis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "modes": self.modes,
            "attempts": self.attempts,
            "evidence": self.evidence,
            "hypothesis": self.hypothesis,
        }


@dataclass
class WorldModel:
    files: dict[str, str] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)

    def record_file(self, path: str, content: str) -> None:
        self.files[path] = content
        self.hashes[path] = hashlib.sha256(content.encode()).hexdigest()

    def has_file(self, path: str) -> bool:
        return path in self.hashes

    def check_divergence(self, path: str, current_content: str) -> bool:
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()
        return path in self.hashes and self.hashes[path] != current_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files.keys()),
            "facts": self.facts,
        }


@dataclass
class WorkingMemory:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal: Goal | None = None
    plan: list[Subtask] = field(default_factory=list)
    executed: list[StepRecord] = field(default_factory=list)
    findings: dict[str, Finding] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)
    world_model: WorldModel = field(default_factory=WorldModel)
    corrections: list[CorrectionRecord] = field(default_factory=list)
    unresolvable: list[UnresolvableRecord] = field(default_factory=list)
    provider_events: list[dict[str, Any]] = field(default_factory=list)
    final_output: Any = None
    is_finished_flag: bool = False

    @property
    def pending(self) -> list[str]:
        return [s.id for s in self.plan if s.status == SubtaskStatus.PENDING]

    @property
    def active_subtask(self) -> Subtask | None:
        for s in self.plan:
            if s.status == SubtaskStatus.ACTIVE:
                return s
        return None

    def set_plan(self, subtasks: list[Subtask], budget_per: int) -> None:
        self.plan = subtasks
        self.budget = {s.id: budget_per for s in subtasks}

    def advance_subtask(self) -> None:
        for i, s in enumerate(self.plan):
            if s.status == SubtaskStatus.ACTIVE:
                s.status = SubtaskStatus.DONE
                if i + 1 < len(self.plan):
                    self.plan[i + 1].status = SubtaskStatus.ACTIVE
                else:
                    self.is_finished_flag = True
                return

    def activate_first(self) -> None:
        if self.plan and self.plan[0].status == SubtaskStatus.PENDING:
            self.plan[0].status = SubtaskStatus.ACTIVE

    def decrement_budget(self, subtask_id: str) -> int:
        self.budget[subtask_id] = self.budget.get(subtask_id, 0) - 1
        return self.budget[subtask_id]

    def get_budget(self, subtask_id: str) -> int:
        return self.budget.get(subtask_id, 0)

    def record_step(
        self,
        thought: str,
        tool: str,
        args: dict[str, Any],
        result: Any,
        eval_result: dict[str, Any],
        correction_trigger: str | None = None,
    ) -> StepRecord:
        rec = StepRecord(
            ts=datetime.now(UTC).isoformat(),
            step_ix=len(self.executed) + 1,
            thought=thought,
            tool=tool,
            args=args,
            result=result,
            eval_result=eval_result,
            correction_trigger=correction_trigger,
        )
        self.executed.append(rec)
        return rec

    def add_correction(self, rec: CorrectionRecord) -> None:
        self.corrections.append(rec)

    def add_finding(self, subtask_id: str, key: str, value: Any) -> None:
        f = Finding(subtask_id=subtask_id, key=key, value=value)
        self.findings[f"{subtask_id}:{key}"] = f

    def mark_unresolvable(
        self, subtask_id: str, modes: list[str], attempts: int, evidence: str, hypothesis: str
    ) -> None:
        for s in self.plan:
            if s.id == subtask_id:
                s.status = SubtaskStatus.UNRESOLVABLE
        self.unresolvable.append(
            UnresolvableRecord(
                subtask_id=subtask_id,
                modes=modes,
                attempts=attempts,
                evidence=evidence,
                hypothesis=hypothesis,
            )
        )

    def is_finished(self) -> bool:
        if self.is_finished_flag:
            return True
        return all(s.status in (SubtaskStatus.DONE, SubtaskStatus.UNRESOLVABLE) for s in self.plan)

    def replace_plan_from(
        self, from_index: int, new_subtasks: list[Subtask], budget_per: int
    ) -> None:
        kept = self.plan[:from_index]
        self.plan = kept + new_subtasks
        for s in new_subtasks:
            if s.id not in self.budget:
                self.budget[s.id] = budget_per

    def insert_subtask_before_active(self, subtask: Subtask, budget_per: int) -> None:
        for i, s in enumerate(self.plan):
            if s.status == SubtaskStatus.ACTIVE:
                s.status = SubtaskStatus.PENDING
                self.plan.insert(i, subtask)
                self.budget[subtask.id] = budget_per
                return
        self.plan.append(subtask)
        self.budget[subtask.id] = budget_per

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": {
                "id": self.goal.id,
                "spec": self.goal.spec,
                "acceptance": self.goal.acceptance,
            }
            if self.goal
            else None,
            "plan_current": [s.to_dict() for s in self.plan],
            "steps": [s.to_dict() for s in self.executed],
            "corrections": [c.to_dict() for c in self.corrections],
            "provider_events": self.provider_events,
            "unresolvable": [u.to_dict() for u in self.unresolvable],
            "final_output": self.final_output,
            "metrics": self.to_metrics(),
        }

    def to_metrics(self) -> dict[str, Any]:
        return {
            "steps": len(self.executed),
            "self_corrections": len(self.corrections),
            "provider_switches": len(self.provider_events),
            "unresolvable_count": len(self.unresolvable),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def persist(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_goal(cls, goal: Goal, subtask_descs: list[str], budget_per: int) -> WorkingMemory:
        mem = cls(goal=goal)
        subtasks = [Subtask(id=f"S{i + 1}", desc=d) for i, d in enumerate(subtask_descs)]
        mem.set_plan(subtasks, budget_per)
        mem.activate_first()
        return mem

